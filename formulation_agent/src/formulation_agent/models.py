"""Typed contracts for the formulation agent.

These are the only structures that cross a component boundary. The grounding
pipeline, the scorer, the follow-up manager and the CLI all speak in terms of
`Idea` / `Claim` / `Evidence` and nothing else.

Design rule that motivates most of this file: an idea is only ever as credible
as the weakest claim it stands on, and a claim is only credible if a *separate*
check confirmed the paper says what we think it says. So evidence carries its
own verification verdict, and the verdict is derived, never asserted by the
model that proposed the idea.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# enums
# --------------------------------------------------------------------------


class SupportLevel(str, Enum):
    """How settled the underlying science is, per the source itself."""

    ESTABLISHED = "established"
    CONTESTED = "contested"
    SPECULATIVE = "speculative"


class EvidenceKind(str, Enum):
    EXPERIMENTAL = "experimental"
    COMPUTATIONAL = "computational"
    REVIEW = "review"
    THEORETICAL = "theoretical"


class Verification(str, Enum):
    """Outcome of the two-layer check in `grounding.py`.

    Only VERIFIED counts as grounding. Everything else is a failure mode we
    name explicitly rather than collapsing into "unsupported", because the
    scientist needs to know *how* it failed to decide what to do about it.
    """

    VERIFIED = "verified"  # quote is real AND entails the claim
    QUOTE_MISMATCH = "quote_mismatch"  # quoted text not found at those lines
    UNSUPPORTED = "unsupported"  # quote is real but doesn't support the claim
    PARTIAL = "partial"  # quote is real, supports the claim only in part
    NO_EVIDENCE = "no_evidence"  # searched, nothing relevant in the corpus
    ERROR = "error"  # retrieval or check failed


class IdeaStatus(str, Enum):
    PROPOSED = "proposed"
    DROPPED = "dropped"
    UNDER_FOLLOWUP = "under_followup"
    REFINED = "refined"


class Recommendation(str, Enum):
    PURSUE = "pursue"
    INVESTIGATE = "investigate"
    PARK = "park"
    REJECT = "reject"


# --------------------------------------------------------------------------
# evidence
# --------------------------------------------------------------------------

_CORPUS_PREFIX = {"fda_": "fda", "tri_": "trials"}


class LineRef(BaseModel):
    """A pin into a specific span of a specific document."""

    doc_id: str
    start_line: int
    end_line: int

    @property
    def span(self) -> str:
        if self.end_line and self.end_line != self.start_line:
            return f"L{self.start_line}-L{self.end_line}"
        return f"L{self.start_line}"

    @property
    def citation_url(self) -> str:
        corpus = "papers"
        for prefix, name in _CORPUS_PREFIX.items():
            if self.doc_id.startswith(prefix):
                corpus = name
                break
        return f"https://paperclip.gxl.ai/citations/{corpus}/{self.doc_id}#{self.span}"


class Citation(BaseModel):
    doc_id: str
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    journal: str = ""
    year: int | None = None
    doi: str = ""
    source: str = ""

    def formatted(self) -> str:
        """Nature-ish reference line; preprints get the bioRxiv/medRxiv form."""
        who = ", ".join(self.authors[:3])
        if len(self.authors) > 3:
            who += " et al."
        venue = self.journal
        if not venue:
            src = self.source.lower()
            if src in {"biorxiv", "medrxiv", "arxiv"}:
                venue = f"{self.source} preprint"
            # "pmc" is an archive, not a journal — better to omit the venue than
            # to print a corpus name where a reader expects a publication.
            elif src not in {"pmc", "", "papers"}:
                venue = self.source
        bits = [b for b in (who, f'"{self.title}."', f"*{venue}*") if b.strip(' "*.')]
        line = " ".join(bits)
        if self.year:
            line += f" ({self.year})"
        if self.doi:
            line += f". doi:{self.doi}"
        return line


class Evidence(BaseModel):
    """One verbatim span of one paper, offered in support of one claim."""

    quote: str
    ref: LineRef
    citation: Citation
    support_level: SupportLevel = SupportLevel.SPECULATIVE
    evidence_kind: EvidenceKind = EvidenceKind.EXPERIMENTAL

    # populated by grounding.py — never by the proposing model
    quote_found: bool = False
    entailment: Literal["yes", "partial", "no", "unknown"] = "unknown"
    entailment_note: str = ""
    verification: Verification = Verification.ERROR
    # A verified quote that *cuts against* the claim. Kept deliberately: a
    # formulation agent that silently drops refutations is worse than useless.
    refutes: bool = False

    @property
    def is_grounding(self) -> bool:
        return self.verification is Verification.VERIFIED and not self.refutes


class Claim(BaseModel):
    """A single checkable factual assertion an idea depends on.

    `load_bearing` is the important flag: if it is True and the claim fails
    verification, the idea's score is capped. Non-load-bearing claims are
    colour, not structure.
    """

    id: str
    text: str
    load_bearing: bool = True
    search_queries: list[str] = Field(default_factory=list)
    # Literal entity names (proteins, genes, reagents) for exact full-text
    # retrieval; semantic search alone reliably misses these.
    exact_terms: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    searched: bool = False

    @property
    def verified_evidence(self) -> list[Evidence]:
        return [e for e in self.evidence if e.is_grounding]

    @property
    def partial_evidence(self) -> list[Evidence]:
        return [
            e
            for e in self.evidence
            if e.verification is Verification.PARTIAL and not e.refutes
        ]

    @property
    def refuting_evidence(self) -> list[Evidence]:
        """Verified quotes that argue against this claim."""
        return [e for e in self.evidence if e.refutes and e.quote_found]

    @property
    def status(self) -> Verification:
        if self.verified_evidence:
            return Verification.VERIFIED
        if self.partial_evidence:
            return Verification.PARTIAL
        if not self.evidence:
            # "we looked and the corpus has nothing" is a finding; "we never
            # looked" is a bug. Keep them distinguishable in the UI.
            return Verification.NO_EVIDENCE if self.searched else Verification.ERROR
        # evidence was found but none of it held up
        if any(e.verification is Verification.QUOTE_MISMATCH for e in self.evidence):
            return Verification.QUOTE_MISMATCH
        return Verification.UNSUPPORTED

    @property
    def best_support(self) -> SupportLevel | None:
        order = [SupportLevel.ESTABLISHED, SupportLevel.CONTESTED, SupportLevel.SPECULATIVE]
        found = {e.support_level for e in self.verified_evidence}
        for level in order:
            if level in found:
                return level
        return None


# --------------------------------------------------------------------------
# ideas
# --------------------------------------------------------------------------


class IdeaScore(BaseModel):
    """Decomposed confidence. Never collapse this to a single number in the UI.

    `overall` is deliberately *not* a free weighted average: `grounding_cap`
    bounds it from above, so an eloquent ungrounded idea cannot beat a modest
    verified one.
    """

    grounding: float = 0.0  # fraction of load-bearing claims verified
    evidence_strength: float = 0.0  # weighted by established/contested/speculative
    mechanistic_plausibility: float = 0.0  # model judgement
    novelty: float = 0.0
    testability: float = 0.0

    overall: float = 0.0
    grounding_cap: float = 1.0
    cap_applied: bool = False

    recommendation: Recommendation = Recommendation.INVESTIGATE
    rationale: str = ""

    def bar(self, value: float, width: int = 10) -> str:
        filled = int(round(value * width))
        return "█" * filled + "·" * (width - filled)


class Idea(BaseModel):
    id: str
    title: str
    one_liner: str = ""
    mechanism_chain: list[str] = Field(default_factory=list)
    rationale: str = ""
    claims: list[Claim] = Field(default_factory=list)
    key_risk: str = ""
    testability_note: str = ""
    novelty_note: str = ""

    score: IdeaScore | None = None
    status: IdeaStatus = IdeaStatus.PROPOSED
    drop_reason: str = ""
    followup_ids: list[str] = Field(default_factory=list)
    origin: str = "initial"  # "initial" | "followup:<job_id>"

    @property
    def load_bearing_claims(self) -> list[Claim]:
        return [c for c in self.claims if c.load_bearing]

    @property
    def all_evidence(self) -> list[Evidence]:
        return [e for c in self.claims for e in c.evidence]

    @property
    def verified_evidence(self) -> list[Evidence]:
        return [e for e in self.all_evidence if e.is_grounding]

    def unique_citations(self) -> list[Citation]:
        seen: dict[str, Citation] = {}
        for ev in self.verified_evidence:
            seen.setdefault(ev.citation.doc_id, ev.citation)
        return list(seen.values())


# --------------------------------------------------------------------------
# follow-ups + session
# --------------------------------------------------------------------------


class FollowupStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FollowupReport(BaseModel):
    job_id: str
    idea_id: str
    question: str
    status: FollowupStatus = FollowupStatus.RUNNING
    answer: str = ""
    claims: list[Claim] = Field(default_factory=list)
    verdict: str = ""  # e.g. "strengthens" / "weakens" / "inconclusive"
    new_ideas: list[Idea] = Field(default_factory=list)
    error: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    @property
    def elapsed_s(self) -> float:
        end = self.finished_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()


class Turn(BaseModel):
    role: Literal["scientist", "agent"]
    text: str
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Session(BaseModel):
    """Everything the agent knows. Serialised by /save; the audit trail."""

    question: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    transcript: list[Turn] = Field(default_factory=list)
    ideas: list[Idea] = Field(default_factory=list)
    followups: list[FollowupReport] = Field(default_factory=list)

    def live_ideas(self) -> list[Idea]:
        return [i for i in self.ideas if i.status is not IdeaStatus.DROPPED]

    def ranked(self) -> list[Idea]:
        return sorted(
            self.live_ideas(),
            key=lambda i: (i.score.overall if i.score else 0.0),
            reverse=True,
        )

    def by_id(self, idea_id: str) -> Idea | None:
        target = idea_id.strip().lower()
        for idea in self.ideas:
            if idea.id.lower() == target:
                return idea
        return None

    def by_index(self, n: int) -> Idea | None:
        ranked = self.ranked()
        if 1 <= n <= len(ranked):
            return ranked[n - 1]
        return None

    def resolve(self, token: str) -> Idea | None:
        """Accept either a rank number (`3`) or an idea id (`I2`)."""
        token = token.strip()
        if re.fullmatch(r"\d+", token):
            return self.by_index(int(token))
        return self.by_id(token)

    def next_idea_id(self) -> str:
        return f"I{len(self.ideas) + 1}"
