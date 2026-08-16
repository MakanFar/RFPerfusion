# RFPerfusion — Formulation Agent 007

A scientist poses a protein design question. The agent commits to one build
pathway, decomposes it into swappable **shards**, writes the Paperclip mining
plan that finds real sequences for each shard, specifies how to stitch them,
and hands the downstream Proto agent a fitness cascade with numeric kill
thresholds.

Sibling of [`formulation_agent`](../formulation_agent/README.md), different
question. That one asks *which direction is actually grounded in the
literature*. This one asks *what do we build, what do we go read, and what
number decides whether a design survives*.

```
question ──▶ frame ──▶ shards ──┬──▶ literature plan  ──▶ concept + plan_<slug>.json
                                ├──▶ harvest contract ──▶ Paperclip agent
                                └──▶ assembly ──▶ cascade ──▶ Proto agent
```

## Quick start

```bash
uv run --project formulation_agent007 formulate007-run \
  --question "Design a protein that changes conformation in response to radiofrequency fields" \
  --output-dir formulation_agent007/briefs/rf-switch
```

Interactive:

```bash
uv run --project formulation_agent007 formulate007
```

Backend selection matches the sibling agent — `FA7_LLM_BACKEND` (or the
inherited `FA_LLM_BACKEND`), `codex` by default, `claude` supported. Each model
call launches a fresh headless CLI using saved subscription auth; API-key
environment variables are stripped from the child so an inherited key cannot
silently switch the run to API billing.

Repeat `--context-file <path>` to supply framing context.

## What it writes

| file | consumer |
|---|---|
| `concept_<slug>.txt` | `paperclip_kb.py` positional argument |
| `plan_<slug>.json` | `paperclip_kb.py --plan-file` — skips its own planning call |
| `run_literature.sh` | you; the two mining commands, dry run first |
| `harvest_<slug>.md` | the Paperclip agent — per-shard extraction contract |
| `proto_brief_<slug>.md` | the Proto agent — assembly + cascade runbook |
| `brief-<stamp>.json` | the audit trail |
| `brief-<stamp>.md` | the human read |

Then:

```bash
bash formulation_agent007/briefs/<run>/run_literature.sh
```

## Why the validators are the point

An LLM asked for a computational design plan will produce a fluent, correctly
formatted cascade that thresholds an invented metric on a tool that does not
exist. Prose reads the same either way, so the rules are enforced in
`validate.py`, not by prompting:

**Tool keys must exist.** Every `tool_keys` entry is checked against the
proto-tools catalogue in `catalog.py`. A gate naming `fieldsolver3d` is
rejected and regenerated. The catalogue is a hallucination guard, *not* ground
truth — it will drift, so the emitted runbook tells the Proto agent to confirm
each key with `search_tools` before running anything.

**Metrics must be things the tools emit.** `plddt`, `iptm`, `pdockq2`,
`dg_fold`, `population_fraction` — not "switchiness", not "high confidence".

**The cascade must be ordered cheap-first.** `esmfold` before `boltz2` before
`bioemu`. Enforced by cost tier, because inverting it is the difference between
a run that finishes and one that burns a Modal budget on candidates a 30-second
gate would have killed.

**Some gate must be decisive.** At least one gate must measure the function
that was asked for rather than whether the chain folds. A cascade of
foldability gates tests nothing anyone wanted.

**Linkers must join adjacent shards, in amino acids.** A linker declared
between shards that are not neighbours is a silent assembly bug that produces a
confident, wrong FASTA.

**The plan must satisfy `paperclip_kb.py`.** 8–14 multi-word phrases, 12–20
mechanism patterns, no questions, no single words, no duplicates.
`tests/test_emit.py` validates our emitted plan by importing that script's real
`validate_plan`, so the two contracts cannot drift apart silently.

A stage that fails validation is regenerated once with the specific problems
listed. Whatever still fails is recorded on the brief as `validation_warnings`
and printed into the Proto runbook — a flaw stated on the artifact beats a
clean-looking artifact.

## Method embedded in the prompts

`prompts.py` is where the methodology lives. In one line: **pick a pathway you
can actually score, break it into swappable shards, go find real sequences for
each shard, say exactly how to stitch them, and name the number that kills a
bad design.**

The consequential instruction is the first one. The toolchain has no molecular
dynamics, no field simulation, no quantum chemistry — so any stimulus-response
design must be reduced to a **two-state structural problem**. You do not
simulate the stimulus; you design and score the two end states plus the
population balance between them, and let the hardware or a cofactor supply the
physics. Every frame is required to name the step this leaves unscoreable, and
that sentence is reprinted at the bottom of the Proto runbook.

## Layout

| file | role |
|---|---|
| `models.py` | typed contracts — the only things crossing a boundary |
| `catalog.py` | proto-tools allowlist, cost tiers, metric vocabulary |
| `prompts.py` | the method |
| `validate.py` | the rules the JSON schema cannot express |
| `agent.py` | six staged calls, each validated before the next builds on it |
| `emit.py` | artifacts, one per downstream consumer |
| `report.py` | the human brief |
| `run.py` / `cli.py` | entry points |

## Known limitations

- **The catalogue drifts.** `catalog.py` was transcribed from the proto-tools
  tool list. A key passing validation means it was spelled correctly, not that
  it is deployed on your Modal workspace. Deployment is billable and needs
  explicit approval.
- **Nothing here is verified against literature.** The brief is a plan. Claim
  verification is the sibling agent's job, and sequence verification is the
  harvest step's. The mining pipeline declares its output
  `discovery_only_unverified`; everything built from it inherits that.
- **Thresholds are defensible, not calibrated.** The numbers come from a model
  asked to defend them, not from a benchmark on your target class. Treat the
  first cascade as a starting point and move the thresholds once you have seen
  where real candidates fall.
- **`formulate007` is not a REPL.** A brief is one artifact from one question,
  not an evolving ranking, so the interactive entry point asks, builds, and
  prints. There is no chat, no `/followup`, no web UI.

## Development

```bash
uv run --project formulation_agent007 pytest formulation_agent007/tests -q
```

Tunable via env (`FA7_*`, falling back to `FA_*`): `LLM_BACKEND`, `MODEL`,
`EFFORT`, `FRAME_EFFORT`, `SHARD_EFFORT`, `DETAIL_EFFORT`, `LLM_CONCURRENCY`,
`REQUEST_TIMEOUT`, `SOURCES`, `PAPERS_PER_SEARCH`, `OUTPUT_DIR`.
