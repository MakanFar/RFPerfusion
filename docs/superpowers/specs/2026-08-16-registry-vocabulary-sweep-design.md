# Design — Evaluator registry, property vocabulary, and repo sweep

| | |
|---|---|
| **Date** | 2026-08-16 |
| **Status** | Approved for planning |
| **Scope** | `litterature_search_from_concept/litkb`, `registry/`, `formulation_agent007`, CI, repo hygiene |
| **Relationship to PRDs** | Implements `PRD-framework.md` §6 (evaluator registry) more faithfully. No principle changes. |

## 1. Problem

Five defects, sequenced from most to least consequential. Each figure below was
measured against the tree at `e20abee`, not estimated.

### 1.1 `requires_new_evaluator` is a check that cannot return false

`registry/proto_catalog.json` carries `measures: []` for **140/140** tools.
`litkb/proto.py:resolve_properties` intersects an evidence item's measurable
properties against `measures`, so it returns `requires_new_evaluator: true`
unconditionally. In the committed run
`outputs/20260816T043704Z-rfp/evidence_rfp.json`, all **45/45** items report
`true`.

Filling `measures` alone would not fix this. The two sides speak different
languages:

```
evidence properties (n=158, 156 unique)   tool metrics
  "reorganization energy"                   avg_plddt
  "time-resolved EPR"                       ptm
  "radical pair lifetime"                   iptm
  "transient absorption spectra"            perplexity
```

Set intersection over free text can never match. The substantive answer today is
mostly *correct* — proto-tools genuinely cannot measure time-resolved EPR — but
it is correct by construction rather than by inspection. This is the failure
mode `biophysical_triage_pipeline/README.md` already names for the pLDDT gate: a
gate that never fires while appearing to work.

### 1.2 Constraint parsing reads prose when structured data exists

`parse_input_doc` regex-scrapes `proto-tools input <key>`. Coverage:

| field | parsed | of |
|---|---:|---:|
| `molecules` | 7 | 140 |
| `max_length` | 5 | 140 |
| `input_kind` | 102 | 140 |

The parser is not wrong — `esmfold-prediction` resolves all four constraints
correctly — it just matches two prose phrasings out of many. Consequence in the
committed run: each artifact binds to 1 tool and leaves 97 `unverified`. Since
unknown never passes (correct, and unchanged), the funnel is choked by parser
coverage rather than by real constraints.

`proto-tools schema <key>` returns an actual JSON Schema (`inputs`, `config`,
`output`) and was never used.

### 1.3 `formulation_agent007` validates gates against metric names that do not exist

`catalog.py` hand-types `PROTO_METRICS`. It contains `plddt` and `mean_plddt`;
the catalogue emits `avg_plddt`, and `mean_plddt` is emitted by no tool at all.
The 13 real plddt-family names (`avg_iplddt`, `complex_plddt`,
`avg_binder_plddt`, …) are absent from the frozenset.

`validate.py` therefore passes a gate thresholding a metric the named tool does
not emit — precisely the hallucination the validator exists to catch. README
claims "Metrics must be things the tools emit"; the check is against a hand-typed
list that has drifted.

### 1.4 CI runs one suite of four

`.github/workflows/tests.yml` runs litkb's 119 tests. The other three projects —
`formulation_agent007` (44), `formulation_agent` (24 offline + 4 live),
`biophysical_triage_pipeline` (16) — never run on a pull request. All 203 pass
locally as of this date.

### 1.5 Hygiene

- `_to_delete/git-index.lock` and `_to_delete/git-index.lock2` are tracked in
  git. Both are zero bytes.
- `litterature_search_from_concept/readme.txt` points at
  `docs/superpowers/specs/2026-08-15-litkb-proto-extraction-design.md`, which
  does not exist. The file is at
  `docs/superpowers/plans/2026-08-15-litkb-proto-extraction.md`.
- The brief hands off to `paperclip_kb.py` while `litkb` — the typed pipeline —
  is reachable only by hand via `plan-adopt`. `readme.txt` records this as a team
  decision not yet taken. It is taken here: **litkb becomes the default handoff
  and `paperclip_kb.py` is retained** as the cheap, no-LLM-quota path.

## 2. Non-goals

- **Calibration.** `status: needs_calibration` stays on every tool. Knowing a
  tool emits `avg_plddt` is a capability fact, not an accuracy claim. Framework
  §6's bar on ranking with uncalibrated tools is unaffected.
- **Making the committed RF run look better.** Most of its 45 items will remain
  `requires_new_evaluator: true` after this work, because EPR and transient
  absorption spectroscopy are genuinely outside the catalogue. The gain is that
  the answer becomes earned. Any design that lights up that run is wrong.
- **Modal-backed generation**, benchmark calibration of the 007 thresholds, and
  biophys T2. Unchanged and still open.
- **Retiring `paperclip_kb.py`.** It keeps the no-LLM-read-limit path the README
  advertises.

## 3. Design

### 3.1 `litkb proto-sync` derives the registry from proto-tools

Two sources replace one:

| source | supplies |
|---|---|
| `proto-tools schema <key>` | `input_kind`, `molecules`, `alphabet`, declared length bounds |
| `proto-tools output <key>` | `measures` — parsed from the rendered `metric_spec` table |
| `proto-tools input <key>` | fallback only, for caps stated in prose Notes (e.g. ESMFold's 2,400-residue cap, which is not a schema constraint) |

`constraint_source` becomes a list recording which source supplied the entry
(`["schema"]`, `["schema","docstring"]`), so a thin entry is traceable to why.
This changes the field's type from string to list, so the registry gains a
top-level `schema_version: 2`. A reader encountering version 1 must fail loudly
rather than coerce — a silently mis-read constraint is the fail-open behaviour
this whole design exists to prevent.

Registry entry shape:

```json
{
  "key": "esmfold-prediction",
  "category": "structure_prediction",
  "uses_gpu": true,
  "input_kind": "complex",
  "molecules": ["protein"],
  "alphabet": "ACDEFGHIKLMNPQRSTVWYXBZUO",
  "max_length": 2400,
  "constraint_source": ["schema", "docstring"],
  "status": "needs_calibration",
  "measures": [
    {"metric": "avg_plddt", "type": "float", "range": [0.0, 1.0],
     "availability": "always", "better": "higher", "primary": true},
    {"metric": "avg_pae", "type": "float", "range": [0.0, null],
     "availability": "depends on model output", "better": "lower",
     "primary": false}
  ]
}
```

`range` uses `null` for an unbounded end (`[0.0, inf]` → `[0.0, null]`), since
JSON has no infinity literal.

**Measured coverage of the metrics source**, across all 140 tools:

| | |
|---|---:|
| tools publishing a metrics block | 48 / 140 |
| metric rows | 211 |
| distinct metric names | 99 |
| tools declaring a `*primary` | 33 |

The remaining 92 are generators, retrievers, aligners and annotators that
measure nothing. For them `measures: []` is the correct answer, and it becomes a
derived fact rather than an unfilled column.

**The row parser must handle three observed variants**, not only the ESMFold
shape:

```
avg_plddt      float, range [0.0, 1.0], always, better=higher  *primary
pae            list[list[float]], range [0.0, inf], when include_pae_matrix=True, better=lower
dSASA          float, range [0.0, inf], Å^2, better=context
```

That is: `better=` takes `higher | lower | context`; field three is either an
availability phrase or a unit; and rows may carry indented continuation lines
that are not themselves rows.

**Unparsed in-block lines are recorded, not dropped.** The registry gains a
top-level `parse_failures: [{key, line}]`. Coverage stays auditable and the
repo's "rejections ship" rule holds. A silent drop here would recreate exactly
the invisible-gap problem this work exists to fix.

### 3.2 A closed property vocabulary bridges evidence to metrics

New file `registry/property_vocabulary.json`, versioned:

```json
{
  "version": 1,
  "terms": [
    {"id": "fold_confidence",
     "definition": "Model confidence that the predicted monomer fold is correct.",
     "metrics": ["avg_plddt", "plddt", "complex_plddt", "avg_ss_plddt", "ptm"]},
    {"id": "interface_confidence",
     "definition": "Model confidence in a predicted inter-chain interface.",
     "metrics": ["iptm", "chain_pair_iptm", "pdockq2", "ipsae", "avg_iplddt"]},
    {"id": "sequence_likelihood",
     "definition": "How probable the sequence is under a protein language model.",
     "metrics": ["perplexity", "log_likelihood", "avg_log_likelihood"]}
  ]
}
```

Roughly twelve terms, each derived from metrics the 48 metric-bearing tools
actually emit. Full term list is an implementation detail of the plan; the
contract is the invariant below.

**Invariant — every term resolves to at least one metric present in the
generated registry.** A term that resolves to nothing is a bug and fails a test.
This is what stops the vocabulary rotting as the catalogue moves, and it is why
the vocabulary contains *only* addressable properties. A property with no
evaluator is expressed by assigning **no** term, not by inventing an unbacked
one.

**Assignment stays with the agent.** `litkb label` gains a `vocabulary` field.
`contracts.py` already draws this line — the tool drafts, the agent judges — and
this respects it. Assigning zero terms is legitimate and will be the common case.

`testable_by` keeps free-text `properties` verbatim and adds `vocabulary`:

```json
"testable_by": {
  "properties": ["radical pair lifetime"],
  "vocabulary": [],
  "tools": [],
  "requires_new_evaluator": true
}
```

**`requires_new_evaluator` becomes three-valued:**

| value | meaning |
|---|---|
| `false` | terms assigned, and the registry lists tools measuring them |
| `true` | terms assessed, and nothing in the catalogue measures them |
| `"unassessed"` | `label` has not run; no claim is made |

Today's unconditional `true` becomes `"unassessed"` on a freshly drafted item.
This mirrors `check()`'s three-valued `unknown`, which never counts as pass: an
unmade assessment must not read as a completed one.

`resolve_properties` is rewritten to take vocabulary ids rather than free text
and to return the three-valued result.

**Migration.** Committed runs under `outputs/` are historical records and are not
rewritten. Evidence and manifest outputs gain `schema_version: 2` so a consumer
can tell which contract a file follows.

### 3.3 `formulation_agent007` reads the generated metric vocabulary

`catalog.py` drops the hand-typed `PROTO_METRICS` frozenset and loads a
committed snapshot, `registry/proto_metrics.json`, generated by the same
`proto-sync` pass. The snapshot keeps 007 free of any runtime dependency on the
`proto` project, preserving offline tests.

`validate.py` gains a check it cannot perform today: **a gate's comparison
direction must agree with the metric's `better=`.** `avg_pae >= 0.8` is rejected
as inverted, because `avg_pae` is `better=lower`. `better=context` metrics are
exempt — direction is not decidable for them.

A staleness test compares the snapshot against the live catalogue. It is marked
so it is skipped offline and never breaks CI.

### 3.4 litkb becomes the default handoff

`emit.py` writes `run_literature.sh` with two labelled blocks:

1. **Default — litkb**: `plan-adopt → search → screen → dig → bind → evidence →
   report → manifest`, producing typed records.
2. **Alternative — paperclip_kb.py**: the existing two commands, labelled as the
   grep path with no LLM read quota.

`KB_SCRIPT` is joined by a litkb invocation constant rather than replaced, so the
grep path stays a first-class option.

**The mirrored `validate_plan` collapses.** `contracts.py` mirrors
`paperclip_kb.py`'s three-key check and documents the reason: avoiding an import
dependency on a sibling script. The fix honours that reason rather than
overriding it — the shared check moves into a small dependency-free module both
import. `test_emit.py` continues to import the real validator, so the anti-drift
guarantee is preserved.

### 3.5 Hygiene and CI

- `git rm -r _to_delete/`.
- Repoint the `readme.txt` design reference at
  `docs/superpowers/plans/2026-08-15-litkb-proto-extraction.md`.
- `tests.yml` becomes a matrix over the four projects. `formulation_agent` runs
  with `-m "not live"`; the other three run whole. Expected total: 203 tests.

## 4. Testing

All offline. Paperclip and proto-tools stay monkeypatched, matching the existing
suite's contract.

| area | cases |
|---|---|
| metrics parser | all three row variants; a tool with no metrics block; a continuation line; an unparseable row landing in `parse_failures` |
| schema constraint parsing | schema-supplied molecules/alphabet; prose-only cap fallback; a tool supplying neither stays `unknown` |
| vocabulary | every term resolves to ≥1 registry metric; unknown term id rejected by `label` |
| `resolve_properties` | all three `requires_new_evaluator` values |
| `007` | snapshot staleness (marked, skipped offline); direction agreement, incl. `better=context` exemption |
| regression | `check()` still never treats `unknown` as pass |

Fixtures are captured from real `proto-tools output` text, committed verbatim, so
the parser is tested against the format it must actually survive.

## 5. Risks

- **The registry will look sparse.** 92/140 tools with `measures: []` reads as
  incomplete. The file documents that this is derived and correct for tools that
  measure nothing.
- **The vocabulary is a judgement call.** Twelve terms will not partition the
  space cleanly forever. It is versioned in-file and guarded by the
  resolves-to-a-metric invariant.
- **`proto-sync` is not offline.** It needs the proto venv. The registry stays
  committed; CI validates that the committed file parses and satisfies the
  vocabulary invariant, not that it is fresh.
- **Re-labelling cost.** Existing drafted evidence reads `"unassessed"` until
  `label` runs. This is intended, and cheap — `label` is an agent call, not a
  paperclip read.

## 6. Sequencing

Ordered so each step is independently verifiable and nothing depends on a later
step.

1. Hygiene and CI (§3.5) — mechanical, makes every later step verifiable on PR.
2. `proto-sync` rewrite and registry regeneration (§3.1).
3. Property vocabulary and three-valued `resolve_properties` (§3.2).
4. 007 snapshot and direction check (§3.3).
5. litkb default handoff and shared `validate_plan` (§3.4).
