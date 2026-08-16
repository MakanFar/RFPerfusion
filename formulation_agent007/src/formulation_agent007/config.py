"""Runtime configuration. Everything tunable lives here.

Env vars are read as `FA7_*` first, then fall back to the sibling agent's
`FA_*` so a shell already configured for `formulation_agent` works unchanged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(f"FA7_{name}") or os.environ.get(f"FA_{name}") or default).strip()


MODEL = _env("MODEL") or None
JUDGE_MODEL = _env("JUDGE_MODEL") or None


@dataclass(frozen=True)
class Settings:
    # Each model call launches one subscription-authenticated headless CLI.
    llm_backend: str = _env("LLM_BACKEND", "codex")
    model: str | None = MODEL
    judge_model: str | None = JUDGE_MODEL

    max_tokens: int = 16_000

    # effort: low | medium | high | xhigh | max
    effort: str = _env("EFFORT", "high")

    # Framing is the highest-judgement call in the system: it picks the
    # transduction pathway everything downstream is built on. Sharding is a
    # close second. The rest is elaboration of decisions already made.
    frame_effort: str = _env("FRAME_EFFORT", "high")
    shard_effort: str = _env("SHARD_EFFORT", "high")
    detail_effort: str = _env("DETAIL_EFFORT", "medium")

    request_timeout: float = float(_env("REQUEST_TIMEOUT", "300"))
    llm_concurrency: int = int(_env("LLM_CONCURRENCY", "2"))

    # paperclip_kb.py's planner contract. Mirrored here so the emitted
    # plan_<slug>.json is accepted by its validate_plan() without editing.
    min_search_phrases: int = 8
    max_search_phrases: int = 14
    min_mechanism_patterns: int = 12
    max_mechanism_patterns: int = 20

    # A cascade with fewer gates than this is not a cascade, it is a guess.
    min_gates: int = 4
    max_gates: int = 10
    min_shards: int = 2
    max_shards: int = 8

    # Sources for the emitted paperclip_kb command. Queried separately: the
    # comma form silently returns PMC-only results instead of unioning.
    sources: str = _env("SOURCES", "pmc,biorxiv")
    papers_per_search: int = int(_env("PAPERS_PER_SEARCH", "500"))

    output_dir: str = _env("OUTPUT_DIR", "briefs")

    def source_list(self) -> list[str]:
        return [s.strip() for s in self.sources.split(",") if s.strip()]


SETTINGS = Settings()
