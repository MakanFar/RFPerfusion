"""Background follow-up subagents.

When the scientist asks a follow-up about an idea, that investigation runs as a
detached asyncio task while the main conversation continues. The scientist is
never blocked on a literature search.

Each subagent does the same thing the main agent does, scoped to one question:
decompose into checkable claims, ground them, then report a verdict. It reports
back with the same verified-evidence guarantee — a follow-up cannot introduce
an unverified assertion into the session.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from .agent import FormulationAgent
from .models import Claim, FollowupReport, FollowupStatus, Idea

MAX_CONCURRENT_JOBS = 4


class SubClaim(BaseModel):
    text: str
    search_queries: list[str] = Field(default_factory=list)
    exact_terms: list[str] = Field(default_factory=list)


class SubQuestions(BaseModel):
    claims: list[SubClaim] = Field(default_factory=list)


class Synthesis(BaseModel):
    answer: str
    verdict: Literal["strengthens", "weakens", "inconclusive", "refutes"]
    revised_key_risk: str = ""


DECOMPOSE_SYSTEM = """A scientist asked a follow-up question about a proposed \
research direction. Break the question into 2-4 checkable factual claims that a \
literature search could confirm or refute.

Same rules as before: one proposition per claim, specific enough that a paper \
could contradict it, quantities wherever possible. For each claim give 1-2 \
literature search queries — topical noun phrases, not questions — and \
`exact_terms`: literal named entities (proteins, genes, reagents, techniques) \
matched verbatim against full text.

Do not answer the question. Only decompose it into what would need to be true."""


SYNTHESIS_SYSTEM = """You are reporting the result of a focused literature \
investigation back to a scientist.

You are given the follow-up question and ONLY the evidence that survived \
independent verification. Answer the question directly in a short paragraph.

Set `verdict` relative to the idea the question was about:
  strengthens   — verified evidence supports the direction
  weakens       — verified evidence makes it look worse, without killing it
  refutes       — verified evidence contradicts something load-bearing
  inconclusive  — nothing verified either way

Say plainly when the literature does not answer the question. "The corpus does \
not contain this" is a legitimate and useful finding — do not pad it into an \
answer that sounds more complete than it is."""


class FollowupManager:
    """Owns detached follow-up tasks and hands back completed reports."""

    def __init__(self, agent: FormulationAgent):
        self.agent = agent
        self.jobs: dict[str, asyncio.Task] = {}
        self.reports: dict[str, FollowupReport] = {}
        self._delivered: set[str] = set()
        self._sem = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

    # ----------------------------------------------------------------- public

    def spawn(self, idea: Idea, question: str) -> FollowupReport:
        job_id = f"F{len(self.reports) + 1}-{uuid.uuid4().hex[:4]}"
        report = FollowupReport(job_id=job_id, idea_id=idea.id, question=question)
        self.reports[job_id] = report
        idea.followup_ids.append(job_id)
        self.jobs[job_id] = asyncio.create_task(self._run(idea, report))
        return report

    def running(self) -> list[FollowupReport]:
        return [r for r in self.reports.values() if r.status is FollowupStatus.RUNNING]

    def collect(self) -> list[FollowupReport]:
        """Return reports that finished since the last call."""
        done = [
            r
            for r in self.reports.values()
            if r.status is not FollowupStatus.RUNNING and r.job_id not in self._delivered
        ]
        for report in done:
            self._delivered.add(report.job_id)
        return done

    async def drain(self, timeout: float = 300.0) -> None:
        pending = [t for t in self.jobs.values() if not t.done()]
        if pending:
            await asyncio.wait(pending, timeout=timeout)

    def cancel_all(self) -> None:
        for job_id, task in self.jobs.items():
            if not task.done():
                task.cancel()
                self.reports[job_id].status = FollowupStatus.CANCELLED

    # ---------------------------------------------------------------- worker

    async def _run(self, idea: Idea, report: FollowupReport) -> None:
        from datetime import datetime, timezone

        try:
            async with self._sem:
                claims = await self._decompose(idea, report.question)
                await self.agent.grounder.ground_claims(claims)
                report.claims = claims
                synthesis = await self._synthesise(idea, report.question, claims)
                report.answer = synthesis.answer
                report.verdict = synthesis.verdict
                if synthesis.revised_key_risk:
                    idea.key_risk = synthesis.revised_key_risk
                # fold the new verified claims into the idea and rescore
                idea.claims.extend(claims)
                await self.agent.score(idea)
            report.status = FollowupStatus.DONE
        except asyncio.CancelledError:
            report.status = FollowupStatus.CANCELLED
            raise
        except Exception as exc:  # noqa: BLE001 — surfaced in the report, not raised
            report.status = FollowupStatus.FAILED
            report.error = f"{type(exc).__name__}: {exc}"
        finally:
            report.finished_at = datetime.now(timezone.utc)

    async def _decompose(self, idea: Idea, question: str) -> list[Claim]:
        user = (
            f"RESEARCH DIRECTION: {idea.title}\n{idea.one_liner}\n"
            f"MECHANISM: {' -> '.join(idea.mechanism_chain) or 'n/a'}\n\n"
            f"FOLLOW-UP QUESTION:\n{question}"
        )
        result = await self.agent.llm.structured(
            schema=SubQuestions, system=DECOMPOSE_SYSTEM, user=user, max_tokens=6_000
        )
        base = len(idea.claims)
        # Follow-up claims are not load-bearing: a follow-up adds detail, it does
        # not silently re-found the idea on a new set of assumptions. The idea's
        # grounding score still reflects the claims it was originally proposed on.
        return [
            Claim(
                id=f"{idea.id}.C{base + i + 1}",
                text=c.text,
                load_bearing=False,
                search_queries=c.search_queries or [c.text],
                exact_terms=c.exact_terms,
            )
            for i, c in enumerate(result.claims)
        ]

    async def _synthesise(self, idea: Idea, question: str, claims: list[Claim]) -> Synthesis:
        from .scoring import evidence_digest

        stub = Idea(id=idea.id, title=idea.title, claims=claims)
        user = (
            f"RESEARCH DIRECTION: {idea.title}\n\n"
            f"FOLLOW-UP QUESTION:\n{question}\n\n"
            f"VERIFIED EVIDENCE:\n{evidence_digest(stub) or '(nothing verified)'}"
        )
        return await self.agent.llm.structured(
            schema=Synthesis, system=SYNTHESIS_SYSTEM, user=user, max_tokens=6_000
        )
