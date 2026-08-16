"""Deterministic orchestrator (PRD §5.1).

Holds only the Design Record and runs the stages in order. This is the DAG in
code — reproducible for the demo. The LLM-driven orchestrator (Agent SDK /
Managed Agents) wraps these same stage functions as worker tools later; the
control flow and data contracts do not change.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schemas import DesignRecord, ScoredCandidate
from .stages import formulate, literature, scaffold, generate, evaluate, rank, report


@dataclass
class RunConfig:
    goal: str | None = None
    live_literature: bool = True     # real Paperclip searches
    gen_method: str = "heuristic"    # "heuristic" (free) | "proto_esm2" (Modal, billable)
    n_candidates: int = 120
    use_modal_eval: bool = False     # real ESMFold/PyRosetta (billable) when True
    top_k: int = 5


def run(cfg: RunConfig) -> tuple[DesignRecord, list[ScoredCandidate]]:
    # Stage 1 — formulate
    record: DesignRecord = formulate.formulate(cfg.goal)

    # Stage 2 — literature (assembles the L1 negative result + photothermal redirect)
    record = literature.run_literature(record, live=cfg.live_literature)

    # Stage 3 — resolve the real TlpA scaffold
    record = scaffold.resolve_scaffold(record)

    # Stage 4 — generate candidate variants
    candidates = generate.generate(record, method=cfg.gen_method, n=cfg.n_candidates)

    # Stage 5 — evaluate against constraints (uncertainty-aware)
    scored = evaluate.evaluate(candidates, record, use_modal=cfg.use_modal_eval)

    # Stage 6 — rank by lower confidence bound; Stage 7 — report
    top = rank.rank(scored, top_k=cfg.top_k)
    report.report(record, top, rank.funnel(candidates, scored))
    return record, top
