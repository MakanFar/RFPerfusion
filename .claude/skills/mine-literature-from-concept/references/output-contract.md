# Literature Mining Output Contract

The run directory contains:

- `plan_<slug>.json`: reviewed search phrases, mechanism patterns, and planner notes.
- `knowledge_base_<slug>.txt`: deduplicated Paperclip grep lines grouped into mechanism, sequence, database identifier, mutation, and quantitative categories.
- `manifest_<slug>.json`: model, sources, limits, Paperclip set ID, artifact paths, and evidence status.

The manifest must declare `evidence_status` as `discovery_only_unverified`. A knowledge-base line proves only that text matching a pattern was returned from the result set. It does not prove that the line was quoted faithfully from the intended document, entails a proposed claim, or generalizes beyond the paper's experimental conditions.

Use the Paperclip set ID to reopen results or verify a candidate in its source. Preserve empty categories: they are useful search diagnostics and must not be rewritten as evidence that the literature contains nothing.
