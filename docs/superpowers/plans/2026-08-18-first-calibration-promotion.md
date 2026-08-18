# First Calibration Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `calibration/` harness that measures the resolution of `esmfold-prediction:avg_plddt` on a held-out PDB benchmark and proposes a promotion record for a human to curate.

**Architecture:** A fifth uv project beside the other four, dependency-free and offline-testable. Benchmark selection and the resolution maths are pure functions. The proto-tools driver shells out to a committed runner script executed with `uv run --project ../proto python`, because proto-tools has no `run` verb and a tool call is a Python import inside that project's environment. The harness proposes; it never writes `registry/calibration.json`.

**Tech Stack:** Python 3.10+, pytest, uv. No third-party runtime dependencies. `proto_tools` is a run-time prerequisite of the live run only, never an import dependency of tested code.

**Spec:** `docs/superpowers/specs/2026-08-18-first-calibration-promotion-design.md`

## Global Constraints

- `measured_error` is **resolution**, in the units of the metric being thresholded (`avg_plddt`, on `[0.0, 1.0]`). Never an accuracy-units figure.
- The slope band is `avg_plddt >= 0.7`, stated explicitly because resolution depends on where the slope is taken.
- **A degenerate slope refuses to promote.** If the fit is flat within noise, resolution is undefined and the harness reports a failed promotion with the fit statistics — never a large `measured_error`.
- The harness **never writes** `registry/calibration.json`. It writes proposals under `calibration/out/`.
- ESMFold's training cutoff is established from the model card and recorded. **Never guessed.** An implementation that cannot establish it stops and reports.
- Every test is offline: the runner subprocess is faked. No test may require Modal, a GPU, or network.
- Run from `calibration/` as `uv run --project . pytest -q`.
- Existing suites must stay green: litkb 239, formulation_agent007 111 (+1 deselected), formulation_agent 24 (+4 deselected), biophys_triage 16.

---

## Task 1: Project skeleton and benchmark selection

**Files:**
- Create: `calibration/pyproject.toml`
- Create: `calibration/calib/__init__.py`
- Create: `calibration/calib/benchmark.py`
- Create: `calibration/tests/test_benchmark.py`
- Modify: `.github/workflows/tests.yml:10-29`

**Interfaces:**
- Consumes: nothing.
- Produces: `benchmark.select(entries, cutoff_date) -> (kept, rejected)`, where `entries` is a list of dicts with keys `pdb_id`, `released` (ISO date string), `method`, `n_chains`, `length`; `kept` is a list of `pdb_id` strings; `rejected` is a list of `{"pdb_id", "reason"}`.

- [ ] **Step 1: Create the project files**

`calibration/pyproject.toml` — mirrors litkb's, which is the repo's dependency-free pattern:

```toml
[project]
name = "calib"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = []

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.uv]
package = false

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

`calibration/calib/__init__.py` — empty file.

- [ ] **Step 2: Write the failing test**

Create `calibration/tests/test_benchmark.py`:

```python
from calib import benchmark

CUTOFF = "2020-05-01"


def _entry(**over):
    base = {"pdb_id": "7ABC", "released": "2023-01-01", "method": "X-RAY DIFFRACTION",
            "n_chains": 1, "length": 200}
    base.update(over)
    return base


def test_a_post_cutoff_single_chain_is_kept():
    kept, rejected = benchmark.select([_entry()], CUTOFF)
    assert kept == ["7ABC"]
    assert rejected == []


def test_a_pre_cutoff_entry_is_rejected_as_potentially_in_training():
    """The whole held-out claim rests on this filter. ESMFold was trained on
    the PDB, so an entry released before the cutoff may be in its training
    set and would produce a number that looks measured and is not."""
    kept, rejected = benchmark.select([_entry(released="2019-06-01")], CUTOFF)
    assert kept == []
    assert "cutoff" in rejected[0]["reason"]


def test_a_multi_chain_entry_is_rejected():
    kept, rejected = benchmark.select([_entry(n_chains=3)], CUTOFF)
    assert kept == []
    assert "chain" in rejected[0]["reason"]


def test_a_chain_outside_the_length_band_is_rejected():
    short, _ = benchmark.select([_entry(length=40)], CUTOFF)
    long_, _ = benchmark.select([_entry(length=900)], CUTOFF)
    assert short == [] and long_ == []


def test_a_non_xray_entry_is_rejected():
    kept, rejected = benchmark.select([_entry(method="SOLUTION NMR")], CUTOFF)
    assert kept == []
    assert "method" in rejected[0]["reason"]


def test_every_rejection_names_its_reason():
    """Rejections ship: a filtered-out entry must say which filter removed
    it, so a reviewer can audit the set rather than trust it."""
    entries = [_entry(pdb_id="A", released="2019-01-01"),
               _entry(pdb_id="B", n_chains=4),
               _entry(pdb_id="C", length=10),
               _entry(pdb_id="D", method="SOLUTION NMR")]
    _, rejected = benchmark.select(entries, CUTOFF)
    assert len(rejected) == 4
    assert all(r["reason"] and isinstance(r["reason"], str) for r in rejected)
    assert {r["pdb_id"] for r in rejected} == {"A", "B", "C", "D"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd calibration && uv run --project . pytest -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'calib.benchmark'`

- [ ] **Step 4: Write the implementation**

Create `calibration/calib/benchmark.py`:

```python
"""Selecting a held-out benchmark set.

Framework section 6 asks for measured reliability on a HELD-OUT benchmark.
ESMFold's structure module was trained on the PDB, so an arbitrary selection
of entries would produce a number that looks measured and is not. The cutoff
filter is what makes the claim honest, and it is the only filter here whose
removal would silently invalidate a promotion.
"""

MIN_LENGTH = 50
MAX_LENGTH = 400
METHOD = "X-RAY DIFFRACTION"


def select(entries, cutoff_date):
    """Split candidate PDB entries into a kept id list and named rejections.

    `cutoff_date` is an ISO date string; entries released on or before it are
    excluded. Dates compare lexically, which is correct for ISO-8601.
    """
    kept, rejected = [], []
    for e in entries:
        if e["released"] <= cutoff_date:
            rejected.append({"pdb_id": e["pdb_id"],
                             "reason": f"released {e['released']}, on or before the "
                                       f"training cutoff {cutoff_date}"})
        elif e["n_chains"] != 1:
            rejected.append({"pdb_id": e["pdb_id"],
                             "reason": f"{e['n_chains']} chains; the benchmark is "
                                       f"single-chain so TM-score is unambiguous"})
        elif not MIN_LENGTH <= e["length"] <= MAX_LENGTH:
            rejected.append({"pdb_id": e["pdb_id"],
                             "reason": f"{e['length']} residues outside the "
                                       f"{MIN_LENGTH}-{MAX_LENGTH} band"})
        elif e["method"] != METHOD:
            rejected.append({"pdb_id": e["pdb_id"],
                             "reason": f"method {e['method']!r}, not {METHOD}"})
        else:
            kept.append(e["pdb_id"])
    return kept, rejected
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd calibration && uv run --project . pytest -q`
Expected: PASS, 6 tests.

- [ ] **Step 6: Add the CI leg**

In `.github/workflows/tests.yml`, add to the `matrix.include` list after the `biophys_triage` entry:

```yaml
          - name: calibration
            dir: calibration
            args: ""
```

- [ ] **Step 7: Commit**

```bash
git add calibration/ .github/workflows/tests.yml
git commit -m "feat(calibration): project skeleton and held-out benchmark selection

Framework section 6 asks for a HELD-OUT benchmark. ESMFold trained on the
PDB, so the release-date filter is what separates a measured number from one
that only looks measured. Every excluded entry ships the filter that removed
it, so the set can be audited rather than trusted."
```

---

## Task 2: The resolution maths

**Files:**
- Create: `calibration/calib/resolution.py`
- Create: `calibration/tests/test_resolution.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `resolution.measure(rows, slope_floor=0.7) -> dict`. `rows` is a list of `{"pdb_id", "avg_plddt", "tm_score"}`. Returns `{"ok": True, "measured_error": float, "n": int, "slope": float, "sd_resid": float, "spearman": float}` or `{"ok": False, "reason": str, "slope": float, "sd_resid": float, "n": int}`.

- [ ] **Step 1: Write the failing test**

Create `calibration/tests/test_resolution.py`:

```python
import math

from calib import resolution


def _rows(slope, noise, n=40, start=0.70):
    """Synthetic rows with a KNOWN slope and known scatter, so the returned
    resolution has an arithmetic answer rather than a plausible one."""
    rows = []
    for i in range(n):
        plddt = start + (0.29 * i / (n - 1))
        # deterministic alternating residual of exactly +/- `noise`
        resid = noise if i % 2 == 0 else -noise
        rows.append({"pdb_id": f"P{i:03d}", "avg_plddt": plddt,
                     "tm_score": 0.5 + slope * (plddt - start) + resid})
    return rows


def test_resolution_is_scatter_divided_by_slope():
    """measured_error must come back in pLDDT units: an accuracy scatter of
    0.02 TM-score against a slope of 0.5 TM-score per pLDDT is 0.04 pLDDT.
    Returning 0.02 would be the units conflation the spec exists to prevent."""
    out = resolution.measure(_rows(slope=0.5, noise=0.02))

    assert out["ok"] is True
    assert math.isclose(out["measured_error"], 0.04, rel_tol=0.15)


def test_a_flat_slope_refuses_to_promote():
    """If pLDDT does not track accuracy, resolution is undefined. The honest
    output is no promotion -- NOT a huge measured_error, which would wave
    every gate through as trivially satisfiable."""
    out = resolution.measure(_rows(slope=0.0, noise=0.02))

    assert out["ok"] is False
    assert "slope" in out["reason"]
    assert "measured_error" not in out


def test_a_steeper_slope_gives_a_finer_resolution():
    """More discriminating metric, smaller detectable difference."""
    shallow = resolution.measure(_rows(slope=0.3, noise=0.02))["measured_error"]
    steep = resolution.measure(_rows(slope=0.9, noise=0.02))["measured_error"]
    assert steep < shallow


def test_rows_below_the_slope_floor_are_excluded():
    """The slope is taken over avg_plddt >= 0.7 because that is where gates
    are written; including low-confidence rows measures a different regime."""
    rows = _rows(slope=0.5, noise=0.01) + [
        {"pdb_id": "LOW", "avg_plddt": 0.20, "tm_score": 0.05}]
    out = resolution.measure(rows)
    assert out["n"] == 40


def test_too_few_rows_cannot_produce_a_fit():
    out = resolution.measure([{"pdb_id": "A", "avg_plddt": 0.8, "tm_score": 0.9}])
    assert out["ok"] is False
    assert "rows" in out["reason"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd calibration && uv run --project . pytest tests/test_resolution.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'calib.resolution'`

- [ ] **Step 3: Write the implementation**

Create `calibration/calib/resolution.py`:

```python
"""Turning benchmark rows into a resolution figure.

`validate.py` in formulation_agent007 compares a gate's threshold precision
against `measured_error`, so the number must carry the units of the metric
being thresholded -- pLDDT, not TM-score. Predicted confidence and observed
accuracy are different quantities, so the conversion is explicit rather than
implied:

    measured_error = sd_resid / slope
                   = TM-score / (TM-score per pLDDT)
                   = pLDDT

That is the pLDDT difference below which two structures cannot be told apart
on outcome, which is exactly what section 6's margin rule compares a
threshold against.
"""

import statistics

SLOPE_FLOOR = 0.7
MIN_ROWS = 8
# Below this the fit is flat within its own noise and the metric does not
# discriminate; dividing by it would manufacture an enormous "resolution"
# that every gate trivially satisfies.
MIN_SLOPE = 0.05


def _linfit(xs, ys):
    """Ordinary least squares. Returns (slope, intercept)."""
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return slope, my - slope * mx


def _spearman(xs, ys):
    def ranks(vs):
        order = sorted(range(len(vs)), key=lambda i: vs[i])
        r = [0.0] * len(vs)
        for pos, i in enumerate(order):
            r[i] = float(pos)
        return r
    rx, ry = ranks(xs), ranks(ys)
    slope, _ = _linfit(rx, ry)
    sdx, sdy = statistics.pstdev(rx), statistics.pstdev(ry)
    return 0.0 if sdx == 0 or sdy == 0 else slope * sdx / sdy


def measure(rows, slope_floor=SLOPE_FLOOR):
    """Resolution of the metric, in metric units, or a refusal."""
    used = [r for r in rows if r["avg_plddt"] >= slope_floor]
    n = len(used)
    if n < MIN_ROWS:
        return {"ok": False, "n": n, "slope": 0.0, "sd_resid": 0.0,
                "reason": f"only {n} rows at or above {slope_floor}; "
                          f"{MIN_ROWS} are needed for a fit"}

    xs = [r["avg_plddt"] for r in used]
    ys = [r["tm_score"] for r in used]
    slope, intercept = _linfit(xs, ys)
    resid = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
    sd_resid = statistics.pstdev(resid)

    if abs(slope) < MIN_SLOPE:
        return {"ok": False, "n": n, "slope": slope, "sd_resid": sd_resid,
                "reason": f"slope {slope:.4f} is flat within noise (below "
                          f"{MIN_SLOPE}); the metric does not discriminate on "
                          f"this set, so its resolution is undefined and it "
                          f"must not be promoted"}

    return {"ok": True, "measured_error": sd_resid / abs(slope), "n": n,
            "slope": slope, "sd_resid": sd_resid,
            "spearman": _spearman(xs, ys)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd calibration && uv run --project . pytest -q`
Expected: PASS, 11 tests.

- [ ] **Step 5: Commit**

```bash
git add calibration/
git commit -m "feat(calibration): derive resolution in metric units

measured_error is compared against a gate's threshold precision, so it must
carry pLDDT units. Predicted confidence and observed accuracy are different
quantities, so the conversion is explicit: scatter divided by slope cancels
TM-score and leaves pLDDT.

A slope flat within noise refuses to promote rather than returning a huge
error -- a metric that does not discriminate has no resolution, and a large
number would wave every gate through instead of blocking it."
```

---

## Task 3: The proto-tools driver and the proposal

**Files:**
- Create: `calibration/calib/driver.py`
- Create: `calibration/calib/propose.py`
- Create: `calibration/runner/run_chain.py`
- Create: `calibration/tests/test_driver.py`
- Create: `calibration/tests/test_propose.py`

**Interfaces:**
- Consumes: `resolution.measure` from Task 2.
- Produces: `driver.measure_chain(pdb_id, runner=None) -> dict` returning `{"pdb_id", "avg_plddt", "tm_score", "length"}` or raising `driver.DriverError`; `propose.build(tool, metric, rows, benchmark_meta) -> dict` returning the v2 curation fragment.

- [ ] **Step 1: Write the failing driver test**

Create `calibration/tests/test_driver.py`:

```python
import json

import pytest

from calib import driver


def _fake_runner(payload):
    """Stands in for the subprocess that executes inside the proto venv."""
    def run(job):
        assert job["pdb_id"] == "7ABC"
        return payload
    return run


def test_measure_chain_returns_the_pair_the_fit_needs():
    row = driver.measure_chain("7ABC", runner=_fake_runner(
        {"ok": True, "avg_plddt": 0.83, "tm_score": 0.91, "length": 210}))

    assert row == {"pdb_id": "7ABC", "avg_plddt": 0.83,
                   "tm_score": 0.91, "length": 210}


def test_a_failed_chain_raises_rather_than_returning_a_partial_row():
    """A chain that failed to fold or align must not enter the fit as a
    silent zero -- that would drag the slope toward flat and understate the
    metric, which is the fail-open direction."""
    with pytest.raises(driver.DriverError, match="esmfold"):
        driver.measure_chain("7ABC", runner=_fake_runner(
            {"ok": False, "stage": "esmfold", "error": "OOM"}))


def test_the_runner_is_never_called_at_import_time():
    """proto_tools is a run-time prerequisite, not an import dependency --
    this is what keeps the suite offline."""
    import calib.driver as d
    assert "proto_tools" not in json.dumps(sorted(dir(d)))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd calibration && uv run --project . pytest tests/test_driver.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'calib.driver'`

- [ ] **Step 3: Write the driver**

Create `calibration/calib/driver.py`:

```python
"""Driving the proto tools for one benchmark chain.

`proto-tools` has no `run` verb -- it is discovery only. A tool call is a
Python import from inside the proto project's environment, so this module
shells out to `runner/run_chain.py` under `uv run --project ../proto python`
rather than importing proto_tools itself. That keeps proto_tools a run-time
prerequisite instead of an import dependency, which is what lets every test
here run offline with the runner faked.
"""

import json
import subprocess

PROTO_PROJECT = "../proto"
RUNNER = "runner/run_chain.py"


class DriverError(RuntimeError):
    pass


def _subprocess_runner(job):
    proc = subprocess.run(
        ["uv", "run", "--project", PROTO_PROJECT, "python", RUNNER],
        input=json.dumps(job), capture_output=True, text=True)
    if proc.returncode != 0:
        raise DriverError(f"runner exited {proc.returncode}: {proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


def measure_chain(pdb_id, runner=None):
    """One chain -> one (avg_plddt, tm_score) row.

    Raises rather than returning a partial row: a chain that failed to fold
    or align must not enter the fit as a zero, which would drag the slope
    toward flat and understate the metric's discrimination.
    """
    result = (runner or _subprocess_runner)({"pdb_id": pdb_id})
    if not result.get("ok"):
        raise DriverError(
            f"{pdb_id} failed at {result.get('stage', 'unknown')}: "
            f"{result.get('error', 'no error reported')}")
    return {"pdb_id": pdb_id,
            "avg_plddt": result["avg_plddt"],
            "tm_score": result["tm_score"],
            "length": result["length"]}
```

- [ ] **Step 4: Write the runner script**

Create `calibration/runner/run_chain.py`. This is the only file that imports
`proto_tools`; it is never imported by the test suite.

```python
"""Executed with `uv run --project ../proto python runner/run_chain.py`.

Reads one job as JSON on stdin, writes one result as JSON on stdout. Kept
deliberately small: it is the only code here that cannot be tested offline,
so it holds no logic worth testing -- selection, maths and record-building
all live in `calib/`.

Ground truth is downloaded from RCSB rather than fetched with a proto tool.
`pdb-fetch-entry` returns metadata only and `alphafold-db-fetch` returns
AlphaFold predictions; aligning against a prediction would measure agreement
between two predictors, not reliability against experiment.
"""

import json
import sys
import urllib.request

RCSB_CIF = "https://files.rcsb.org/download/{}.cif"


def main():
    job = json.load(sys.stdin)
    pdb_id = job["pdb_id"]
    stage = "import"
    try:
        from proto_tools.tools.database_retrieval.pdb.fetch_fasta import (
            PdbFetchFastaInput, run_pdb_fetch_fasta,
        )
        from proto_tools.tools.structure_alignment.usalign.usalign import (
            USalignConfig, USalignInput, run_usalign,
        )
        from proto_tools.tools.structure_prediction.esmfold.esmfold import (
            ESMFoldConfig, ESMFoldInput, run_esmfold,
        )

        stage = "pdb-fetch-fasta"
        fasta = run_pdb_fetch_fasta(PdbFetchFastaInput(pdb_id=pdb_id))
        chains = [c for c in fasta.chains if c.is_protein]
        if len(chains) != 1:
            raise ValueError(f"expected one protein chain, got {len(chains)}")
        sequence = chains[0].sequence

        stage = "rcsb-download"
        with urllib.request.urlopen(RCSB_CIF.format(pdb_id), timeout=60) as resp:
            reference_cif = resp.read().decode()

        stage = "esmfold"
        predicted = run_esmfold(ESMFoldInput(complexes=[sequence]),
                                ESMFoldConfig()).structures[0]

        stage = "usalign"
        aln = run_usalign(
            USalignInput(query_structure=predicted,
                         reference_structure=reference_cif),
            USalignConfig(),
        )

        # structure_2 is the REFERENCE, so this is the reference-normalised
        # TM-score. Normalising by the prediction would let a truncated model
        # score well on the fragment it did predict.
        json.dump({"ok": True, "length": len(sequence),
                   "avg_plddt": predicted.metrics.avg_plddt,
                   "tm_score": aln.metrics.tm_score_structure_2}, sys.stdout)
    except Exception as exc:  # noqa: BLE001 -- reported, not swallowed
        json.dump({"ok": False, "stage": stage,
                   "error": f"{type(exc).__name__}: {exc}"}, sys.stdout)


if __name__ == "__main__":
    main()
```

Every name above was verified against the live catalogue while this plan was
written: the three import paths come from `proto-tools signature`,
`PdbChain` exposes `chain_ids/header/sequence/is_protein`, `ESMFoldOutput`
exposes `structures` with metrics on each item, and `USalignOutput` documents
`metrics.tm_score_structure_1|2`. Nothing here is guessed. If a name still
fails at run time the runner reports its `stage`, which names the step.

- [ ] **Step 5: Run the driver tests**

Run: `cd calibration && uv run --project . pytest tests/test_driver.py -q`
Expected: PASS, 3 tests.

- [ ] **Step 6: Write the failing proposal test**

Create `calibration/tests/test_propose.py`:

```python
from calib import propose

ROWS = [{"pdb_id": f"P{i}", "avg_plddt": 0.70 + 0.005 * i,
         "tm_score": 0.55 + 0.0025 * i + (0.01 if i % 2 else -0.01)}
        for i in range(40)]
META = {"name": "PDB post-cutoff single chains", "held_out": True,
        "cutoff_date": "2020-05-01",
        "selection": "X-ray, single chain, 50-400 aa, released after cutoff"}


def test_the_proposal_is_a_v2_curation_fragment():
    out = propose.build("esmfold-prediction", "avg_plddt", ROWS, META)

    rec = out["esmfold-prediction"]["metrics"]["avg_plddt"]
    assert rec["status"] == "validated"
    assert rec["measured_error"]["kind"] == "resolution"
    assert rec["measured_error"]["value"] > 0
    assert rec["benchmark"]["held_out"] is True
    assert rec["benchmark"]["cutoff_date"] == "2020-05-01"


def test_validity_is_recorded_beside_the_benchmark_not_in_measured_error():
    """measured_error is what the margin rule consumes; validity is what a
    reviewer judges the promotion by. Conflating them is the units error the
    spec exists to prevent."""
    rec = propose.build("esmfold-prediction", "avg_plddt", ROWS,
                        META)["esmfold-prediction"]["metrics"]["avg_plddt"]

    assert "spearman" in rec["benchmark"]["validity"]
    assert "spearman" not in rec["measured_error"]


def test_a_refused_measurement_produces_no_promotion():
    """A flat slope must not yield a record at all -- not a record with a
    large error, and not a record with status needs_calibration that a reader
    might mistake for a measured result."""
    flat = [{"pdb_id": f"P{i}", "avg_plddt": 0.70 + 0.005 * i, "tm_score": 0.8}
            for i in range(40)]
    out = propose.build("esmfold-prediction", "avg_plddt", flat, META)

    assert out["promoted"] is False
    assert "slope" in out["reason"]
    assert "esmfold-prediction" not in out
```

- [ ] **Step 7: Run it to verify it fails**

Run: `cd calibration && uv run --project . pytest tests/test_propose.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'calib.propose'`

- [ ] **Step 8: Write the proposal builder**

Create `calibration/calib/propose.py`:

```python
"""Building the curation fragment a human pastes into calibration.json.

This module deliberately stops at a proposal. `registry/calibration.json` is
curated, never generated -- that separation is what makes the overlay
trustworthy, and framework section 11's "who may promote" question is still
open, so a script must not answer it by writing the file.
"""

from . import resolution


def build(tool, metric, rows, benchmark_meta):
    """A v2 curation fragment, or a refusal carrying the fit statistics."""
    fit = resolution.measure(rows)
    if not fit["ok"]:
        return {"promoted": False, "reason": fit["reason"],
                "slope": fit["slope"], "sd_resid": fit["sd_resid"],
                "n": fit["n"]}

    benchmark = dict(benchmark_meta)
    benchmark["validity"] = {"spearman": round(fit["spearman"], 4),
                             "slope": round(fit["slope"], 4),
                             "sd_resid": round(fit["sd_resid"], 4)}
    lengths = [r.get("length") for r in rows if r.get("length")]
    return {
        "promoted": True,
        tool: {"metrics": {metric: {
            "status": "validated",
            "measured_error": {"kind": "resolution",
                               "value": round(fit["measured_error"], 4),
                               "n": fit["n"]},
            "benchmark": benchmark,
            "applicability_domain": {
                "molecules": ["protein"],
                "length": [min(lengths), max(lengths)] if lengths else None,
                "notes": "single chains only; measured on this benchmark set",
            },
        }}},
    }
```

- [ ] **Step 9: Run the full calibration suite**

Run: `cd calibration && uv run --project . pytest -q`
Expected: PASS, 17 tests.

- [ ] **Step 10: Verify the proposal satisfies the registry's own validation**

This is the seam that matters: a proposal the registry would refuse is
useless. Run from the repo root:

```bash
cd litterature_search_from_concept && uv run --project . python - <<'PY'
import json, sys
sys.path.insert(0, "../calibration")
from calib import propose
from litkb import proto

ROWS = [{"pdb_id": f"P{i}", "avg_plddt": 0.70 + 0.005 * i, "length": 200,
         "tm_score": 0.55 + 0.0025 * i + (0.01 if i % 2 else -0.01)}
        for i in range(40)]
META = {"name": "PDB post-cutoff single chains", "held_out": True,
        "cutoff_date": "2020-05-01", "selection": "test"}
frag = propose.build("esmfold-prediction", "avg_plddt", ROWS, META)
frag.pop("promoted")
cat = json.load(open("../registry/proto_catalog.json"))
out, orphans = proto.apply_calibration(cat, {"schema_version": 2, "tools": frag})
tool = [t for t in out["tools"] if t["key"] == "esmfold-prediction"][0]
voc = json.load(open("../registry/property_vocabulary.json"))
res = proto.resolve_properties(["fold_confidence"], out, voc)
print("accepted; orphans:", orphans, "| status:", tool["status"])
print("rankable_by:", res["rankable_by"], "| can measure:", len(res["tools"]))
PY
```

Expected:

```
accepted; orphans: [] | status: validated
rankable_by: [esmfold-prediction] | can measure: 15
```

That second line is the point of the whole exercise: the first non-empty
`rankable_by` the system has produced, and the moment 15 tools that can
measure a property stop being indistinguishable from the one that may rank
on it.

- [ ] **Step 11: Commit**

```bash
git add calibration/
git commit -m "feat(calibration): proto driver and promotion proposal

proto-tools has no run verb, so the driver shells out to a small runner
executed inside the proto environment. The runner is the only file importing
proto_tools and holds no logic worth testing; selection, maths and record
building stay in calib/ where they run offline.

A chain that fails to fold or align raises rather than entering the fit as a
zero, which would drag the slope toward flat and understate the metric.

The builder stops at a proposal. calibration.json is curated, never
generated, and section 11's who-may-promote question is still open."
```

---

## Operator procedure — the live run

Not implementable work: these steps need a GPU, cost money, and end in a
human judgement. They are recorded here so the run is reproducible.

- [ ] **Establish ESMFold's training cutoff** from its model card. Record the
  date and the source. **If it cannot be established unambiguously, stop** —
  the held-out claim rests on it and a guessed year invalidates the promotion.

- [ ] **Build the candidate entry list** and run `benchmark.select`, committing
  the kept ids and the named rejections.

- [ ] **Confirm Modal is authenticated and the tool is deployed**
  (`uv run --project ../proto proto-tools doctor`).

- [ ] **Get explicit go-ahead for the GPU spend**, then run one ESMFold call
  per kept chain, writing `calibration/out/measurements.csv`.

- [ ] **Build the proposal** and read it. A `promoted: false` result is a
  legitimate outcome, not a failed run.

- [ ] **Promote by hand** into `registry/calibration.json`, then
  `cd litterature_search_from_concept && uv run --project . python -m litkb
  proto-sync -o ../registry/proto_catalog.json --snapshot
  ../registry/proto_metrics.json --calibration ../registry/calibration.json`
  to carry it into the derived registries.

## Verification

- [ ] `calibration/` suite passes and is a CI matrix leg
- [ ] Every existing suite still passes: litkb 239, 007 111 (+1 deselected), formulation_agent 24 (+4), biophys 16
- [ ] No test requires Modal, a GPU, or network
- [ ] `calib` imports no `proto_tools` outside `runner/run_chain.py`
- [ ] The harness never writes `registry/calibration.json`
- [ ] A flat slope yields `promoted: false` with fit statistics, and no record
- [ ] A built proposal is accepted by `proto.apply_calibration` and derives `esmfold-prediction` to `validated`
