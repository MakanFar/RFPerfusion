"""Structured model calls through subscription-authenticated headless CLIs.

The rest of the formulation agent only knows about :meth:`LLM.structured`.
Each call launches a fresh, non-interactive Codex or Claude process, asks it for
JSON matching the supplied Pydantic model, and validates the result locally.

The child process is deliberately isolated from the repository and has tools
disabled (Claude) or a read-only sandbox (Codex). API-key environment variables
are removed so the CLIs use their saved subscription authentication rather than
silently switching to usage-based API billing.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .config import SETTINGS

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLMTimeout(LLMError):
    pass


class LLM:
    """Drop-in structured-output client backed by Codex or Claude Code."""

    def __init__(self, backend: str | None = None, concurrency: int | None = None):
        self.backend = (backend or SETTINGS.llm_backend).strip().lower()
        if self.backend not in {"codex", "claude"}:
            raise ValueError(
                f"unsupported FA_LLM_BACKEND={self.backend!r}; use 'codex' or 'claude'"
            )
        self._sem = asyncio.Semaphore(concurrency or SETTINGS.llm_concurrency)

    async def _call(
        self,
        *,
        schema: type[T],
        system: str,
        messages: list[dict[str, str]],
        model: str | None,
        effort: str | None,
    ) -> str:
        async with self._sem:
            if self.backend == "codex":
                return await self._call_codex(schema, system, messages, model, effort)
            return await self._call_claude(schema, system, messages, model, effort)

    async def _call_codex(
        self,
        schema: type[T],
        system: str,
        messages: list[dict[str, str]],
        model: str | None,
        effort: str | None,
    ) -> str:
        with tempfile.TemporaryDirectory(prefix="formulation-codex-") as tmp:
            schema_path = Path(tmp) / "schema.json"
            schema_path.write_text(
                json.dumps(_strict_json_schema(schema.model_json_schema())),
                encoding="utf-8",
            )
            args = [
                "codex",
                "exec",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--ignore-user-config",
                "--ignore-rules",
                "--output-schema",
                str(schema_path),
            ]
            if model:
                args.extend(["--model", model])
            if effort:
                args.extend(["--config", f'model_reasoning_effort="{effort}"'])
            args.append("-")
            prompt = (
                "Answer directly. Do not use tools or inspect the filesystem.\n\n"
                "Follow these instructions as the system prompt:\n\n"
                f"{system}\n\nCONVERSATION:\n{_render_messages(messages)}"
            )
            env = _subscription_env("codex")
            return await self._run_process(args, prompt, cwd=tmp, env=env)

    async def _call_claude(
        self,
        schema: type[T],
        system: str,
        messages: list[dict[str, str]],
        model: str | None,
        effort: str | None,
    ) -> str:
        output_schema = json.dumps(_strict_json_schema(schema.model_json_schema()))
        args = [
            "claude",
            "--print",
            "--safe-mode",
            "--no-session-persistence",
            "--permission-mode",
            "dontAsk",
            "--tools",
            "",
            "--input-format",
            "text",
            "--output-format",
            "json",
            "--json-schema",
            output_schema,
            "--system-prompt",
            system,
        ]
        if model:
            args.extend(["--model", model])
        if effort:
            args.extend(["--effort", effort])

        with tempfile.TemporaryDirectory(prefix="formulation-claude-") as tmp:
            raw = await self._run_process(
                args,
                _render_messages(messages),
                cwd=tmp,
                env=_subscription_env("claude"),
            )
        return _unwrap_claude(raw)

    async def _run_process(
        self,
        args: list[str],
        prompt: str,
        *,
        cwd: str,
        env: dict[str, str],
    ) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                cwd=cwd,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise LLMError(
                f"{self.backend} CLI is not installed or is not on PATH"
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(prompt.encode()), timeout=SETTINGS.request_timeout
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise LLMTimeout(
                f"{self.backend} call exceeded {SETTINGS.request_timeout:.0f}s "
                "(raise FA_REQUEST_TIMEOUT if this is expected)"
            ) from exc

        out = stdout.decode(errors="replace").strip()
        err = stderr.decode(errors="replace").strip()
        if process.returncode:
            detail = (err or out or "no diagnostic output")[-4000:]
            raise LLMError(
                f"{self.backend} exited with status {process.returncode}: {detail}"
            )
        if not out:
            raise LLMError(f"{self.backend} returned an empty response")
        return out

    async def structured(
        self,
        *,
        schema: type[T],
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int | None = None,
        effort: str | None = None,
    ) -> T:
        """Make one schema-constrained call, with one repair attempt.

        ``max_tokens`` remains in the interface because every existing caller
        supplies the same contract. Neither headless CLI exposes an equivalent
        per-call output-token flag, so the value is intentionally ignored.
        """
        del max_tokens
        messages: list[dict[str, str]] = [{"role": "user", "content": user}]

        for attempt in (1, 2):
            text = await self._call(
                schema=schema,
                system=system,
                messages=messages,
                model=model or SETTINGS.model,
                effort=effort or SETTINGS.effort,
            )
            try:
                return _coerce(schema, text)
            except (ValidationError, json.JSONDecodeError) as exc:
                if attempt == 2:
                    raise LLMError(f"could not parse structured output: {exc}") from exc
                messages.extend(
                    [
                        {"role": "assistant", "content": text[:8000]},
                        {
                            "role": "user",
                            "content": (
                                "That response failed schema validation:\n\n"
                                f"{exc}\n\n"
                                "Return the same content again, corrected to satisfy "
                                "the schema. Do not add commentary."
                            ),
                        },
                    ]
                )

        raise LLMError("structured call exhausted its attempts")  # pragma: no cover

    async def healthcheck(self) -> tuple[bool, str]:
        class _Ping(BaseModel):
            ok: bool

        try:
            await self.structured(
                schema=_Ping,
                system="Reply with ok=true.",
                user="ping",
                max_tokens=2_000,
                effort="low",
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the user verbatim
            return False, f"{type(exc).__name__}: {exc}"
        return True, f"ok ({self.backend})"


def _render_messages(messages: list[dict[str, str]]) -> str:
    return "\n\n".join(
        f"{message['role'].upper()}:\n{message['content']}" for message in messages
    )


def _subscription_env(backend: str) -> dict[str, str]:
    """Prevent an inherited API key from overriding saved subscription auth."""
    env = os.environ.copy()
    keys = {
        "codex": ("OPENAI_API_KEY", "CODEX_API_KEY"),
        "claude": ("ANTHROPIC_API_KEY",),
    }[backend]
    for key in keys:
        env.pop(key, None)
    return env


def _strict_json_schema(value: Any) -> Any:
    """Make Pydantic's schema acceptable to strict structured-output APIs."""
    if isinstance(value, list):
        return [_strict_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    cleaned = {
        key: _strict_json_schema(item)
        for key, item in value.items()
        if key != "default"
    }
    properties = cleaned.get("properties")
    if isinstance(properties, dict):
        cleaned["required"] = list(properties)
        cleaned["additionalProperties"] = False
    return cleaned


def _unwrap_claude(text: str) -> str:
    """Extract structured content from Claude Code's JSON result envelope."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(payload, dict):
        return text
    if payload.get("is_error"):
        raise LLMError(f"claude failed: {payload.get('result') or 'unknown error'}")
    structured = payload.get("structured_output")
    if structured is not None:
        return json.dumps(structured)
    result = payload.get("result")
    if isinstance(result, str):
        return result
    if result is not None:
        return json.dumps(result)
    return text


def _coerce(schema: type[T], text: str) -> T:
    """Parse ``text`` as ``schema``, tolerating prose around the JSON body."""
    try:
        return schema.model_validate_json(text)
    except (ValidationError, json.JSONDecodeError):
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return schema.model_validate(json.loads(text[start : end + 1]))
        raise
