"""Compose an idea's confidence score.

Split of responsibility, on purpose:

* **Computed in code, not by a model** — grounding and evidence strength. These
  are counts over verification outcomes. A model cannot argue its way to a
  better grounding number.
* **Judged by a model** — mechanistic plausibility, novelty, testability. These
  are genuinely matters of scientific judgement and there is no honest way to
  compute them.

`overall` is then a weighted blend *bounded from above* by grounding. That cap
is the mechanism that stops a fluent, well-argued, entirely ungrounded idea
from outranking a modest one with real citations behind it — which is the
failure mode this whole tool exists to prevent.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .config import SETTINGS
from .models import Claim, Idea, IdeaScore, Recommendation, SupportLevel

_STRENGTH = {
    SupportLevel.ESTABLISHED: 1.0,
    SupportLevel.CONTESTED: 0.6,
    SupportLevel.SPECULATIVE: 0.3,
}

WEIGHTS = {
    "grounding": 0.34,
    "evidence_strength": 0.20,
    "mechanistic_plausibility": 0.24,
    "novelty": 0.10,
    "testability": 0.12,
}


class JudgedAxes(BaseModel):
    """The three axes that require scientific judgement rather than counting."""

    mechanistic_plausibility: float = Field(ge=0.0, le=1.0)
    novelty: float = Field(ge=0.0, le=1.0)
    testability: float = Field(ge=0.0, le=1.0)
    rationale: str


JUDGE_SYSTEM = (
    "You are scoring a proposed research direction on three axes. You are given "
    "the idea and ONLY the evidence that survived independent verification.\n\n"
    "  mechanistic_plausibility — could this physically work, given the verified "
    "evidence? Penalise heavily if a required step has no verified support.\n"
    "  novelty — how far is this from what the verified literature already "
    "reports? An idea the literature already describes in full scores low.\n"
    "  testability — could a competent lab get a decisive readout in weeks, not "
    "years? Prefer directions with an existing assay.\n\n"
    "Calibration: 0.5 is an ordinary, unremarkable score. Reserve >0.8 for cases "
    "where the verified evidence genuinely compels it. Do not let confident "
    "prose raise your score — you are shown the rationale, but only the evidence "
    "should move you. If the evidence list is empty, mechanistic_plausibility "
    "must not exceed 0.35."
)


def compute_grounding(claims: list[Claim]) -> float:
    """Fraction of load-bearing claims that carry verified support.

    Partial support counts as half. Claims with no load-bearing role are ignored.
    """
    load_bearing = [c for c in claims if c.load_bearing]
    if not load_bearing:
        return 0.0
    total = 0.0
    for claim in load_bearing:
        if claim.verified_evidence:
            total += 1.0
        elif claim.partial_evidence:
            total += 0.5
    return total / len(load_bearing)


def compute_evidence_strength(claims: list[Claim]) -> float:
    strengths = [
        _STRENGTH[e.support_level]
        for c in claims
        for e in c.verified_evidence
    ]
    if not strengths:
        return 0.0
    return sum(strengths) / len(strengths)


def has_refutation(claims: list[Claim]) -> bool:
    return any(c.refuting_evidence for c in claims if c.load_bearing)


def grounding_cap(grounding: float, refuted: bool, settings=SETTINGS) -> float:
    """Upper bound on `overall`, derived from how well grounded the idea is."""
    if refuted:
        return 0.35
    if grounding <= 0.0:
        return settings.ungrounded_ceiling
    if grounding < 0.6:
        return settings.partial_ceiling
    return 1.0


def recommend(overall: float, grounding: float, refuted: bool) -> Recommendation:
    if refuted:
        return Recommendation.REJECT
    if grounding <= 0.0:
        # Not "bad" — unevidenced. The honest next move is to look, not to bet.
        return Recommendation.INVESTIGATE if overall >= 0.3 else Recommendation.PARK
    if overall >= 0.7:
        return Recommendation.PURSUE
    if overall >= 0.45:
        return Recommendation.INVESTIGATE
    return Recommendation.PARK


def assemble(idea: Idea, axes: JudgedAxes, settings=SETTINGS) -> IdeaScore:
    grounding = compute_grounding(idea.claims)
    strength = compute_evidence_strength(idea.claims)
    refuted = has_refutation(idea.claims)

    raw = (
        WEIGHTS["grounding"] * grounding
        + WEIGHTS["evidence_strength"] * strength
        + WEIGHTS["mechanistic_plausibility"] * axes.mechanistic_plausibility
        + WEIGHTS["novelty"] * axes.novelty
        + WEIGHTS["testability"] * axes.testability
    )

    cap = grounding_cap(grounding, refuted, settings)
    overall = min(raw, cap)

    return IdeaScore(
        grounding=round(grounding, 3),
        evidence_strength=round(strength, 3),
        mechanistic_plausibility=round(axes.mechanistic_plausibility, 3),
        novelty=round(axes.novelty, 3),
        testability=round(axes.testability, 3),
        overall=round(overall, 3),
        grounding_cap=cap,
        cap_applied=overall < raw - 1e-9,
        recommendation=recommend(overall, grounding, refuted),
        rationale=axes.rationale,
    )


def evidence_digest(idea: Idea, max_items: int = 12) -> str:
    """Verified-evidence-only view of an idea, for the scoring judge."""
    lines: list[str] = []
    for claim in idea.claims:
        tag = "LOAD-BEARING" if claim.load_bearing else "supporting"
        lines.append(f"\nCLAIM ({tag}): {claim.text}")
        lines.append(f"  verification: {claim.status.value}")
        shown = 0
        for ev in claim.evidence:
            if shown >= 3:
                break
            if ev.is_grounding:
                lines.append(
                    f'  [VERIFIED · {ev.support_level.value}] "{ev.quote[:240]}"'
                    f"\n      — {ev.citation.formatted()} {ev.ref.span}"
                )
                shown += 1
            elif ev.refutes and ev.quote_found:
                lines.append(
                    f'  [REFUTES · verified] "{ev.quote[:240]}"'
                    f"\n      — {ev.citation.formatted()} {ev.ref.span}"
                )
                shown += 1
        if shown == 0:
            lines.append("  (no evidence survived verification)")
    return "\n".join(lines[: max_items * 4])
