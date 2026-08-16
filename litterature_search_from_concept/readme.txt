litterature_search_from_concept
===============================

Two literature-mining pipelines live here. They share a corpus (Paperclip) and
a purpose (turn a design concept into a knowledge base), but differ in what
they emit and how much of the reading an LLM does.


1. paperclip_kb.py -- the shipped pipeline
------------------------------------------

Regex-grep mining, wrapped by the `mine-literature-from-concept` skill and fed
by `design-brief-007`.  Emits plan_<slug>.json, knowledge_base_<slug>.txt and
manifest_<slug>.json into a run directory.

From the repository root:

    uv run --with anthropic python litterature_search_from_concept/paperclip_kb.py \
      litterature_search_from_concept/context.txt \
      --slug rfp \
      --output-dir litterature_search_from_concept/outputs/rfp \
      --dry-run

Inspect the generated plan, then reuse that exact plan for the full run:

    uv run --with anthropic python litterature_search_from_concept/paperclip_kb.py \
      litterature_search_from_concept/context.txt \
      --slug rfp \
      --output-dir litterature_search_from_concept/outputs/rfp \
      --plan-file litterature_search_from_concept/outputs/rfp/plan_rfp.json

The knowledge base contains discovery leads, not independently verified claims.


2. litkb/ -- LLM reading bounded by proto-tools
------------------------------------------------

Replaces the regex grep with full-text LLM reading via `paperclip map`, and
keeps only sequences a proto-tools tool can actually accept.  Emits typed
EvidenceItem and ProtoArtifact records rather than grep lines.

Agent-facing usage lives in .claude/skills/litkb/SKILL.md.
Design: docs/superpowers/plans/2026-08-15-litkb-proto-extraction.md

Requires Python >= 3.10 and an authenticated `paperclip` (`paperclip config`
should show Auth OK; `paperclip login` is an interactive browser flow).  No
API keys -- the calling agent does the planning and the judging.

    cd litterature_search_from_concept
    uv run --project . python -m litkb plan-import <keywords.csv> <groups.json> \
        --objective "$(cat context.txt)" --slug rfp -o rfp_plan.json
    uv run --project . python -m litkb search   rfp_plan.json -n 20 -o rfp_search.json
    uv run --project . python -m litkb screen   rfp_search.json -o rfp_screen.json
    uv run --project . python -m litkb dig      rfp_screen.json -o rfp_dug.json
    uv run --project . python -m litkb bind     rfp_dug.json -o rfp_artifacts.json
    uv run --project . python -m litkb evidence rfp_screen.json -o rfp_evidence.json
    uv run --project . python -m litkb report   rfp_evidence.json --search rfp_search.json \
        --artifacts rfp_artifacts.json -o knowledge_base_rfp.txt

`proto-sync` regenerates registry/proto_catalog.json, the constraint table
`bind` checks sequences against.


WHICH ONE
---------

paperclip_kb.py is what `design-brief-007` currently hands its plan to.  litkb
is the newer path and produces machine-consumable artifacts; it accepts the
same brief-emitted plan via `plan-adopt`.  Repointing the skills at litkb is a
team decision that has not been taken.


PAPERCLIP BEHAVIOUR BOTH PIPELINES MUST RESPECT
-----------------------------------------------

Verified against paperclip 0.7.36.  Re-check if that version moves.

  * `search` has no --tag and does not accumulate; each search returns its own
    set, so every set ID must be carried separately.
  * `merge` is broken -- it resolves only its first argument, even for sets
    `results --list` shows.  There is no server-side union.
  * Exit code 1 means "no matches", as in grep -- but a crashed paperclip also
    exits 1 with empty stdout.  Treating every exit 1 as "no matches" silently
    turns a crash into an empty result; litkb/paperclip.py raises instead.
  * Paperclip's launcher is `#!/usr/bin/env python3`.  Under `uv run` that
    resolves to the project venv, which lacks paperclip's dependencies, and it
    crashes on import.  Strip VIRTUAL_ENV before invoking it -- see
    `host_env()` in paperclip_kb.py.
  * `map` rejects any `-j` concurrency flag with "Parallel map workers are
    currently limited to GXL testers".  The gate is on -j, not on the worker.
  * `--worker structured-extraction` is gated; `exhaustive-extraction` is not,
    but requires --claim-schema and an active repo.
  * The grep engine supports lookaround and `-F` fixed-string matching.
