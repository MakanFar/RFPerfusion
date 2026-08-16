"""Typed contracts for the design brief.

Design rule that motivates this file: every downstream consumer is an *agent*,
not a person. The Paperclip agent needs patterns it can grep; the Proto agent
needs tool keys, metrics and numbers it can threshold on. So nothing here is
allowed to be prose where it could be a field.

Note the absence of `max_length` on any model. Structured-output backends
strip string `maxLength` and validate client-side afterwards, so the model
never learns the limit and a completed, expensive generation gets discarded for
exceeding it. Length guidance goes in the prompt.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

AA_ALPHABET = set("ACDEFGHIKLMNPQRSTVWY")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class Confidence(str, Enum):
    ESTABLISHED = "established"
    CONTESTED = "contested"
    SPECULATIVE = "speculative"


class GateState(str, Enum):
    """Which structural state a gate is scoring.

    SINGLE   — one chain, one state (foldability, expressibility)
    ON       — the functional/active state
    OFF      — the inactive state; usually a *negative* design criterion
    CONTRAST — the difference between ON and OFF; this is where function lives
    """

    SINGLE = "single"
    ON = "on"
    OFF = "off"
    CONTRAST = "contrast"


# --------------------------------------------------------------------------
# stage 1 — frame
# --------------------------------------------------------------------------


class ExcludedPathway(BaseModel):
    """A route considered and dropped. Kept because the reason is the content.

    Most of these are dropped for being unsimulable with the available tools
    rather than for being wrong, and that distinction decides whether the idea
    comes back when the toolchain grows.
    """

    name: str
    reason: str
    unsimulable: bool = False


class DesignFrame(BaseModel):
    slug: str
    reading_of_question: str
    target_function: str
    stimulus: str = ""
    chosen_pathway: str
    pathway_rationale: str
    pathway_confidence: Confidence = Confidence.SPECULATIVE
    excluded_pathways: list[ExcludedPathway] = Field(default_factory=list)
    # The honest statement of what the toolchain cannot do for this design.
    simulability_note: str = ""
    assumptions: list[str] = Field(default_factory=list)

    def slug_ok(self) -> bool:
        return bool(SLUG_RE.fullmatch(self.slug))


# --------------------------------------------------------------------------
# stage 2 — shards
# --------------------------------------------------------------------------


class Shard(BaseModel):
    """One independently-sourced module of the final construct.

    The shard is the unit of literature harvesting: one shard, one set of
    candidate sequences, swappable without redesigning its neighbours.
    """

    id: str  # S1, S2, ...
    name: str
    role: str
    why_needed: str = ""
    candidate_families: list[str] = Field(default_factory=list)
    # Literal strings a relevant paper would contain — protein names, mutant
    # designations, technique names. Matched verbatim, so no descriptions.
    search_handles: list[str] = Field(default_factory=list)
    sequence_source_hint: str = ""
    failure_mode: str = ""
    required: bool = True


# --------------------------------------------------------------------------
# stage 3 — literature plan (feeds paperclip_kb.py)
# --------------------------------------------------------------------------


class LiteraturePlan(BaseModel):
    """Drop-in input for `litterature_search_from_concept/paperclip_kb.py`.

    `concept_text` becomes the concept file. `search_phrases` /
    `mechanism_patterns` / `notes` are written out as `plan_<slug>.json`, whose
    shape is dictated by that script's `validate_plan()` — 8-14 phrases,
    12-20 patterns, a notes string. Emitting a reviewed plan lets the run skip
    the script's own planning call entirely via `--plan-file`.
    """

    concept_text: str
    search_phrases: list[str] = Field(default_factory=list)
    mechanism_patterns: list[str] = Field(default_factory=list)
    notes: str = ""

    def plan_payload(self) -> dict:
        """Exactly the three keys paperclip_kb.validate_plan requires."""
        return {
            "search_phrases": list(self.search_phrases),
            "mechanism_patterns": list(self.mechanism_patterns),
            "notes": self.notes,
        }


# --------------------------------------------------------------------------
# stage 4 — harvest contract (instructions to the Paperclip agent)
# --------------------------------------------------------------------------


class ShardHarvestRule(BaseModel):
    shard_id: str
    what_to_extract: str
    accept_if: list[str] = Field(default_factory=list)
    reject_if: list[str] = Field(default_factory=list)
    expected_length_range: str = ""


class HarvestContract(BaseModel):
    per_shard: list[ShardHarvestRule] = Field(default_factory=list)
    record_fields: list[str] = Field(default_factory=list)
    global_rules: list[str] = Field(default_factory=list)
    dedup_rules: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# stage 5 — assembly recipe
# --------------------------------------------------------------------------


class Linker(BaseModel):
    after_shard: str
    before_shard: str
    sequence: str
    rigid: bool = False
    rationale: str = ""

    def sequence_ok(self) -> bool:
        seq = self.sequence.strip().upper()
        return bool(seq) and set(seq) <= AA_ALPHABET


class AssemblyRecipe(BaseModel):
    """How the harvested shards become one construct.

    `construct_order` is N-to-C. `linkers` must join consecutive pairs in that
    order — checked in validate.py, because a linker declared between shards
    that are not neighbours is a silent assembly bug.
    """

    construct_order: list[str] = Field(default_factory=list)
    linkers: list[Linker] = Field(default_factory=list)
    trimming_rules: list[str] = Field(default_factory=list)
    expression_tags: list[str] = Field(default_factory=list)
    fasta_outputs: list[str] = Field(default_factory=list)
    combinatorial_plan: str = ""
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# stage 6 — fitness cascade (instructions to the Proto agent)
# --------------------------------------------------------------------------


class FitnessGate(BaseModel):
    """One pass/fail checkpoint in the design loop.

    A gate without a number is an opinion. `metric`, `operator` and `threshold`
    are mandatory and constrained so the Proto agent can evaluate the gate
    without interpreting prose.
    """

    order: int
    name: str
    purpose: str
    tool_keys: list[str] = Field(default_factory=list)
    input_description: str
    state: GateState = GateState.SINGLE
    metric: str
    operator: Literal[">=", "<=", ">", "<", "between"]
    threshold: float
    threshold_upper: float | None = None
    unit: str = ""
    kill_rule: str
    on_failure: str = ""
    cost_tier: Literal["cheap", "moderate", "expensive"] = "cheap"
    # True for the gate(s) that measure the *requested function* rather than
    # generic foldability. A cascade with none of these tests nothing.
    decisive: bool = False
    caveat: str = ""

    def condition(self) -> str:
        if self.operator == "between":
            hi = self.threshold_upper if self.threshold_upper is not None else float("inf")
            return f"{self.threshold:g} <= {self.metric} <= {hi:g} {self.unit}".strip()
        return f"{self.metric} {self.operator} {self.threshold:g} {self.unit}".strip()


class ProtoBrief(BaseModel):
    gates: list[FitnessGate] = Field(default_factory=list)
    ranking_expression: str = ""
    ranking_rationale: str = ""
    deployment_notes: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)

    def decisive_gates(self) -> list[FitnessGate]:
        return [g for g in self.gates if g.decisive]

    def ordered(self) -> list[FitnessGate]:
        return sorted(self.gates, key=lambda g: g.order)


# --------------------------------------------------------------------------
# the brief
# --------------------------------------------------------------------------


class DesignBrief(BaseModel):
    """Everything the run produced. Serialised as the audit trail."""

    question: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    frame: DesignFrame
    shards: list[Shard] = Field(default_factory=list)
    literature: LiteraturePlan
    harvest: HarvestContract
    assembly: AssemblyRecipe
    proto: ProtoBrief
    validation_warnings: list[str] = Field(default_factory=list)

    @property
    def slug(self) -> str:
        return self.frame.slug

    def shard_by_id(self, shard_id: str) -> Shard | None:
        for shard in self.shards:
            if shard.id.upper() == shard_id.strip().upper():
                return shard
        return None

    def required_shards(self) -> list[Shard]:
        return [s for s in self.shards if s.required]
