---
name: litkb
description: Mine Paperclip full text into typed evidence and proto-runnable sequence artifacts from a design concept. Use when literature findings must be machine-consumable rather than a prose knowledge base — extracting mechanisms with their measurable properties, candidate sequences verified present in their source, and the proto-tools that could actually score them.
---

# litkb — literature to typed, proto-bounded evidence

Discrete subcommands over the `paperclip` corpus. You supply every judgement; the tool supplies plumbing, constraint checking, and citations.

Related but different: `mine-literature-from-concept` runs `paperclip_kb.py` and emits a grep-based knowledge base for human reading. `litkb` reads full text with an LLM and emits typed records for machine consumption. Both are discovery, not verification.

Read [references/output-contract.md](references/output-contract.md) before interpreting or forwarding anything this skill emits.

## Run workflow

1. Confirm `paperclip config` shows an authenticated account. `paperclip login` is an interactive browser flow — report it and stop rather than attempting it.
2. Create a run directory under `litterature_search_from_concept/outputs/` using a UTC timestamp and a short slug. Pass it as `--output-dir`.
3. Get a plan, by whichever route applies:
   - From `design-brief-007`: `plan-adopt <brief-plan> --objective "<question>" --slug <slug>`. The brief's plan is already validated; do not re-plan it.
   - From a curated keyword CSV: `plan-import <csv> <groups.json>`, where groups maps each mechanism class to its rows. An unassigned row is an error, not a silent drop.
   - Written by you: start from `plan-template`.
4. `plan-validate <plan> --probe` before searching. It reports per-phrase yield and warns when one class will swamp the corpus.
5. `search` → `screen` → `dig` → `bind`, then `evidence` → `label` → `validate` → `report`, then `manifest`.
6. Report the coverage summary, what was rejected and why, and the evidence status. Link every emitted file.

## Labelling `testable_by`

`evidence` drafts each item with `testable_by.requires_new_evaluator: "unassessed"` — the label has not run yet, so no claim is made about what can test the claim. This is not a fourth judgement field to fill in directly; it is resolved for you when you assign `vocabulary`.

`label` accepts a `vocabulary` field per item: a list of term ids from `registry/property_vocabulary.json` (a closed 9-term vocabulary — `fold_confidence`, `interface_confidence`, `predicted_error`, `sequence_likelihood`, `structural_validity`, `interface_energetics`, `interface_geometry`, `surface_character`, `design_ranking`). Read the evidence item's `claim` and its drafted `testable_by.properties` (free text lifted from the paper, e.g. "time-resolved EPR"), decide which vocabulary term(s) actually cover what was measured, and pass those ids. `label` then resolves `testable_by.tools` against `registry/proto_catalog.json` and sets `requires_new_evaluator` to one of three values:

- `"unassessed"` — no `vocabulary` has been assigned yet (the draft state; never set this yourself).
- `false` — vocabulary terms were assigned and at least one tool in the catalogue measures them. `testable_by.tools` is non-empty.
- `true` — vocabulary terms were assigned and nothing in the catalogue measures them.

Assigning an **empty** `vocabulary` list is a real, deliberate assessment — "I looked at the catalogue and nothing in it measures this claim" — and resolves to `requires_new_evaluator: true`. That is different from never labelling the item, which leaves it at `"unassessed"` forever. Do not assign vocabulary terms you are not confident actually match what the paper measured just to avoid leaving an item unassessed — an unmatched term raises an error (`vocabulary.UnknownTerm`), and a wrongly-matched term produces a false `tools` binding.

`label` invocation:

```bash
uv run --project . python -m litkb label <evidence.json> <labels.json> \
    --registry ../registry/proto_catalog.json \
    --vocabulary ../registry/property_vocabulary.json
```

`labels.json` is either a bare list or `{"labels": [...]}`, each entry keyed by evidence `id`:

```json
{"labels": [
  {"id": "ev_001", "vocabulary": ["fold_confidence"],
   "claim_type": "mechanism", "support": "established",
   "evidence_kind": "computational", "confidence": 0.8}
]}
```

`--registry` and `--vocabulary` default to `../registry/proto_catalog.json` and `../registry/property_vocabulary.json` (relative to `litterature_search_from_concept/`, the directory these commands run from) and rarely need overriding.

Run from `litterature_search_from_concept/` as `uv run --project . python -m litkb <cmd>`. Every command reads JSON and writes JSON, so any stage can be inspected or retried alone.

## Cost

`screen` and `dig` are LLM passes over full text and spend the user's Paperclip account.

`screen` reads every paper in every set. Use `-n` to cap papers per set for a pilot before committing to a full corpus. `dig` re-reads each set containing at least one flagged paper — paperclip cannot scope a read to specific document ids, so the flagged subset cannot be targeted, and `dig` logs flagged-against-total per set so the waste is visible. Sets with nothing flagged are skipped.

Get approval before a full run on a large corpus.

## Paperclip constraints this skill works around

Verified against 0.7.36. Re-check if that version moves.

- `map` rejects any `-j` concurrency flag: "Parallel map workers are currently limited to GXL testers". The gate is on `-j`, not the worker.
- `--worker structured-extraction` is gated. `exhaustive-extraction` is not, but needs `--claim-schema` and an active repo — repos are opt-in, so ask before creating one. Both passes currently run `quick-reader`.
- Paperclip's launcher is `#!/usr/bin/env python3`; under `uv run` that resolves to a venv without its dependencies and it crashes on import. Strip `VIRTUAL_ENV` before invoking it.
- Exit code 1 means "no matches" — but a crashed paperclip also exits 1 with empty stdout. Never treat exit 1 alone as an empty result.
- `search` has no `--tag` and does not accumulate; `merge` resolves only its first argument. Every set ID must be carried separately.

## Guardrails

- Never present litkb output as evidence. Everything carries `evidence_status: discovery_only_unverified`, and it propagates into anything assembled from it.
- Never treat an artifact in `artifacts[]` as validated. Binding is a schema check against the constraint table; nothing has been executed.
- Never let an `unknown` constraint check count as a pass. An unparsed limit yields `unverified`, which does not enter `artifacts[]`.
- Never accept a sequence that failed source confirmation, whatever its constraint status. A fabricated sequence passes every alphabet and length check.
- Never fill `support` yourself from memory. Read the span and label it, or leave it unlabelled and let `validate` block it.
- Never rewrite an empty category as evidence that the literature contains nothing. Zero-yield phrases and empty classes are diagnostics.
- Regenerate `registry/proto_catalog.json` with `proto-sync` rather than hand-editing it. `measures` is derived by `proto-sync` from `proto-tools output <key>`, not curated — every `proto-sync` run overwrites it. `status` is the only field a human curates by hand afterward (`proto-sync` always writes `needs_calibration`; promoting a tool to `validated` is a deliberate, separate act).
