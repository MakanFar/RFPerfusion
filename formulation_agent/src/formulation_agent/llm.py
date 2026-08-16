"""Thin helper over the Anthropic SDK for schema-constrained calls.

Every call in this project returns a Pydantic model — there is no free-text
parsing anywhere above this layer. `structured()` is the only entry point.

Two pieces of defensiveness here are load-bearing:

* **Bounded requests.** The SDK default is a 10-minute timeout with 2 retries,
  so a wedged call can hang for half an hour while looking identical to slow
  work. Every call carries an explicit timeout and fails loudly instead.

* **One repair attempt on validation failure.** A response that fails schema
  validation has already been generated and paid for; discarding it outright is
  the most expensive possible way to handle a fixable problem. This bit us in
  production when a reply exceeded a `max_length` the API was never told about
  (structured outputs don't support string `maxLength` — the SDK strips it and
  validates client-side), destroying a completed answer. The constraints are
  gone now, but the retry stays as insurance against the next one.
"""

from __future__ import annotations

import asyncio
import json
from typing import TypeVar

from anthropic import APITimeoutError, AsyncAnthropic
from pydantic import BaseModel, ValidationError

from .config import SETTINGS

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLMTimeout(LLMError):
    pass


class LLM:
    def __init__(self, api_key: str | None = None, concurrency: int | None = None):
        self.client = AsyncAnthropic(api_key=api_key or SETTINGS.require_api_key())
        self._sem = asyncio.Semaphore(concurrency or SETTINGS.llm_concurrency)

    async def _call(
        self,
        *,
        schema: type[T],
        system: str,
        messages: list[dict],
        model: str | None,
        max_tokens: int | None,
        effort: str | None,
    ):
        async with self._sem:
            client = self.client.with_options(
                timeout=SETTINGS.request_timeout, max_retries=1
            )
            return await client.messages.parse(
                model=model or SETTINGS.model,
                max_tokens=max_tokens or SETTINGS.max_tokens,
                system=system,
                output_config={"effort": effort or SETTINGS.effort},
                output_format=schema,
                messages=messages,
            )

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
        """One schema-constrained call, with a single repair attempt."""
        messages: list[dict] = [{"role": "user", "content": user}]

        for attempt in (1, 2):
            try:
                resp = await self._call(
                    schema=schema,
                    system=system,
                    messages=messages,
                    model=model,
                    max_tokens=max_tokens,
                    effort=effort,
                )
            except APITimeoutError as exc:
                raise LLMTimeout(
                    f"model call exceeded {SETTINGS.request_timeout:.0f}s "
                    f"(raise FA_REQUEST_TIMEOUT if this is expected)"
                ) from exc

            if getattr(resp, "stop_reason", None) == "refusal":
                details = getattr(resp, "stop_details", None)
                category = getattr(details, "category", None) if details else None
                raise LLMError(f"model declined the request (category={category})")

            parsed = getattr(resp, "parsed_output", None)
            if isinstance(parsed, schema):
                return parsed

            text = "".join(
                block.text for block in resp.content if getattr(block, "type", "") == "text"
            ).strip()
            if not text:
                raise LLMError("empty response from model")

            try:
                return _coerce(schema, text)
            except ValidationError as exc:
                if attempt == 2:
                    raise LLMError(f"could not parse structured output: {exc}") from exc
                # Feed the failure back and let the model correct itself rather
                # than throwing away a response we already paid for.
                messages = [
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": text[:8000]},
                    {
                        "role": "user",
                        "content": (
                            "That response failed schema validation:\n\n"
                            f"{exc}\n\n"
                            "Return the same content again, corrected to satisfy the "
                            "schema. Do not add commentary."
                        ),
                    },
                ]

        raise LLMError("structured call exhausted its attempts")  # unreachable

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
        except Exception as exc:  # noqa: BLE001 — surfaced to the user verbatim
            return False, f"{type(exc).__name__}: {exc}"
        return True, "ok"


def _coerce(schema: type[T], text: str) -> T:
    """Parse `text` as `schema`, tolerating prose around the JSON body."""
    try:
        return schema.model_validate_json(text)
    except ValidationError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return schema.model_validate(json.loads(text[start : end + 1]))
        raise
