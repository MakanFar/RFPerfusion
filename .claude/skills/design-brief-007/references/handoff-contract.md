# Design Brief Output Contract

The output directory contains:

- `brief-<stamp>.json`: the full typed brief — frame, shards, literature plan, harvest contract, assembly recipe, fitness cascade, and `validation_warnings`. The audit trail.
- `brief-<stamp>.md`: the same content as a human read.
- `concept_<slug>.txt`: the concept file, the positional argument to `paperclip_kb.py`.
- `plan_<slug>.json`: reviewed search phrases, mechanism patterns, and notes. Already validated against that script's `validate_plan`; pass it with `--plan-file` so no planning call is made and no `ANTHROPIC_API_KEY` is needed.
- `run_literature.sh`: the dry run and the real run, in order, from the repository root.
- `harvest_<slug>.md`: the per-shard extraction contract for the Paperclip agent.
- `proto_brief_<slug>.md`: the assembly recipe and fitness cascade for the Proto agent.

## What the brief is and is not

A brief is a plan, not a finding. Nothing in it has been retrieved, quoted, or verified against a source. A gate passing validation means its tool key was spelled correctly and its metric is one the tool emits — not that the tool is deployed, and not that the threshold is right for this target class.

Every cascade gate carries a tool key, a metric, an operator, and a number, so the Proto agent can evaluate it without interpreting prose. Gates marked `decisive` measure the requested function rather than generic foldability; a cascade without one tests nothing the user asked about. Gates with `state: off` are negative design — the inactive state must fail — and most candidates die there.

`validation_warnings` are problems that survived one repair attempt. They are recorded rather than hidden, and they are reprinted at the end of the Proto runbook. Read them before forwarding anything.

## Inherited status

Sequences harvested from the mining run carry `evidence_status: discovery_only_unverified` from its manifest. Everything assembled from them inherits it, through the cascade and into any shortlist. A computational score is not experimental evidence and not a calibrated ranking signal: the cascade orders candidates for synthesis, it does not predict that any of them work.
