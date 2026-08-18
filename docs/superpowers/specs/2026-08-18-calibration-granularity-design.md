# Design — Per-metric calibration and its propagation

| | |
|---|---|
| **Date** | 2026-08-18 |
| **Status** | **ROUGH DRAFT — not approved, not planned** |
| **Scope** | `registry/`, `litterature_search_from_concept/litkb`, `formulation_agent007` |
| **Relationship to PRDs** | Implements `PRD-framework.md` §6 bullets 1, 3 and 4, which currently have no representation anywhere. No principle changes. |
| **Follows** | `2026-08-16-registry-vocabulary-sweep-design.md`, whose §2 listed calibration as a non-goal. |

## 1. Problem

Durability landed in `f758275`: curated status lives in `registry/calibration.json`
and survives `proto-sync`. Nothing else about §6 exists. Figures below are
measured against the tree at `f758275`, not estimated.

### 1.1 `status` is per-tool; reliability is per-metric

The curated unit is a tool. The thing that has an error bar is a metric.

| | |
|---|---:|
| tools catalogued | 140 |
| tools emitting any metric | 48 |
| **(tool, metric) rows — the real calibration unit** | **311** |
| distinct metric names | 170 |
| rows flagged `primary` | 42 |
| tools declaring a `primary` | 42 (exactly one each) |

`boltz2-prediction` emits `iptm`, `avg_pae` and others from one model. Its
ipTM may be well characterised on a docking benchmark while its PAE is not.
A single tool-level string cannot say that, so today the only expressible
answers are "trust all of it" or "trust none of it". Both are wrong.

The `measures` rows already carry `metric`, `type`, `range`, `unit`,
`availability`, `better` and `primary` — the granularity is already there.
Calibration is the one property of a metric kept somewhere else, at the wrong
resolution.

### 1.2 `requires_new_evaluator: false` reads as "rankable" and is not

Newly load-bearing: before `31a0a0a` this value was unreachable, so the
ambiguity never surfaced. In the committed binder run, `ev_001` reports:

```json
"testable_by": {
  "vocabulary": ["fold_confidence", "predicted_error", "interface_energetics"],
  "tools": ["alphafold2-prediction", "esmfold-prediction", "boltz2-prediction", "..."],
  "requires_new_evaluator": false
}
```

Fifteen tools, every one `needs_calibration`. §6 permits all fifteen to run
and forbids all fifteen from ranking, and nothing in the record says so. A
downstream agent reading `false` plus a 15-tool list has been told, in effect,
"this claim is covered".

`resolve_properties` (`litkb/proto.py:449`) selects on metric membership alone
and never consults `status`. That is correct for the question it answers — *what
can measure this* — and the artifact simply has no field for the other question.

### 1.3 `formulation_agent007` is calibration-blind

`registry/proto_metrics.json` (schema 3) carries `tool_keys`, `metrics`,
`categories`. No status, no error. `catalog.py` mentions calibration nowhere.

So `validate.py` can reject a gate whose direction contradicts `better=`
(landed in the sweep) but cannot reject `avg_plddt >= 0.85` on a tool whose
pLDDT has never been characterised, nor a threshold quoted to a precision the
evaluator cannot resolve. §6 bullet 3 — *no claimed design margin finer than the
evaluator's measured error* — is stated as "enforced in the reporting layer"
and is enforced nowhere.

### 1.4 Three of §6's four bullets have no field

Grepping the tree for `benchmark`, `reliability`, `measured_error`,
`uncertainty`, `applicability` returns zero hits in code or JSON. Only bullet 2
(may run, may not rank) is represented, and only as a boolean consulted in one
function.

## 2. Non-goals

- **Calibrating anything.** Producing a measured error needs Modal credentials,
  a held-out benchmark and ground truth. This design builds the place to put
  the answer and the rules that follow from it. The shipped file still promotes
  nothing.
- **Changing what `validated` means.** It continues to mean measured reliability
  on a held-out benchmark.
- **Ranking policy.** How a calibrated score orders candidates is L3's problem.
- **Re-labelling committed runs.** `outputs/` are historical records, as in the
  previous sweep.

## 3. Design

### 3.1 Curation keys on (tool, metric)

`registry/calibration.json` goes to schema 2:

```json
{
  "schema_version": 2,
  "tools": {
    "esmfold-prediction": {
      "metrics": {
        "avg_plddt": {
          "status": "validated",
          "measured_error": {"kind": "mae", "value": 0.06, "n": 312},
          "benchmark": {"name": "CAMEO 2025-H1", "doi": "10.xxxx/yyy", "held_out": true},
          "applicability_domain": {"molecules": ["protein"], "length": [30, 800],
                                   "notes": "monomers only; no membrane proteins in the set"},
          "curated_on": "2026-08-18"
        }
      }
    }
  }
}
```

`status` stays two-valued (`needs_calibration` | `validated`); absence still
means `needs_calibration`, and silence is still never a promotion. `validated`
now **requires** `measured_error` and `benchmark` to be present — a promotion
without a number is the thing §6 exists to prevent, so the loader rejects it
rather than accepting a bare flag.

Migration from v1 is mechanical: v1's `{"status": ...}` per tool has no metric
to attach to, and the shipped file promotes nothing, so v1 is simply refused
with a message pointing here. No data is lost because no data exists.

### 3.2 Tool-level `status` becomes derived

Consumers that ask about a tool still get an answer, but it is computed rather
than curated:

> A tool is `validated` iff it has at least one `primary` metric and **every**
> `primary` metric is validated.

Rationale: `primary` is the catalogue's own statement of what the tool is meant
to be judged on. Measured: all 42 tools that declare a primary declare exactly
one, so in practice the rule reads "its primary metric is validated" — the
`every` is there for tools that later declare more than one.

A tool with no primary metric can never be tool-validated, which is correct —
there is nothing to judge it on. That covers **98 of 140**: the 92 that measure
nothing, plus 6 metric-bearing tools that declare no primary. Those 6 are the
uncomfortable case: they emit numbers a gate could threshold while the
catalogue never says which number the tool is *for*. They are reachable
per-metric under §3.1 and simply never roll up.

This keeps `resolve_coverage` working unchanged while the real gate moves down
a level.

### 3.3 `testable_by` separates measuring from ranking

Evidence goes to schema 3, adding one field:

```json
"testable_by": {
  "properties": ["pLDDT", "pAE_interaction"],
  "vocabulary": ["fold_confidence", "predicted_error"],
  "tools": ["esmfold-prediction", "boltz2-prediction"],
  "rankable_by": [],
  "requires_new_evaluator": false
}
```

`tools` keeps its current meaning — *can measure this* — so nothing downstream
breaks. `rankable_by` is the subset whose relevant metric is validated, and is
`[]` for every item in the repo today. `requires_new_evaluator` is unchanged
and still three-valued.

This is deliberately additive rather than a redefinition. The alternative —
making `requires_new_evaluator` four-valued to fold in calibration — overloads
one field with two independent questions and would silently change the meaning
of every committed `false`.

### 3.4 The 007 snapshot carries calibration, and `validate.py` uses it

`proto_metrics.json` goes to schema 4, adding per-metric `status` and
`measured_error`. Two new checks in `validate_proto`:

1. **A gate on an uncalibrated metric is a warning, not an error.** §6 lets an
   uncalibrated evaluator run. The runbook must label such gates so the reader
   knows the cascade is ordering candidates on an uncharacterised signal —
   which the emitted disclaimer already says in prose and can now say per gate.
2. **A gate whose threshold is finer than the metric's measured error is
   rejected.** `avg_plddt >= 0.85` against an MAE of 0.06 is a claim the
   evaluator cannot support. This is §6 bullet 3, enforceable for the first
   time, and only for calibrated metrics — an uncalibrated one has no error to
   compare against and falls under check 1.

Applicability domain (bullet 4) is recorded in this pass and enforced when
candidates exist to test against it; there is no candidate set today.

### 3.5 Schema versions move together

| file | from | to |
|---|---:|---:|
| `calibration.json` | 1 | 2 |
| `proto_catalog.json` | 2 | 3 |
| `proto_metrics.json` | 3 | 4 |
| evidence output | 2 | 3 |

`proto_catalog.json` bumps because `measures` rows gain a `calibration`
sub-object, overlaid at the end of `proto-sync` exactly as tool `status` is
today. Curation is *stored* separately and *overlaid* into the generated
artifact — the pattern that shipped in `f758275`, extended one level down.
The bump forces a regeneration (~9.5 min, needs the proto venv).

## 4. Testing

All offline; proto-tools and paperclip stay monkeypatched.

| area | cases |
|---|---|
| calibration v2 | per-metric promotion; `validated` without `measured_error` rejected; v1 file refused with a pointer; unknown status rejected; orphan metric on a real tool reported like an orphan tool |
| derived tool status | validated iff all primary validated; tool with no primary never validated; one-of-two primary validated stays uncalibrated |
| `resolve_properties` | `rankable_by` empty when nothing validated; populated when the specific metric is; `tools` unchanged either way |
| 007 | gate on uncalibrated metric warns; threshold finer than measured error rejected; coarser threshold passes; direction check still works |
| regression | `check()` still never treats `unknown` as pass; committed catalogue satisfies the vocabulary invariant |

## 5. Risks

- **`interface_energetics` is a near-singleton.** 2 of 311 rows, on 1 tool
  (`bindcraft-design`). Calibrating that one tool decides the term for the whole
  vocabulary, and `ev_006`/`ev_012` in the binder run already depend on it.
  A term this thin may not deserve to be a term.
- **Four schema bumps at once** is a wide blast radius for a change that
  promotes nothing. §6 sequencing puts the registry first precisely so each
  step is independently verifiable.
- **Deriving tool status from `primary` inherits the catalogue's judgement.**
  Only 42 of 311 rows are primary-flagged, and `primary` comes from tool
  authors' docstrings, not from us.
- **A calibration file with numbers in it invites trust it has not earned.**
  `measured_error` recorded from a paper's reported benchmark is not the same
  as one we measured. `benchmark.held_out` is the field that carries the
  distinction and it is easy to fill in carelessly.

## 6. Sequencing

Ordered so nothing depends on a later step.

A tractable first target, if one is wanted before the full surface: the
**23 rows that are both `primary` and reachable through the property
vocabulary**. Those are the only rows that can change a `rankable_by` answer
for evidence the pipeline actually produces today.

1. Calibration v2 and the per-metric loader (§3.1) — no consumer changes.
2. Derived tool status (§3.2) — keeps `resolve_coverage` honest.
3. `proto_catalog` v3 overlay and regeneration (§3.5).
4. `rankable_by` in evidence (§3.3).
5. 007 snapshot v4 and the two new checks (§3.4).

## 7. Open questions

1. **`resolve_coverage` takes tool keys, not metrics.** A plan names
   `candidate_evaluators: ["esmfold-prediction"]` with no metric, so coverage
   can only use the derived roll-up. Should plans name `tool:metric` pairs?
   That changes the plan contract and every existing plan.
2. **Is a kill gate "ranking"?** §6 forbids ranking on an uncalibrated
   evaluator. A cascade gate filters rather than orders, but a filter is an
   ordering with one boundary. §3.4 treats it as not-ranking-but-labelled;
   the stricter reading would forbid uncalibrated gates outright and empty the
   007 cascade today.
3. **Who may promote?** Framework §11 Q5 is still open. A promotion changes what
   the system is permitted to claim, and nothing currently distinguishes a
   curator from anyone with write access.
4. **Does `measured_error` need a distribution rather than a scalar?** An MAE
   hides heteroscedasticity; pLDDT error is not uniform across fold classes.
   Scalar is proposed for tractability and may be the wrong call.
