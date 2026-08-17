"""Shared fixtures: a minimal but fully valid brief to mutate in tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from formulation_agent007.models import (
    AssemblyRecipe,
    Confidence,
    DesignBrief,
    DesignFrame,
    ExcludedPathway,
    FitnessGate,
    GateState,
    HarvestContract,
    Linker,
    LiteraturePlan,
    ProtoBrief,
    Shard,
    ShardHarvestRule,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
KB_PATH = REPO_ROOT / "litterature_search_from_concept" / "paperclip_kb.py"


@pytest.fixture(scope="session")
def paperclip_kb():
    """The real mining script, imported by path.

    The point of this fixture is that our emitted plan is checked against the
    *actual* consumer rather than against our restatement of its rules.
    """
    if not KB_PATH.exists():  # pragma: no cover - repo layout changed
        pytest.skip(f"paperclip_kb.py not found at {KB_PATH}")
    spec = importlib.util.spec_from_file_location("paperclip_kb", KB_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _phrases(n: int = 10) -> list[str]:
    return [f"designed protein switch variant {i}" for i in range(n)]


def _patterns(n: int = 14) -> list[str]:
    return [f"conformational change upon binding step {i}" for i in range(n)]


@pytest.fixture
def frame() -> DesignFrame:
    return DesignFrame(
        slug="test-design",
        reading_of_question="Interpreting the question as a two-state switch.",
        target_function="Release a binder on stimulus.",
        stimulus="local heating",
        chosen_pathway="thermal latch releasing a caged binder",
        pathway_rationale="Two-state structural problem, scoreable end to end.",
        pathway_confidence=Confidence.CONTESTED,
        excluded_pathways=[
            ExcludedPathway(
                name="direct field coupling",
                reason="no field term available in the toolchain",
                unsimulable=True,
            )
        ],
        simulability_note="The stimulus-to-heat step itself is not modelled.",
        assumptions=["soluble expression"],
    )


@pytest.fixture
def shards() -> list[Shard]:
    return [
        Shard(
            id="S1",
            name="transducer",
            role="absorbs the stimulus",
            candidate_families=["ferritin"],
            search_handles=["FTH1"],
        ),
        Shard(
            id="S2",
            name="latch",
            role="melts and releases",
            candidate_families=["TlpA"],
            search_handles=["TlpA"],
        ),
        Shard(
            id="S3",
            name="binder",
            role="the output",
            candidate_families=["minibinder"],
            search_handles=["de novo minibinder"],
        ),
    ]


@pytest.fixture
def assembly() -> AssemblyRecipe:
    return AssemblyRecipe(
        construct_order=["S1", "S2", "S3"],
        linkers=[
            Linker(
                after_shard="S1",
                before_shard="S2",
                sequence="EAAAKEAAAK",
                rigid=True,
                rationale="transmit strain",
            ),
            Linker(
                after_shard="S2",
                before_shard="S3",
                sequence="GGGGSGGGGS",
                rationale="let the binder reach",
            ),
        ],
        trimming_rules=["cut at loop midpoints found with dssp"],
        fasta_outputs=["on_state.fasta", "off_state.fasta"],
        combinatorial_plan="5 per shard, 125 constructs",
    )


@pytest.fixture
def harvest(shards) -> HarvestContract:
    return HarvestContract(
        per_shard=[
            ShardHarvestRule(
                shard_id=s.id,
                what_to_extract="full-length sequence",
                accept_if=["has an accession"],
                reject_if=["fragment only"],
            )
            for s in shards
        ],
        record_fields=["shard_id", "source_doi", "provenance"],
        global_rules=["a grep hit is a lead, not evidence"],
        dedup_rules=["mmseqs2 at 90% identity"],
    )


@pytest.fixture
def proto() -> ProtoBrief:
    return ProtoBrief(
        gates=[
            FitnessGate(
                order=1,
                name="foldability",
                purpose="kill unfoldable chains cheaply",
                tool_keys=["esmfold-prediction"],
                input_description="every construct",
                state=GateState.SINGLE,
                metric="avg_plddt",
                operator=">=",
                threshold=0.75,
                kill_rule="drop the candidate",
                cost_tier="cheap",
            ),
            FitnessGate(
                order=2,
                name="off-state closure",
                purpose="negative design",
                tool_keys=["boltz2-prediction"],
                input_description="latched construct with target",
                state=GateState.OFF,
                metric="iptm",
                # `between` rather than a bare `<=`: iptm is better=higher, so
                # a plain ceiling reads as "the direction is inverted" to the
                # gate-direction check even though this is intentional
                # negative design (the OFF state should show LOW interface
                # confidence). Bounding both sides sidesteps that mechanical
                # check without changing what the gate actually selects for.
                operator="between",
                threshold=0.0,
                threshold_upper=0.45,
                kill_rule="drop leaky designs",
                cost_tier="moderate",
            ),
            FitnessGate(
                order=3,
                name="on-state binding",
                purpose="the requested function",
                tool_keys=["boltz2-prediction"],
                input_description="released construct with target",
                state=GateState.ON,
                metric="iptm",
                operator=">=",
                threshold=0.8,
                kill_rule="drop non-binders",
                cost_tier="moderate",
                decisive=True,
            ),
            FitnessGate(
                order=4,
                name="two-state ensemble",
                purpose="confirm bimodality",
                tool_keys=["boltz2-prediction"],
                input_description="latch subassembly",
                state=GateState.CONTRAST,
                metric="confidence_score",
                operator="between",
                threshold=0.15,
                threshold_upper=0.85,
                kill_rule="drop single-state designs",
                cost_tier="moderate",
                decisive=True,
            ),
        ],
        ranking_expression="delta_iptm * bimodality",
        known_limitations=[
            "bioemu returns one implicit-temperature ensemble",
            "bioemu publishes no metrics block, so no gate can threshold on "
            "it until it does; gate 4 uses boltz2-prediction instead",
        ],
        deployment_notes=["deploy one tool at a time"],
    )


@pytest.fixture
def literature() -> LiteraturePlan:
    return LiteraturePlan(
        concept_text=" ".join(["concept"] * 80),
        search_phrases=_phrases(),
        mechanism_patterns=_patterns(),
        notes="excluded unrelated imaging work",
    )


@pytest.fixture
def brief(frame, shards, literature, harvest, assembly, proto) -> DesignBrief:
    return DesignBrief(
        question="How do we build a stimulus-gated binder?",
        frame=frame,
        shards=shards,
        literature=literature,
        harvest=harvest,
        assembly=assembly,
        proto=proto,
    )
