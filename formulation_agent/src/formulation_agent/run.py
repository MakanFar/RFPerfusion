"""Non-interactive entry point for agent and automation use."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .agent import FormulationAgent, turn
from .config import SETTINGS
from .llm import LLM
from .models import Claim, Session
from .paperclip import Paperclip
from .report import save_session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate literature-grounded research directions in one run."
    )
    question = parser.add_mutually_exclusive_group(required=True)
    question.add_argument("--question", help="open research or design question")
    question.add_argument("--question-file", type=Path, help="UTF-8 question file")
    parser.add_argument(
        "--context-file",
        type=Path,
        action="append",
        default=[],
        help="optional proposal context; repeat for multiple files",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--n-ideas", type=int, help="override the configured idea count"
    )
    parser.add_argument(
        "--json-progress",
        action="store_true",
        help="emit machine-readable JSON Lines progress",
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
        self.completed = 0

    def emit(self, event: str, **fields) -> None:
        payload = {"event": event, **fields}
        if self.json_lines:
            print(json.dumps(payload), flush=True)
        else:
            detail = " ".join(f"{key}={value}" for key, value in fields.items())
            print(f"[{event}] {detail}".rstrip(), flush=True)

    def claim(self, claim: Claim, status: str) -> None:
        self.completed += 1
        self.emit(
            "claim",
            completed=self.completed,
            claim_id=claim.id,
            status=status,
            text=claim.text,
        )


async def run_once(args: argparse.Namespace) -> list[Path]:
    question = read_question(args)
    context = read_context(args.context_file)
    progress = Progress(args.json_progress)

    llm = LLM(api_key=SETTINGS.require_api_key())
    paperclip = Paperclip(concurrency=SETTINGS.paperclip_concurrency)
    agent = FormulationAgent(llm, paperclip)

    progress.emit("preflight_started")
    pc_ok, pc_message = await paperclip.healthcheck()
    llm_ok, llm_message = await llm.healthcheck()
    progress.emit(
        "preflight_finished",
        paperclip_ok=pc_ok,
        paperclip_message=pc_message,
        model_ok=llm_ok,
        model_message=llm_message,
    )
    if not pc_ok or not llm_ok:
        raise RuntimeError("preflight failed; inspect the reported dependency status")

    session = Session(question=question)
    turn(session, "scientist", question)
    progress.emit("proposal_started")
    ideas, reading = await agent.propose(
        session,
        extra_context=context,
        n=args.n_ideas,
    )
    progress.emit(
        "proposal_finished",
        ideas=len(ideas),
        claims=sum(len(idea.claims) for idea in ideas),
        reading_of_question=reading,
    )

    await agent.ground_and_score(ideas, progress.claim)
    session.ideas.extend(ideas)
    paths = save_session(session, str(args.output_dir))
    progress.emit("finished", paths=[str(path) for path in paths])
    return paths


def main() -> None:
    args = build_parser().parse_args()
    if args.n_ideas is not None and args.n_ideas < 1:
        raise SystemExit("--n-ideas must be at least 1")
    try:
        asyncio.run(run_once(args))
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"formulate-run: {exc}") from exc


if __name__ == "__main__":
    main()
