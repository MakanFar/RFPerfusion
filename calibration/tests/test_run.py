import csv
import json
from pathlib import Path

from calib import driver, run

META = {"name": "PDB post-cutoff single chains", "held_out": True,
        "cutoff_date": "2020-05-01",
        "selection": "X-ray, single chain, 50-400 aa, released after cutoff"}

# Slope 0.5, scatter 0.01, forty rows above the 0.7 floor: a fit that
# promotes, so the writer is exercised on the record it will really emit.
ROWS = [{"pdb_id": f"P{i:03d}", "avg_plddt": 0.70 + 0.005 * i, "length": 200 + i,
         "tm_score": 0.55 + 0.0025 * i + 0.01 * (1, -1, -1, 1)[i % 4]}
        for i in range(40)]


def _measure(failures):
    """Stands in for driver.measure_chain: named ids fail, the rest measure."""
    def measure(pdb_id, runner=None):
        if pdb_id in failures:
            raise driver.DriverError(f"{pdb_id} failed at esmfold: {failures[pdb_id]}")
        return {"pdb_id": pdb_id, "avg_plddt": 0.85, "tm_score": 0.9, "length": 200}
    return measure


def test_a_failing_chain_is_recorded_in_the_ledger_not_silently_dropped():
    """The naive console glue for this is `try/except: pass`, and it is
    biased: if failures correlate with anything -- long chains, ESMFold OOM,
    obsoleted entries -- the surviving set is not the set that was selected,
    and nothing says so. `benchmark.select` names every rejection for exactly
    this reason; a chain lost after selection must be named too."""
    rows, exclusions = run.measure_all(
        ["7AAA", "7BBB", "7CCC"], measure=_measure({"7BBB": "OOM"}))

    assert [r["pdb_id"] for r in rows] == ["7AAA", "7CCC"]
    assert [e["pdb_id"] for e in exclusions] == ["7BBB"]
    assert "OOM" in exclusions[0]["reason"]


def test_every_submitted_chain_is_either_measured_or_excluded():
    """The ledger is only an audit trail if it accounts for everything."""
    ids = [f"7{i:03d}" for i in range(10)]
    rows, exclusions = run.measure_all(
        ids, measure=_measure({"7003": "OOM", "7007": "obsolete entry"}))

    assert len(rows) + len(exclusions) == len(ids)
    assert {r["pdb_id"] for r in rows} | {e["pdb_id"] for e in exclusions} == set(ids)


def test_the_writer_emits_both_artifacts_the_spec_names(tmp_path):
    paths = run.write_proposal("esmfold-prediction", "avg_plddt", ROWS, [],
                               META, out_dir=tmp_path)

    assert paths["proposal"].name == "proposed_esmfold-prediction_avg_plddt.json"
    assert paths["measurements"].name == "measurements.csv"
    assert json.loads(paths["proposal"].read_text())["promoted"] is True

    with paths["measurements"].open() as fh:
        written = list(csv.DictReader(fh))
    assert len(written) == len(ROWS)
    assert written[0]["pdb_id"] == "P000"


def test_the_written_proposal_carries_the_exclusion_ledger(tmp_path):
    """A reviewer judging the promotion has to see what was dropped and why,
    or the measured set silently stops being the selected set."""
    exclusions = [{"pdb_id": "7BBB", "reason": "7BBB failed at esmfold: OOM"}]
    paths = run.write_proposal("esmfold-prediction", "avg_plddt", ROWS,
                               exclusions, META, out_dir=tmp_path)

    doc = json.loads(paths["proposal"].read_text())
    bench = doc["esmfold-prediction"]["metrics"]["avg_plddt"]["benchmark"]
    assert bench["exclusions"] == exclusions


def test_a_refusal_is_written_too_and_still_names_the_exclusions(tmp_path):
    """No promotion is a real outcome, not an error. It must leave the same
    audit trail as a promotion."""
    flat = [{"pdb_id": f"F{i}", "avg_plddt": 0.70 + 0.005 * i,
             "tm_score": 0.8, "length": 200} for i in range(40)]
    exclusions = [{"pdb_id": "7BBB", "reason": "7BBB failed at esmfold: OOM"}]
    paths = run.write_proposal("esmfold-prediction", "avg_plddt", flat,
                               exclusions, META, out_dir=tmp_path)

    doc = json.loads(paths["proposal"].read_text())
    assert doc["promoted"] is False
    assert doc["exclusions"] == exclusions


def test_the_harness_never_writes_the_curated_registry(tmp_path):
    """`registry/calibration.json` is curated and a human promotes into it.
    The harness only proposes -- section 11's "who may promote" is still open
    and a script must not answer it by writing the file."""
    registry = Path(run.__file__).resolve().parents[2] / "registry" / "calibration.json"
    before = registry.read_bytes()

    paths = run.write_proposal("esmfold-prediction", "avg_plddt", ROWS, [],
                               META, out_dir=tmp_path)

    assert registry.read_bytes() == before
    for path in paths.values():
        assert path.resolve().parent == tmp_path.resolve()


def test_the_default_output_directory_is_calibration_out():
    """Every path the writer can produce resolves under calibration/out/ --
    the only place it is allowed to write."""
    calibration = Path(run.__file__).resolve().parents[1]

    assert run.OUT_DIR == calibration / "out"
    assert run.OUT_DIR.is_relative_to(calibration)
