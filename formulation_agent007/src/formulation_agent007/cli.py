"""Interactive entry point.

Deliberately thinner than `formulation_agent`'s REPL. A brief is a single
artifact produced from a single question, not a conversation with a ranking
that evolves — so this asks for the question, shows the stages completing, and
prints where the files landed. Use `formulate007-run` for automation.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from .agent import DesignAgent
from .config import SETTINGS
from .emit import save_brief
from .llm import LLM
from .models import DesignBrief

console = Console()


def _ask_question() -> str:
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:]).strip()
    console.print(
        "[bold]Protein design question[/bold] "
        "[dim](what should the protein do, and under what stimulus?)[/dim]"
    )
    try:
        return console.input("› ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _stage_printer():
    def stage(label: str, status: str) -> None:
        colour = {"started": "dim", "ok": "green"}.get(status, "yellow")
        console.print(f"  [{colour}]{label:<12} {status}[/{colour}]")

    return stage


def _summary(brief: DesignBrief) -> Table:
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("gate")
    table.add_column("tools")
    table.add_column("condition")
    table.add_column("cost")
    for gate in brief.proto.ordered():
        name = gate.name + (" *" if gate.decisive else "")
        table.add_row(
            str(gate.order),
            name,
            ", ".join(gate.tool_keys),
            gate.condition(),
            gate.cost_tier,
        )
    return table


async def _main() -> int:
    question = _ask_question()
    if not question:
        console.print("[red]no question given[/red]")
        return 1

    llm = LLM()
    console.print(f"\n[dim]backend: {llm.backend}[/dim]")
    ok, message = await llm.healthcheck()
    if not ok:
        console.print(f"[red]model backend unavailable:[/red] {message}")
        return 1

    console.print("\n[bold]Building brief[/bold]")
    agent = DesignAgent(llm)
    brief = await agent.build(question, progress=_stage_printer())

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = Path(SETTINGS.output_dir) / f"{stamp}-{brief.slug}"
    paths = save_brief(brief, str(out_dir))

    console.print(f"\n[bold]{brief.frame.chosen_pathway}[/bold]")
    console.print(Markdown(f"_{brief.frame.pathway_rationale}_"))
    if brief.frame.simulability_note:
        console.print(
            f"\n[yellow]Not simulable:[/yellow] {brief.frame.simulability_note}"
        )

    console.print(
        f"\n[bold]{len(brief.shards)} shards[/bold] "
        f"{' → '.join(brief.assembly.construct_order)}"
    )
    console.print(_summary(brief))

    if brief.validation_warnings:
        console.print(
            f"\n[yellow]{len(brief.validation_warnings)} validation warning(s)"
            "[/yellow] — see the brief"
        )
        for warning in brief.validation_warnings[:5]:
            console.print(f"  [dim]{warning}[/dim]")

    console.print("\n[bold]Written[/bold]")
    for path in paths:
        console.print(f"  {path}")
    console.print(
        "\n[dim]next: bash "
        f"{out_dir / 'run_literature.sh'} (from the repo root)[/dim]"
    )
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(_main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
