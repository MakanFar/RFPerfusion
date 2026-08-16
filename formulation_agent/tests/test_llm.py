"""Unit tests for the subscription-backed headless LLM adapter."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from formulation_agent.llm import LLM, LLMError, _strict_json_schema


class Reply(BaseModel):
    reply: str


def test_codex_backend_preserves_structured_contract(monkeypatch):
    captured = {}
    llm = LLM(backend="codex", concurrency=1)

    async def fake_run(args, prompt, *, cwd, env):
        captured.update(args=args, prompt=prompt, cwd=cwd, env=env)
        schema_path = Path(args[args.index("--output-schema") + 1])
        captured["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
        return '{"reply":"from codex"}'

    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setenv("CODEX_API_KEY", "must-not-leak")
    monkeypatch.setattr(llm, "_run_process", fake_run)

    result = asyncio.run(
        llm.structured(
            schema=Reply,
            system="system text",
            user="user text",
            effort="low",
        )
    )

    assert result == Reply(reply="from codex")
    assert captured["args"][:2] == ["codex", "exec"]
    assert "--ephemeral" in captured["args"]
    assert "--output-schema" in captured["args"]
    assert captured["schema"]["additionalProperties"] is False
    assert captured["schema"]["required"] == ["reply"]
    assert "system text" in captured["prompt"]
    assert "user text" in captured["prompt"]
    assert "OPENAI_API_KEY" not in captured["env"]
    assert "CODEX_API_KEY" not in captured["env"]


def test_claude_backend_unwraps_structured_output(monkeypatch):
    captured = {}
    llm = LLM(backend="claude", concurrency=1)

    async def fake_run(args, prompt, *, cwd, env):
        captured.update(args=args, prompt=prompt, cwd=cwd, env=env)
        return json.dumps(
            {"is_error": False, "structured_output": {"reply": "from claude"}}
        )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-leak")
    monkeypatch.setattr(llm, "_run_process", fake_run)

    result = asyncio.run(
        llm.structured(
            schema=Reply,
            system="system text",
            user="user text",
            model="opus",
            effort="high",
        )
    )

    assert result == Reply(reply="from claude")
    assert captured["args"][0] == "claude"
    assert "--print" in captured["args"]
    assert "--safe-mode" in captured["args"]
    assert captured["args"][captured["args"].index("--tools") + 1] == ""
    assert captured["args"][captured["args"].index("--model") + 1] == "opus"
    assert captured["prompt"] == "USER:\nuser text"
    assert "ANTHROPIC_API_KEY" not in captured["env"]


def test_invalid_output_gets_one_repair_attempt(monkeypatch):
    calls = []
    llm = LLM(backend="codex", concurrency=1)

    async def fake_call(**kwargs):
        calls.append(kwargs["messages"])
        if len(calls) == 1:
            return '{"wrong":"shape"}'
        return '{"reply":"repaired"}'

    monkeypatch.setattr(llm, "_call", fake_call)
    result = asyncio.run(
        llm.structured(schema=Reply, system="system", user="user", effort="low")
    )

    assert result.reply == "repaired"
    assert len(calls) == 2
    assert calls[1][-1]["role"] == "user"
    assert "failed schema validation" in calls[1][-1]["content"]


def test_claude_error_envelope_is_reported(monkeypatch):
    llm = LLM(backend="claude", concurrency=1)

    async def fake_run(args, prompt, *, cwd, env):
        return json.dumps({"is_error": True, "result": "please run claude auth login"})

    monkeypatch.setattr(llm, "_run_process", fake_run)
    with pytest.raises(LLMError, match="claude auth login"):
        asyncio.run(
            llm.structured(schema=Reply, system="system", user="user", effort="low")
        )


def test_strict_schema_requires_defaulted_nested_fields():
    class Child(BaseModel):
        names: list[str] = Field(default_factory=list)

    class Parent(BaseModel):
        child: Child

    schema = _strict_json_schema(Parent.model_json_schema())

    assert schema["required"] == ["child"]
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["Child"]["required"] == ["names"]
    assert schema["$defs"]["Child"]["additionalProperties"] is False
    assert "default" not in schema["$defs"]["Child"]["properties"]["names"]


def test_unknown_backend_is_rejected(monkeypatch):
    monkeypatch.delenv("FA_LLM_BACKEND", raising=False)
    with pytest.raises(ValueError, match="use 'codex' or 'claude'"):
        LLM(backend="api")
