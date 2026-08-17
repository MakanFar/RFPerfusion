# litkb Output Contract

The run directory contains:

- `plan_<slug>.json`: mechanism classes, each with search phrases and mechanism patterns, plus deliberate exclusions. Either agent-written, imported from a curated keyword CSV, or adopted from a `design-brief-007` plan with `plan-adopt`.
- `<slug>_search.json`: every Paperclip set ID, per class and phrase, with per-phrase yield and a coverage summary.
- `<slug>_screen.json`: one record per paper read — mechanisms with their measurable properties, a `has_sequence` flag, where the sequence lives, and named proteins. Papers whose output could not be parsed appear under `failed`, never folded into "no sequence".
- `<slug>_dug.json`: candidate sequences and mutations extracted from the flagged papers.
- `<slug>_artifacts.json`: `artifacts[]` (proto-runnable) and `rejections[]` (everything else, each carrying the check it failed).
- `<slug>_evidence.json`: typed `EvidenceItem[]` per PRD §6.2. `testable_by` starts `"unassessed"` on every freshly drafted item and is resolved against the proto catalogue only once `label` assigns `vocabulary` terms to it.
- `knowledge_base_<slug>.txt`: the human read.
- `manifest_<slug>.json`: sources, limits, every set ID, the workers actually used, artifact paths, counts, and evidence status.

The manifest declares `evidence_status` as `discovery_only_unverified`. A litkb record proves that a reader returned that text from a result set. It does not prove the span was quoted faithfully, that it entails a proposed claim, or that it generalizes beyond the paper's conditions. Sequences carried downstream inherit this status through any cascade and into any shortlist.

## What binding means, and does not

An artifact in `artifacts[]` passed three gates: it is marked `verbatim`, it was re-grepped and `confirmed_in_source` in the document it cites, and at least one proto tool returned `pass` on every constraint check.

That is a **schema check, not a run**. Nothing in `artifacts[]` has been executed, folded, scored, or deployed. Acceptance means a tool would accept the input's molecule type, alphabet, and length — not that the tool produces a useful result on it.

Constraint checks are three-valued. `unknown` never counts as `pass`: a tool whose limit could not be parsed yields `unverified`, and an unverified artifact does not enter `artifacts[]`. Only one tool in the current catalogue (`esmfold-prediction`) carries enough parseable constraints to ever return `runnable`, so the binding surface is far narrower than the catalogue's size suggests.

## Why source confirmation exists

An LLM asked for a sequence will produce a plausible one, and a fabricated sequence passes every alphabet and length check because it is well-formed but not real. Constraint verification confirms well-formedness, never existence. `confirm_in_source` re-greps each extracted value against its own cited document with literal matching, and anything absent is rejected regardless of constraint status.

A mutation rejected this way is reported as a notation mismatch rather than a fabrication, because `Val342Ala` and `V342A` name the same real fact.

## Judgement is the caller's

`litkb` never invents a claim or a support level. `screen` writes the claim it read; `support`, `claim_type`, `evidence_kind`, `confidence` and `vocabulary` start null/empty and are supplied by the calling agent through `label`. `validate` refuses items that are still unlabelled. `support` is `established | contested | speculative`, and nothing speculative may become a hard constraint downstream.

`vocabulary` is a list of term ids from `registry/property_vocabulary.json`, the closed set of properties the proto catalogue can actually address. Assigning it re-resolves `testable_by.tools` and `testable_by.requires_new_evaluator` against `registry/proto_catalog.json`. An empty list is a real, distinct assessment ("nothing in the catalogue measures this") that resolves to `requires_new_evaluator: true`; never labelling `vocabulary` at all leaves the item at `requires_new_evaluator: "unassessed"` indefinitely.

Empty categories, zero-yield phrases, classes with no corpus, and failed extractions are all preserved as rejections. They are search diagnostics and must not be rewritten as evidence that the literature contains nothing.
