"""Runtime configuration. Everything tunable lives here."""

from __future__ import annotations

import os
from dataclasses import dataclass

# Claude Opus 5: thinking is on by default, so max_tokens bounds thinking +
# visible text together. Keep it generous or structured answers truncate.
MODEL = os.environ.get("FA_MODEL", "claude-opus-5")
JUDGE_MODEL = os.environ.get("FA_JUDGE_MODEL", "claude-sonnet-5")


@dataclass(frozen=True)
class Settings:
    model: str = MODEL
    # The entailment judge is a narrow yes/partial/no call over a short passage.
    # A smaller model keeps it cheap, and independence from the proposing model
    # is the point of the check.
    judge_model: str = JUDGE_MODEL

    max_tokens: int = 16_000
    judge_max_tokens: int = 2_000

    # effort: low | medium | high | xhigh | max
    effort: str = os.environ.get("FA_EFFORT", "high")
    judge_effort: str = "low"

    # Choosing which directions to pursue is the highest-judgement step in the
    # system, so the outline call gets the most effort. Turning a stated
    # direction into checkable claims is mechanical by comparison.
    propose_effort: str = os.environ.get("FA_PROPOSE_EFFORT", "high")
    expand_effort: str = os.environ.get("FA_EXPAND_EFFORT", "medium")

    # Without this the SDK default (10 min, 2 retries) lets a wedged call hang
    # for ~30 minutes with no way to tell it apart from slow work.
    request_timeout: float = float(os.environ.get("FA_REQUEST_TIMEOUT", "240"))

    n_ideas: int = int(os.environ.get("FA_N_IDEAS", "6"))
    papers_per_claim: int = int(os.environ.get("FA_PAPERS_PER_CLAIM", "6"))
    max_claims_per_idea: int = 4

    # Reading is the expensive leg: ~10s per paper, ~60s for a six-paper map.
    # Search returns more than this; only this many are actually read.
    papers_per_map: int = int(os.environ.get("FA_PAPERS_PER_MAP", "4"))
    # Stop searching a claim once this many verified supports are in hand. Each
    # result set is still read in full first, so refutations are never skipped,
    # and a claim that finds nothing exhausts every set.
    evidence_target: int = int(os.environ.get("FA_EVIDENCE_TARGET", "2"))
    # Claims in flight at once. Bounded so they *complete* progressively rather
    # than all finishing at the very end.
    claim_concurrency: int = int(os.environ.get("FA_CLAIM_CONCURRENCY", "4"))

    # These subprocesses sit near 0% CPU waiting on the network, so this cap
    # protects nothing locally — it only throttles throughput.
    paperclip_concurrency: int = int(os.environ.get("FA_PC_CONCURRENCY", "16"))
    llm_concurrency: int = int(os.environ.get("FA_LLM_CONCURRENCY", "6"))

    # Queried one at a time and merged: paperclip's comma form silently
    # returns PMC-only results instead of unioning the corpora.
    sources: str = os.environ.get("FA_SOURCES", "pmc,biorxiv")

    # An idea whose load-bearing claims are unverified cannot score above this.
    ungrounded_ceiling: float = 0.45
    partial_ceiling: float = 0.65

    session_dir: str = os.environ.get("FA_SESSION_DIR", "sessions")

    def source_list(self) -> list[str]:
        return [s.strip() for s in self.sources.split(",") if s.strip()]

    def require_api_key(self) -> str:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise SystemExit(
                "ANTHROPIC_API_KEY is not set.\n\n"
                "The formulation agent needs Claude API access. If you are using "
                "Console credits, create a key in the workspace holding the balance "
                "and run:\n\n"
                "    export ANTHROPIC_API_KEY=sk-ant-...\n"
            )
        return key


SETTINGS = Settings()
