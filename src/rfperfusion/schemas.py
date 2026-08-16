"""Frozen data contracts (PRD §6).

These Pydantic models are the ONLY cross-workstream dependency. Every stage is a
pure function `f(typed_in) -> typed_out`, so any workstream can mock an upstream
artifact and keep moving. Do not change these casually once frozen at hour 4.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Support = Literal["established", "contested", "speculative"]
ClaimType = Literal["mechanism", "parameter", "scaffold", "constraint", "negative_result"]


# --------------------------------------------------------------------------- #
# §6.2 EvidenceItem — output of the Literature stage                          #
# --------------------------------------------------------------------------- #
class Quantitative(BaseModel):
    parameter: str
    value: float
    unit: str
    at_wavelength_nm: Optional[float] = None


class Citation(BaseModel):
    doi: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    url: Optional[str] = None
    lines: Optional[str] = None  # paperclip line anchors, e.g. "L45,L120"


class EvidenceItem(BaseModel):
    id: str
    question_id: str  # L1..L4
    claim: str
    claim_type: ClaimType
    quantitative: Optional[Quantitative] = None
    support: Support
    citation: Citation
    evidence_kind: Literal["experimental", "computational", "review", "theoretical"] = "experimental"
    extracted_by: str = "paperclip"
    confidence: float = Field(ge=0.0, le=1.0)


# --------------------------------------------------------------------------- #
# §6.3 Constraint — one Proto/eval callable                                   #
# --------------------------------------------------------------------------- #
class TargetRange(BaseModel):
    min: float
    max: float
    unit: str


class KnownReliability(BaseModel):
    benchmark: str
    mae: Optional[float] = None
    unit: Optional[str] = None
    n: Optional[int] = None


class Constraint(BaseModel):
    id: str
    description: str
    kind: Literal["target_range", "boolean", "threshold", "distance"]
    target: Optional[TargetRange] = None
    evaluator: str  # which proto-tools tool / method implements this
    weight: float = 1.0
    hard: bool = False
    evidence_refs: list[str] = Field(default_factory=list)
    known_reliability: Optional[KnownReliability] = None


# --------------------------------------------------------------------------- #
# §6.1 DesignRecord — orchestrator's single source of truth                   #
# --------------------------------------------------------------------------- #
class RejectedAlternative(BaseModel):
    id: str
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)


class Mechanism(BaseModel):
    id: str
    chain: list[str]
    evidence_refs: list[str] = Field(default_factory=list)
    status: Support = "speculative"
    rejected_alternatives: list[RejectedAlternative] = Field(default_factory=list)


class Scaffold(BaseModel):
    name: str
    length_aa: Optional[int] = None
    uniprot: Optional[str] = None
    sequence: Optional[str] = None
    immutable_regions: list[tuple[int, int]] = Field(default_factory=list)  # 1-indexed, inclusive


class ResearchQuestion(BaseModel):
    id: str  # L1..L4
    question: str
    expected_finding: Optional[str] = None


class HumanDecision(BaseModel):
    at: str
    decision: str
    by: str


class DesignRecord(BaseModel):
    goal: str
    sub_questions: list[ResearchQuestion] = Field(default_factory=list)
    mechanism: Optional[Mechanism] = None
    scaffold: Optional[Scaffold] = None
    constraints: list[Constraint] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    human_decisions: list[HumanDecision] = Field(default_factory=list)

    def evidence_by_question(self, qid: str) -> list[EvidenceItem]:
        return [e for e in self.evidence if e.question_id == qid]


# --------------------------------------------------------------------------- #
# §6.4 Candidate / ScoredCandidate — Design & Eval output                     #
# --------------------------------------------------------------------------- #
class Candidate(BaseModel):
    id: str
    sequence: str
    parent: str = "TlpA_WT"
    mutations: list[str] = Field(default_factory=list)  # e.g. ["L217A", "I224V"]
    generated_by: str = ""


class ScoreEntry(BaseModel):
    value: float
    unit: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    ood: bool = False
    method: str = ""


class Aggregate(BaseModel):
    score: float
    ci_low: float
    ci_high: float


class ScoredCandidate(Candidate):
    scores: dict[str, ScoreEntry] = Field(default_factory=dict)
    aggregate: Optional[Aggregate] = None
    hard_violations: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
