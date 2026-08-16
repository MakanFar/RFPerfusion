"""Non-interactive entry point for agent and automation use.

    uv run --project formulation_agent007 formulate007-run \
      --question "..." --output-dir formulation_agent007/briefs/example
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .agent import DesignAgent
from .emit import save_brief
from .llm import LLM


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Turn a protein design question into a shard decomposition, a "
            "Paperclip mining plan, an assembly recipe, and a proto-tools "
            "fitness cascade."
        )
    )
    question = parser.add_mutually_exclusive_group(required=True)
    question.add_argument("--question", help="open protein design question")
    question.add_argument("--question-file", type=Path, help="UTF-8 question file")
    parser.add_argument(
        "--context-file",
        type=Path,
        action="append",
        default=[],
        help="optional framing context; repeat for multiple files",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--json-progress",
        action="store_true",
        help="emit machine-readable JSON Lines progress",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="do not healthcheck the model backend first",
    )
    return parser


def read_question(args: argparse.Namespace) -> str:
    text = args.question
    if args.question_file:
        text = args.question_file.read_text(encoding="utf-8")
    text = (text or "").strip()
    if not text:
        raise ValueError("the question is empty")
    return text


def read_context(paths: list[Path]) -> str:
    sections = []
    for path in paths:
        content = path.read_text(encoding="utf-8").strip()
        if content:
            sections.append(f"SOURCE: {path}\n{content}")
    return "\n\n".join(sections)


class Progress:
    def __init__(self, json_lines: bool):
        self.json_lines = json_lines

    def emit(self, event: str, **fields) -> None:
        payload = {"event": event, **fields}
        if self.json_lines:
            print(json.dumps(payload), flush=True)
        else:
            detail = " ".join(f"{key}={value}" for key, value in fields.items())
            print(f"[{event}] {detail}".rstrip(), flush=True)

    def stage(self, label: str, status: str) -> None:
        self.emit("stage", name=label, status=status)


async def run_once(args: argparse.Namespace) -> list[Path]:
    question = read_question(args)
    context = read_context(args.context_file)
    progress = Progress(args.json_progress)

    llm = LLM()
    if not args.skip_preflight:
        progress.emit("preflight_started")
        ok, message = await llm.healthcheck()
        progress.emit("preflight_finished", model_ok=ok, model_message=message)
        if not ok:
            raise RuntimeError(f"model backend preflight failed: {message}")

    agent = DesignAgent(llm)
    brief = await agent.build(question, context, progress.stage)

    paths = save_brief(brief, str(args.output_dir))
    progress.emit(
        "finished",
        slug=brief.slug,
        shards=len(brief.shards),
        gates=len(brief.proto.gates),
        warnings=len(brief.validation_warnings),
        paths=[str(path) for path in paths],
    )
    return paths


def main() -> None:
    args = build_parser().parse_args()
    try:
        asyncio.run(run_once(args))
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"formulate007-run: {exc}") from exc


if __name__ == "__main__":
    main()
