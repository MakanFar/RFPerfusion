"""The 007 design agent.

Six staged calls, each validated in code before the next one builds on it:

    frame ──▶ shards ──┬──▶ literature plan   (concept + plan_<slug>.json)
                       ├──▶ harvest contract  (for the Paperclip agent)
                       └──▶ assembly recipe ──▶ proto brief  (for the Proto agent)

Staging matters for the same reason it does in the sibling agent: one call
producing the whole brief takes minutes and returns a document whose later
sections quietly contradict its earlier ones. Framing is a decision; everything
after it is elaboration of that decision, and each stage is checked against the
one it came from.

Validation is not advisory. A stage that fails `validate.py` is sent back once
with the specific problems listed. Whatever still fails after the repair is
recorded on the brief as `validation_warnings` rather than being dropped — a
flaw stated on the artifact is worth more than a clean-looking artifact.
"""

from __future__ import annotations

import asyncio
from typing import Callable, TypeVar

from pydantic import BaseModel, Field

from .config import SETTINGS
from .llm import LLM
from .models import (
    AssemblyRecipe,
    DesignBrief,
    DesignFrame,
    HarvestContract,
    LiteraturePlan,
    ProtoBrief,
    Shard,
)
from .prompts import (
    ASSEMBLY_SYSTEM,
    FRAME_SYSTEM,
    HARVEST_SYSTEM,
    LITERATURE_SYSTEM,
    PROTO_SYSTEM,
    SHARD_SYSTEM,
)
from .validate import (
    validate_assembly,
    validate_frame,
    validate_harvest,
    validate_literature,
    validate_proto,
    validate_shards,
)

T = TypeVar("T", bound=BaseModel)

Progress = Callable[[str, str], None] | None


class ShardSet(BaseModel):
    """Wrapper: structured-output backends require an object at the top level."""

    shards: list[Shard] = Field(default_factory=list)


def _shard_digest(shards: list[Shard]) -> str:
    rows = []
    for shard in shards:
        rows.append(
            f"  {shard.id} {shard.name} — {shard.role}\n"
            f"      families: {', '.join(shard.candidate_families) or 'n/a'}\n"
            f"      handles:  {', '.join(shard.search_handles) or 'n/a'}\n"
            f"      breaks by: {shard.failure_mode or 'unstated'}"
        )
    return "\n".join(rows)


def _frame_digest(frame: DesignFrame) -> str:
    excluded = "; ".join(
        f"{e.name} ({'unsimulable' if e.unsimulable else 'ruled out'}: {e.reason})"
        for e in frame.excluded_pathways
    )
    return (
        f"TARGET FUNCTION: {frame.target_function}\n"
        f"STIMULUS: {frame.stimulus or 'n/a'}\n"
        f"CHOSEN PATHWAY: {frame.chosen_pathway}\n"
        f"WHY: {frame.pathway_rationale}\n"
        f"CONFIDENCE: {frame.pathway_confidence.value}\n"
        f"EXCLUDED: {excluded or 'none stated'}\n"
        f"CANNOT BE SIMULATED: {frame.simulability_note or 'unstated'}\n"
        f"ASSUMPTIONS: {'; '.join(frame.assumptions) or 'none stated'}"
    )


class DesignAgent:
    def __init__(self, llm: LLM, settings=SETTINGS):
        self.llm = llm
        self.s = settings

    # ------------------------------------------------------------- machinery

    async def _staged(
        self,
        *,
        schema: type[T],
        system: str,
        user: str,
        validator: Callable[[T], list[str]],
        effort: str,
        label: str,
        warnings: list[str],
        progress: Progress = None,
    ) -> T:
        """One stage: generate, validate, repair once, record what survives."""
        if progress:
            progress(label, "started")
        result = await self.llm.structured(
            schema=schema, system=system, user=user, effort=effort
        )
        problems = validator(result)
        if problems:
            if progress:
                progress(label, f"repairing ({len(problems)} problems)")
            try:
                result = await self.llm.repair(
                    schema=schema,
                    system=system,
                    user=user,
                    previous=result,
                    problems=problems,
                    effort=effort,
                )
                problems = validator(result)
            except Exception as exc:  # noqa: BLE001 — repair failure is not fatal
                problems.append(f"repair attempt failed: {type(exc).__name__}: {exc}")
        for problem in problems:
            warnings.append(f"[{label}] {problem}")
        if progress:
            progress(label, "ok" if not problems else f"{len(problems)} warnings")
        return result

    # ------------------------------------------------------------- stage 1

    async def frame(
        self,
        question: str,
        context: str,
        warnings: list[str],
        progress: Progress = None,
    ) -> DesignFrame:
        user = f"DESIGN QUESTION:\n{question}\n"
        if context:
            user += f"\nADDITIONAL CONTEXT:\n{context}\n"
        return await self._staged(
            schema=DesignFrame,
            system=FRAME_SYSTEM,
            user=user,
            validator=validate_frame,
            effort=self.s.frame_effort,
            label="frame",
            warnings=warnings,
            progress=progress,
        )

    # ------------------------------------------------------------- stage 2

    async def shards(
        self,
        question: str,
        frame: DesignFrame,
        warnings: list[str],
        progress: Progress = None,
    ) -> list[Shard]:
        user = f"DESIGN QUESTION:\n{question}\n\n{_frame_digest(frame)}"
        result = await self._staged(
            schema=ShardSet,
            system=SHARD_SYSTEM,
            user=user,
            validator=lambda r: validate_shards(r.shards),
            effort=self.s.shard_effort,
            label="shards",
            warnings=warnings,
            progress=progress,
        )
        return result.shards

    # ------------------------------------------------------------- stage 3

    async def literature(
        self,
        question: str,
        frame: DesignFrame,
        shards: list[Shard],
        warnings: list[str],
        progress: Progress = None,
    ) -> LiteraturePlan:
        user = (
            f"DESIGN QUESTION:\n{question}\n\n{_frame_digest(frame)}\n\n"
            f"SHARDS TO FIND SEQUENCES FOR:\n{_shard_digest(shards)}\n\n"
            "The corpus is biomedical full text (PMC and bioRxiv). Bias every "
            "choice toward papers that publish constructs: the goal is not "
            "topical coverage, it is recovering sequences we can build with."
        )
        return await self._staged(
            schema=LiteraturePlan,
            system=LITERATURE_SYSTEM,
            user=user,
            validator=validate_literature,
            effort=self.s.detail_effort,
            label="literature",
            warnings=warnings,
            progress=progress,
        )

    # ------------------------------------------------------------- stage 4

    async def harvest(
        self,
        frame: DesignFrame,
        shards: list[Shard],
        warnings: list[str],
        progress: Progress = None,
    ) -> HarvestContract:
        user = (
            f"{_frame_digest(frame)}\n\nSHARDS:\n{_shard_digest(shards)}\n\n"
            "Write one rule per shard, in shard-id order."
        )
        return await self._staged(
            schema=HarvestContract,
            system=HARVEST_SYSTEM,
            user=user,
            validator=lambda r: validate_harvest(r, shards),
            effort=self.s.detail_effort,
            label="harvest",
            warnings=warnings,
            progress=progress,
        )

    # ------------------------------------------------------------- stage 5

    async def assembly(
        self,
        frame: DesignFrame,
        shards: list[Shard],
        warnings: list[str],
        progress: Progress = None,
    ) -> AssemblyRecipe:
        user = (
            f"{_frame_digest(frame)}\n\nSHARDS:\n{_shard_digest(shards)}\n\n"
            "Shard ids are already in intended N-to-C order, but reorder them if "
            "the mechanics demand it."
        )
        return await self._staged(
            schema=AssemblyRecipe,
            system=ASSEMBLY_SYSTEM,
            user=user,
            validator=lambda r: validate_assembly(r, shards),
            effort=self.s.detail_effort,
            label="assembly",
            warnings=warnings,
            progress=progress,
        )

    # ------------------------------------------------------------- stage 6

    async def proto(
        self,
        frame: DesignFrame,
        shards: list[Shard],
        assembly: AssemblyRecipe,
        warnings: list[str],
        progress: Progress = None,
    ) -> ProtoBrief:
        fastas = ", ".join(assembly.fasta_outputs) or "(none declared)"
        user = (
            f"{_frame_digest(frame)}\n\nSHARDS:\n{_shard_digest(shards)}\n\n"
            f"CONSTRUCT: {' - '.join(assembly.construct_order)}\n"
            f"FASTA FILES THE CASCADE WILL RECEIVE: {fastas}\n"
            f"VARIANT COUNT: {assembly.combinatorial_plan or 'unstated'}\n\n"
            "Design the cascade that turns those FASTA files into a ranked "
            "shortlist. Cheap gates first."
        )
        return await self._staged(
            schema=ProtoBrief,
            system=PROTO_SYSTEM,
            user=user,
            validator=validate_proto,
            effort=self.s.detail_effort,
            label="proto",
            warnings=warnings,
            progress=progress,
        )

    # ------------------------------------------------------------------ all

    async def build(
        self, question: str, context: str = "", progress: Progress = None
    ) -> DesignBrief:
        warnings: list[str] = []

        frame = await self.frame(question, context, warnings, progress)
        shards = await self.shards(question, frame, warnings, progress)

        async def assembly_then_proto() -> tuple[AssemblyRecipe, ProtoBrief]:
            recipe = await self.assembly(frame, shards, warnings, progress)
            brief = await self.proto(frame, shards, recipe, warnings, progress)
            return recipe, brief

        literature, harvest, (assembly, proto) = await asyncio.gather(
            self.literature(question, frame, shards, warnings, progress),
            self.harvest(frame, shards, warnings, progress),
            assembly_then_proto(),
        )

        return DesignBrief(
            question=question,
            frame=frame,
            shards=shards,
            literature=literature,
            harvest=harvest,
            assembly=assembly,
            proto=proto,
            validation_warnings=warnings,
        )
