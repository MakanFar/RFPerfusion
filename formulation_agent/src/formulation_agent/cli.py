"""Interactive REPL for the formulation agent.

Input is read on a worker thread so the event loop keeps running: follow-up
subagents make progress while the scientist is typing, and completed reports
are announced at the next prompt rather than interrupting mid-sentence.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .agent import FormulationAgent, turn
from .config import SETTINGS
from .followup import FollowupManager
from .llm import LLM
from .models import Claim, FollowupStatus, Idea, IdeaStatus, Session, Verification
from .paperclip import Paperclip
from .report import save_session

console = Console()

MARK = {
    Verification.VERIFIED: ("[green]OK[/green]", "green"),
    Verification.PARTIAL: ("[yellow]~[/yellow]", "yellow"),
    Verification.UNSUPPORTED: ("[red]X[/red]", "red"),
    Verification.QUOTE_MISMATCH: ("[red]![/red]", "red"),
    Verification.NO_EVIDENCE: ("[dim]-[/dim]", "dim"),
    Verification.ERROR: ("[dim]?[/dim]", "dim"),
}

REC_COLOUR = {
    "pursue": "bold green",
    "investigate": "cyan",
    "park": "yellow",
    "reject": "red",
}

HELP = """\
[bold]Commands[/bold]

  [cyan]<anything else>[/cyan]        talk to the agent about the ideas
  [cyan]/ideas[/cyan]                 ranked list of live ideas
  [cyan]/show <n|id>[/cyan]           full detail: claims, verified quotes, citations
  [cyan]/evidence <n|id>[/cyan]       every citation for an idea, including failures
  [cyan]/followup <n|id> <q>[/cyan]   investigate in the background; chat continues
  [cyan]/drop <n|id> [reason][/cyan]  remove an idea from the ranking
  [cyan]/more [n][/cyan]              propose n further directions
  [cyan]/jobs[/cyan]                  status of background investigations
  [cyan]/save [path][/cyan]           write session JSON + markdown report
  [cyan]/help[/cyan]  [cyan]/quit[/cyan]
"""


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def render_ranked(session: Session) -> None:
    ideas = session.ranked()
    if not ideas:
        console.print("[dim]No ideas yet. Ask a question to begin.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("#", width=3, justify="right")
    table.add_column("id", width=4)
    table.add_column("direction", overflow="fold")
    table.add_column("score", width=17)
    table.add_column("grounded", width=9, justify="center")
    table.add_column("verdict", width=12)

    for rank, idea in enumerate(ideas, 1):
        s = idea.score
        overall = f"{s.overall:.2f}" if s else "—"
        bar = s.bar(s.overall) if s else ""
        cap = " [red]▲[/red]" if s and s.cap_applied else ""
        lb = idea.load_bearing_claims
        verified = sum(1 for c in lb if c.status is Verification.VERIFIED)
        rec = s.recommendation.value if s else "—"
        table.add_row(
            str(rank),
            idea.id,
            idea.title,
            f"{bar} {overall}{cap}",
            f"{verified}/{len(lb)}",
            f"[{REC_COLOUR.get(rec, 'white')}]{rec}[/]",
        )
    console.print(table)
    if any(i.score and i.score.cap_applied for i in ideas):
        console.print(
            "[dim]▲ = score capped because load-bearing claims are unverified[/dim]"
        )


def render_claim(claim: Claim, show_failures: bool = False) -> None:
    mark, colour = MARK.get(claim.status, ("?", "dim"))
    tag = "" if claim.load_bearing else " [dim](supporting)[/dim]"
    console.print(f"  {mark} [{colour}]{claim.text}[/{colour}]{tag}")

    shown = 0
    for ev in claim.evidence:
        keep = ev.is_grounding or ev.refutes or (show_failures and ev.quote_found)
        if not keep or shown >= (6 if show_failures else 2):
            continue
        shown += 1
        label = "REFUTES" if ev.refutes else ev.support_level.value
        style = "red" if ev.refutes else "green"
        console.print(f'      [{style}]"{ev.quote[:300]}"[/{style}]')
        console.print(
            f"      [dim]— {ev.citation.formatted()}[/dim]\n"
            f"      [blue underline]{ev.ref.citation_url}[/blue underline]"
            f"  [dim]({label})[/dim]"
        )

    if show_failures:
        for ev in claim.evidence:
            if ev.verification is Verification.QUOTE_MISMATCH:
                console.print(
                    f"      [red]discarded — quote not found in "
                    f"{ev.citation.doc_id}[/red] [dim](fabricated or altered)[/dim]"
                )
            elif ev.verification is Verification.UNSUPPORTED:
                console.print(
                    f"      [yellow]discarded — real quote, does not support the "
                    f"claim[/yellow] [dim]{ev.entailment_note[:110]}[/dim]"
                )

    if shown == 0 and not show_failures:
        why = {
            Verification.QUOTE_MISMATCH: "quotes could not be found in the cited papers",
            Verification.UNSUPPORTED: "found papers, none actually support this",
            Verification.NO_EVIDENCE: "no supporting passage retrieved — note the search index has known gaps, so this is weaker than a refutation",
            Verification.ERROR: "retrieval failed",
        }.get(claim.status, "unverified")
        console.print(f"      [dim]{why}[/dim]")


def render_idea(idea: Idea, show_failures: bool = False) -> None:
    s = idea.score
    header = Text(f"{idea.id}  {idea.title}", style="bold")
    console.print(Panel(header, expand=False, border_style="cyan"))
    if idea.one_liner:
        console.print(f"  {idea.one_liner}\n")
    if idea.mechanism_chain:
        console.print("  [bold]mechanism[/bold]  " + " → ".join(idea.mechanism_chain))

    if s:
        console.print(
            f"\n  [bold]confidence[/bold]  {s.overall:.2f}"
            f"   [{REC_COLOUR.get(s.recommendation.value, 'white')}]"
            f"{s.recommendation.value}[/]"
        )
        for axis in (
            "grounding",
            "evidence_strength",
            "mechanistic_plausibility",
            "novelty",
            "testability",
        ):
            val = getattr(s, axis)
            console.print(f"    {axis:<26} {s.bar(val)} {val:.2f}")
        if s.cap_applied:
            console.print(
                f"    [red]capped at {s.grounding_cap:.2f}[/red] "
                f"[dim]— unverified load-bearing claims[/dim]"
            )
        if s.rationale:
            console.print(f"\n  [dim]{s.rationale}[/dim]")

    console.print("\n  [bold]claims[/bold]")
    for claim in idea.claims:
        render_claim(claim, show_failures)

    if idea.key_risk:
        console.print(f"\n  [bold]key risk[/bold]  {idea.key_risk}")
    if idea.testability_note:
        console.print(f"  [bold]testability[/bold]  {idea.testability_note}")
    if idea.novelty_note:
        console.print(f"  [bold]novelty[/bold]  {idea.novelty_note}")
    console.print()


# --------------------------------------------------------------------------
# app
# --------------------------------------------------------------------------


class App:
    def __init__(self) -> None:
        key = SETTINGS.require_api_key()
        self.llm = LLM(api_key=key)
        self.pc = Paperclip(concurrency=SETTINGS.paperclip_concurrency)
        self.agent = FormulationAgent(self.llm, self.pc)
        self.followups = FollowupManager(self.agent)
        self.session = Session()

    # ------------------------------------------------------------- lifecycle

    async def preflight(self) -> bool:
        console.print("[dim]checking paperclip and model access…[/dim]")
        pc_ok, pc_msg = await self.pc.healthcheck()
        llm_ok, llm_msg = await self.llm.healthcheck()
        console.print(
            f"  paperclip  {'[green]ok[/green]' if pc_ok else f'[red]{pc_msg}[/red]'}"
        )
        console.print(
            f"  model      {'[green]ok[/green]' if llm_ok else f'[red]{llm_msg}[/red]'}"
        )
        return pc_ok and llm_ok

    async def run(self) -> None:
        console.print(
            Panel(
                "[bold]Formulation Agent[/bold]\n"
                "Pose an open design question. Every proposed direction is "
                "decomposed into checkable claims and verified against full-text "
                "literature before it is ranked.",
                border_style="cyan",
            )
        )
        if not await self.preflight():
            console.print("\n[red]Preflight failed — fix the above and retry.[/red]")
            return
        console.print(HELP)

        while True:
            self._announce_finished()
            try:
                raw = await asyncio.to_thread(console.input, "\n[bold cyan]›[/bold cyan] ")
            except (EOFError, KeyboardInterrupt):
                break
            line = raw.strip()
            if not line:
                continue
            if line in {"/quit", "/exit", "/q"}:
                break
            try:
                await self.dispatch(line)
            except Exception as exc:  # noqa: BLE001 — REPL must survive anything
                console.print(f"[red]{type(exc).__name__}: {exc}[/red]")

        self.followups.cancel_all()
        if self.session.ideas:
            paths = save_session(self.session, SETTINGS.session_dir)
            console.print(f"\n[dim]session saved: {paths[0]}[/dim]")

    # ------------------------------------------------------------- dispatch

    async def dispatch(self, line: str) -> None:
        if not line.startswith("/"):
            await self.on_text(line)
            return

        cmd, _, rest = line.partition(" ")
        rest = rest.strip()
        match cmd:
            case "/help":
                console.print(HELP)
            case "/ideas":
                render_ranked(self.session)
            case "/show":
                self._with_idea(rest, lambda i, _: render_idea(i, False))
            case "/evidence":
                self._with_idea(rest, lambda i, _: render_idea(i, True))
            case "/drop":
                self.cmd_drop(rest)
            case "/followup":
                self.cmd_followup(rest)
            case "/jobs":
                self.cmd_jobs()
            case "/more":
                await self.cmd_more(rest)
            case "/save":
                paths = save_session(self.session, rest or SETTINGS.session_dir)
                for p in paths:
                    console.print(f"[green]wrote[/green] {p}")
            case _:
                console.print(f"[red]unknown command {cmd}[/red] — try /help")

    # ------------------------------------------------------------- commands

    async def on_text(self, text: str) -> None:
        turn(self.session, "scientist", text)
        if not self.session.question:
            self.session.question = text
            await self.propose_round(first=True)
            return
        with console.status("[dim]thinking…[/dim]"):
            reply = await self.agent.chat(self.session, text)
        turn(self.session, "agent", reply)
        console.print(Markdown(reply))

    async def propose_round(self, first: bool = False, n: int | None = None) -> None:
        verb = "Proposing directions" if first else "Proposing further directions"
        with console.status(f"[dim]{verb}…[/dim]"):
            ideas, reading = await self.agent.propose(self.session, n=n)

        if first and reading:
            console.print(Panel(reading, title="reading of the question", border_style="dim"))

        total = sum(len(i.claims) for i in ideas)
        console.print(
            f"\n[dim]{len(ideas)} directions, {total} claims — "
            f"verifying against literature…[/dim]"
        )

        done = 0

        def progress(claim: Claim, status: str) -> None:
            nonlocal done
            done += 1
            console.print(f"  [dim]({done}/{total})[/dim] {status:<9} {claim.text[:88]}")

        await self.agent.ground_and_score(ideas, progress)
        self.session.ideas.extend(ideas)
        console.print()
        render_ranked(self.session)
        console.print("\n[dim]/show <n> for evidence · /followup <n> <question>[/dim]")

    async def cmd_more(self, rest: str) -> None:
        n = int(rest) if rest.isdigit() else 3
        if not self.session.question:
            console.print("[yellow]Ask a question first.[/yellow]")
            return
        await self.propose_round(first=False, n=n)

    def cmd_drop(self, rest: str) -> None:
        token, _, reason = rest.partition(" ")
        idea = self.session.resolve(token)
        if not idea:
            console.print(f"[red]no such idea: {token!r}[/red]")
            return
        idea.status = IdeaStatus.DROPPED
        idea.drop_reason = reason.strip() or "dropped by scientist"
        turn(self.session, "scientist", f"dropped {idea.id}: {idea.drop_reason}")
        console.print(f"[yellow]dropped[/yellow] {idea.id} — {idea.title}")
        render_ranked(self.session)

    def cmd_followup(self, rest: str) -> None:
        token, _, question = rest.partition(" ")
        idea = self.session.resolve(token)
        if not idea:
            console.print(f"[red]no such idea: {token!r}[/red]")
            return
        if not question.strip():
            console.print("[yellow]usage: /followup <n|id> <question>[/yellow]")
            return
        report = self.followups.spawn(idea, question.strip())
        idea.status = IdeaStatus.UNDER_FOLLOWUP
        self.session.followups.append(report)
        turn(self.session, "scientist", f"follow-up on {idea.id}: {question.strip()}")
        console.print(
            f"[cyan]▶ {report.job_id}[/cyan] investigating [bold]{idea.id}[/bold] "
            f"in the background — keep going, I'll report back."
        )

    def cmd_jobs(self) -> None:
        if not self.session.followups:
            console.print("[dim]no background investigations[/dim]")
            return
        table = Table(box=None, header_style="bold")
        table.add_column("job", width=10)
        table.add_column("idea", width=5)
        table.add_column("status", width=9)
        table.add_column("elapsed", width=8, justify="right")
        table.add_column("question", overflow="fold")
        for r in self.session.followups:
            colour = {
                FollowupStatus.RUNNING: "cyan",
                FollowupStatus.DONE: "green",
                FollowupStatus.FAILED: "red",
                FollowupStatus.CANCELLED: "dim",
            }[r.status]
            table.add_row(
                r.job_id,
                r.idea_id,
                f"[{colour}]{r.status.value}[/{colour}]",
                f"{r.elapsed_s:.0f}s",
                r.question,
            )
        console.print(table)

    # -------------------------------------------------------------- internals

    def _with_idea(self, token: str, fn) -> None:
        idea = self.session.resolve(token)
        if not idea:
            console.print(f"[red]no such idea: {token!r}[/red] — try /ideas")
            return
        fn(idea, None)

    def _announce_finished(self) -> None:
        for report in self.followups.collect():
            idea = self.session.by_id(report.idea_id)
            if idea and idea.status is IdeaStatus.UNDER_FOLLOWUP:
                idea.status = IdeaStatus.REFINED

            if report.status is FollowupStatus.FAILED:
                console.print(
                    f"\n[red]✗ {report.job_id}[/red] follow-up on {report.idea_id} "
                    f"failed: {report.error}"
                )
                continue
            if report.status is FollowupStatus.CANCELLED:
                continue

            colour = {
                "strengthens": "green",
                "weakens": "yellow",
                "refutes": "red",
                "inconclusive": "dim",
            }.get(report.verdict, "white")
            console.print(
                f"\n[green]✓ {report.job_id}[/green] "
                f"[bold]{report.idea_id}[/bold] — [{colour}]{report.verdict}[/{colour}] "
                f"[dim]({report.elapsed_s:.0f}s)[/dim]"
            )
            console.print(Markdown(report.answer))
            for claim in report.claims:
                render_claim(claim)
            if idea and idea.score:
                console.print(
                    f"  [dim]{idea.id} rescored: {idea.score.overall:.2f} "
                    f"({idea.score.recommendation.value})[/dim]"
                )


def main() -> None:
    try:
        asyncio.run(App().run())
    except KeyboardInterrupt:
        console.print("\n[dim]interrupted[/dim]")
        sys.exit(130)


if __name__ == "__main__":
    main()
