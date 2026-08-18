# Design — The first calibration promotion

| | |
|---|---|
| **Date** | 2026-08-18 |
| **Status** | Approved for planning |
| **Scope** | New `calibration/` project; `registry/calibration.json` (data only) |
| **Relationship to PRDs** | Makes `PRD-framework.md` §6 enforceable rather than merely expressible. No principle changes. |
| **Follows** | `2026-08-18-calibration-granularity-design.md`, which built the mechanism this fills. |

## 1. Problem

The granularity branch shipped the machinery and none of the data. Measured at
`332d838`:

| | |
|---|---:|
| tools in the catalogue | 140 |
| tools reading `validated` | **0** |
| metric rows reading `needs_calibration` | 311 / 311 |
| evidence items with a non-empty `rankable_by` | **0** |
| gates the margin check can fire on | **0** |

Every piece is inert for the same reason: `registry/calibration.json` has an
empty `tools` map. §6 forbids ranking candidates on an uncalibrated evaluator,
so today the system may order candidates for synthesis and may not rank them —
and the runbook says so on every gate.

Nothing here is broken. The gap is that no metric has ever been measured.

### 1.1 What `measured_error` has to be

`validate.py` compares a gate's threshold precision against
`measured_error["value"]`: `step = _decimal_step(gate.threshold)`, then
`step < err` rejects. So the figure is consumed **in the units of the metric
being thresholded** — for `avg_plddt`, units of pLDDT on [0.0, 1.0].

That rules out the obvious reading. "How well does pLDDT agree with the truth"
is naturally expressed as an error in *accuracy* units (TM-score, lDDT), and
comparing a pLDDT threshold against a TM-score error is a category error —
two different scales, silently compared.

`measured_error` is therefore **resolution**: the smallest difference in
`avg_plddt` that corresponds to a real difference in outcome. It answers the
question the margin rule actually asks — *is 0.85 distinguishable from 0.84?*

Validity (does the metric predict anything at all?) is a different question. It
belongs to the promotion decision, not to the margin arithmetic, and §3.4
records it separately.

### 1.2 "Held out" is the load-bearing word

§6 asks for measured reliability **on a held-out benchmark**. ESMFold's
structure module was trained on the PDB, so most PDB entries are potentially
in-training and picking arbitrary ones would produce a number that looks
measured and is not.

## 2. Non-goals

- **Calibrating more than one metric.** This promotes exactly
  `esmfold-prediction:avg_plddt`. Not `ptm`, not the other 22 primary
  vocabulary-reachable rows, not `fold_confidence` as a term.
- **Automating promotion.** The harness proposes; a human promotes.
  `calibration.json` stays curated, which is the property that made the
  overlay trustworthy.
- **Answering §11 Q5 (who may promote).** Still open. This design keeps a
  human in the loop precisely so a script does not answer it by accident.
- **Re-running committed literature runs.** They are historical records.
- **Applicability domain enforcement.** The record gains the field; nothing
  consumes it until there is a candidate set to test against.

## 3. Design

### 3.1 A `calibration/` project

A fifth uv project beside the other four. It earns its own project rather than
a `litkb` subcommand because it has a different dependency profile (proto-tools
and Modal), a different cadence (run when the catalogue moves, not per
literature run), and it is the only thing that reads the benchmark. litkb's
stated purpose is literature to evidence; calibration is neither.

Its offline tests join the CI matrix. The measuring run itself is not CI work —
it needs a GPU and costs money.

### 3.2 The measurement

Per benchmark chain, three of the four steps are free and local:

| step | tool | GPU | yields |
|---|---|---|---|
| 1 | `pdb-fetch-entry` | no | experimental structure (ground truth) |
| 2 | `pdb-fetch-fasta` | no | its sequence |
| 3 | `esmfold-prediction` | **yes** | predicted structure + `avg_plddt` |
| 4 | `usalign-alignment` | no | TM-score, predicted vs experimental |

`usalign-alignment` takes `query_structure` and `reference_structure`
(confirmed against `proto-tools input usalign-alignment`), which is exactly
the pair required. TM-score rather than RMSD because it is length-normalised,
so chains of different sizes are comparable without a correction.

The output is one row per chain: `(pdb_id, length, avg_plddt, tm_score)`.

### 3.3 Deriving resolution from those rows

Predicted confidence and observed accuracy are different quantities, so the
conversion is explicit:

1. Fit accuracy against confidence over the benchmark rows; take the local
   slope `dTM/dpLDDT` over `avg_plddt >= 0.7`. That band is stated explicitly
   rather than left as "the high-confidence end" because the slope — and so
   the resolution — depends on where it is taken, and every gate in the
   generated cascades sits above it (measured: the seven gates of the
   `rf-ferritin-thermoswitch` brief threshold at 0.75 and 0.8).
2. Take the residual scatter of TM-score about that fit, `sd_resid`.
3. `measured_error = sd_resid / slope`, which carries units of
   TM-score ÷ (TM-score per pLDDT) = **pLDDT**.

That is the pLDDT difference below which two structures cannot be told apart
on outcome. A gate quoted finer than it is claiming precision the evaluator
does not have, which is what §6 forbids and what `validate.py` now rejects.

**A degenerate slope is a refusal, not a small number.** If the fit is flat
within noise, the metric does not discriminate at all, resolution is undefined
(division by ~0), and the correct outcome is **no promotion** — not an
enormous `measured_error`. The harness must report that case as a failed
promotion with the fit statistics attached.

### 3.4 The proposed record

The harness writes `calibration/out/proposed_<tool>_<metric>.json` and a raw
`measurements.csv`. It never edits `registry/calibration.json`.

```json
{
  "esmfold-prediction": {
    "metrics": {
      "avg_plddt": {
        "status": "validated",
        "measured_error": {"kind": "resolution", "value": 0.06, "n": 87},
        "benchmark": {
          "name": "PDB post-cutoff single chains",
          "held_out": true,
          "cutoff_date": "<ESMFold training cutoff, from the model card>",
          "selection": "X-ray, single chain, 50-400 aa, released after cutoff",
          "validity": {"spearman": 0.78, "slope": 0.42, "sd_resid": 0.025}
        },
        "applicability_domain": {
          "molecules": ["protein"], "length": [50, 400],
          "notes": "single chains only; no membrane proteins in the set"
        },
        "curated_on": "2026-08-18"
      }
    }
  }
}
```

**This record was verified against the live code before any harness existed.**
Passing it to `proto.apply_calibration` over the committed catalogue is
accepted (no orphans), derives `esmfold-prediction` to `status: validated`
through its primary metric, and makes `resolve_properties(["fold_confidence"])`
return `rankable_by: ["esmfold-prediction"]` against 15 tools that can measure
the term — the first non-empty `rankable_by` the system has produced. So the
consuming half of this design is already proven; what remains is earning the
number.

`validity` sits inside `benchmark` because it describes the measurement, not
the error. Nothing reads it; it exists so a reviewer can judge whether the
promotion was earned. `applicability_domain` records the set's actual span
rather than an aspiration — a promotion measured on 50–400 aa single chains
says nothing about a 900-residue complex.

### 3.5 The benchmark set

~60–100 chains, selected by: released after ESMFold's training cutoff, X-ray,
single chain, 50–400 residues (inside the tool's 2,400 cap with room to spare).

**The cutoff date is established from ESMFold's model card during
implementation and recorded in the benchmark block.** It is not guessed here.
The entire held-out claim rests on that one date, so an implementation that
cannot establish it must stop and report rather than substitute a plausible
year.

Selection is committed as a list of PDB ids, so the run is reproducible and a
reviewer can audit what was measured.

## 4. Testing

Offline, with the proto-tools calls faked — same contract as the other suites.

| area | cases |
|---|---|
| resolution maths | known slope + scatter yields the expected value; a flat (degenerate) slope refuses to promote rather than returning a large error; a single row cannot produce a fit |
| units | the emitted `measured_error` is in metric units, not accuracy units — a fixture where the two differ catches a conflation |
| record shape | the proposal validates against `proto.apply_calibration`'s v2 rules (a promotion missing `measured_error` or `benchmark` is refused) |
| benchmark selection | a chain outside the length band, a multi-chain entry, and a pre-cutoff release are each excluded with a recorded reason |
| harness | never writes `registry/calibration.json` |
| end to end | the proposed record, pasted into a copy of `calibration.json`, makes `resolve_properties` return a non-empty `rankable_by` and makes a too-fine gate fail `validate_proto` |

## 5. Risks

- **The measurement may refuse to promote.** If pLDDT does not discriminate on
  this set, the honest output is no promotion. That is a real possible outcome
  and the design treats it as success, not failure.
- **GPU cost is real.** One ESMFold call per chain, billable on Modal, and the
  run is explicitly gated on a human go-ahead separate from approving this
  design.
- **The cutoff date may be hard to pin.** If ESMFold's card does not state it
  unambiguously, the held-out claim weakens and the promotion should not
  proceed on a guess.
- **Resolution derived from one benchmark generalises no further than that
  benchmark.** `applicability_domain` records the span; nothing enforces it
  yet, so a reader could over-apply the number.
- **One promoted metric changes system behaviour broadly.** `rankable_by`
  becomes non-empty, `resolve_coverage` can return `full`, and the margin
  check goes live — three consequences from a single record, which is why the
  end-to-end test in §4 exists.

## 6. Sequencing

1. The `calibration/` project skeleton, benchmark selection, and its committed
   PDB id list — no GPU, fully testable.
2. The resolution maths, against synthetic rows with known answers.
3. The proto-tools driver (fetch, fold, align), faked in tests.
4. The live run, on explicit go-ahead. Emits the proposal and `measurements.csv`.
5. Human review, then promotion into `registry/calibration.json` by hand,
   followed by `litkb proto-sync` to carry it into the derived registries.

## 7. Open questions

1. **Who may promote?** §11 Q5, still unanswered. This design routes around it
   by keeping a human in the loop; it does not settle it.
2. **Does one metric's resolution license the `fold_confidence` term?** The
   term maps to six metrics across fifteen tools. Promoting `avg_plddt` on
   `esmfold-prediction` makes exactly that pair rankable — but the vocabulary
   union in `resolve_properties` means an item assigned `fold_confidence` will
   list that tool as rankable for the whole claim (the deferred finding F from
   the previous branch). Worth settling before a second metric lands.
3. **Should `ptm` be promoted from the same run?** ESMFold emits it at no extra
   GPU cost, and the same structures give its resolution. Deliberately out of
   scope here to keep the first promotion narrow, but it is nearly free later.
