"""Ranking stage (PRD §7.1). Exclude hard-constraint violators, drop OOD, then
rank by lower confidence bound (ci_low) — a confidently-mediocre candidate beats
a wildly-uncertain excellent one."""

from __future__ import annotations

from ..schemas import ScoredCandidate


def rank(scored: list[ScoredCandidate], top_k: int = 5) -> list[ScoredCandidate]:
    eligible = [s for s in scored if not s.hard_violations and not _is_ood(s)]
    eligible.sort(key=lambda s: (s.aggregate.ci_low if s.aggregate else 0.0), reverse=True)
    return eligible[:top_k]


def funnel(generated: list, scored: list[ScoredCandidate]) -> dict:
    passing = [s for s in scored if not s.hard_violations]
    novel = [s for s in passing if "c_novelty" in s.scores and s.scores["c_novelty"].value > 0.0]
    return {
        "generated": len(generated),
        "passing_hard_constraints": len(passing),
        "novel": len(novel),
    }


def _is_ood(s: ScoredCandidate) -> bool:
    return any(e.ood for e in s.scores.values())
