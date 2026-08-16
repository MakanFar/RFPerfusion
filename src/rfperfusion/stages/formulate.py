"""Formulation stage (PRD §5.2). Free-text goal -> DesignRecord v0 with the
constraint skeleton and the fixed sub-questions. No literature values yet."""

from __future__ import annotations

from .. import config
from ..schemas import DesignRecord, Scaffold


def formulate(goal: str | None = None) -> DesignRecord:
    goal = goal or config.GOAL
    return DesignRecord(
        goal=goal,
        sub_questions=list(config.SUB_QUESTIONS),
        scaffold=Scaffold(
            name=config.SCAFFOLD_NAME,
            length_aa=config.SCAFFOLD_LENGTH_AA_HINT,
            immutable_regions=[(1, config.DBD_END_HINT)],  # provisional; confirmed by scaffold stage
        ),
        constraints=config.default_constraint_set(),
    )
