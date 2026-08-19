import sys

import pytest

from calib import driver


def _fake_runner(payload):
    """Stands in for the subprocess that executes inside the proto venv."""
    def run(job):
        assert job["pdb_id"] == "7ABC"
        return payload
    return run


def _payload(**over):
    """The runner emits pure data; every decision on it belongs here."""
    base = {"ok": True, "avg_plddt": 0.83, "n_protein_chains": 1,
            "query_length": 210, "reference_length": 208,
            "tm_score_structure_1": 0.95, "tm_score_structure_2": 0.91}
    base.update(over)
    return base


def test_measure_chain_returns_the_pair_the_fit_needs():
    row = driver.measure_chain("7ABC", runner=_fake_runner(_payload()))

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
    this is what keeps the suite offline.

    Checking `"proto_tools" not in dir(d)` is not a real guard: a
    `from proto_tools.x.y import z` binds only the name `z` into the module,
    so it never appears in `dir(driver)` even though the import ran and
    `proto_tools` (and everything it pulls in) is now loaded. The only
    reliable signal that an import actually executed is interpreter state --
    `sys.modules` -- not what name the importing module chose to bind it to.
    Do not simplify this back to a `dir()`/name check.
    """
    import calib.driver  # noqa: F401 -- import is the thing under test
    assert "proto_tools" not in sys.modules


def test_a_malformed_runner_response_raises_naming_the_pdb_id(monkeypatch):
    """runner/run_chain.py imports heavyweight ML libraries and shells out to
    external tools, any of which can print incidental text to stdout ahead of
    the final json.dump and corrupt the parse. A zero exit with unparseable
    stdout must not surface as a raw json.JSONDecodeError with no pdb_id and
    no indication it came from the runner subprocess."""
    class _FakeCompletedProcess:
        returncode = 0
        stdout = "warning: some library printed this\nnot json"
        stderr = ""

    monkeypatch.setattr(driver.subprocess, "run",
                        lambda *a, **k: _FakeCompletedProcess())

    with pytest.raises(driver.DriverError, match="7ABC"):
        driver._subprocess_runner({"pdb_id": "7ABC"})


def test_the_reference_normalised_tm_score_is_the_one_selected():
    """usalign emits both normalisations. structure_2 is the REFERENCE, so
    only it answers "how much of the experimental structure did the model get
    right". Normalising by the prediction (structure_1) would let a truncated
    model score well on the fragment it did predict -- plausible-looking and
    categorically wrong. The choice lives here, under test, rather than in
    the runner where a silent flip could not be caught offline."""
    row = driver.measure_chain("7ABC", runner=_fake_runner(
        _payload(tm_score_structure_1=0.99, tm_score_structure_2=0.42)))

    assert row["tm_score"] == 0.42


def test_a_multi_chain_entry_is_rejected_by_the_driver():
    """The benchmark is single-chain so TM-score is unambiguous. The runner
    reports the count; refusing on it is a decision and belongs in tested
    code."""
    with pytest.raises(driver.DriverError, match="3 protein chains"):
        driver.measure_chain("7ABC", runner=_fake_runner(
            _payload(n_protein_chains=3)))


@pytest.mark.parametrize("field", ["avg_plddt", "tm_score_structure_2",
                                   "n_protein_chains", "query_length"])
def test_an_incomplete_row_raises_driver_error_naming_the_field(field):
    """A bare KeyError from deep inside the driver tells an operator nothing
    about which chain or which field failed, and invites the console glue to
    swallow it."""
    payload = _payload()
    payload.pop(field)
    with pytest.raises(driver.DriverError, match=field):
        driver.measure_chain("7ABC", runner=_fake_runner(payload))


@pytest.mark.parametrize("field", ["avg_plddt", "tm_score_structure_2"])
def test_a_non_numeric_value_raises_rather_than_entering_the_fit(field):
    """`None` compares fine against nothing and blows up inside statistics,
    or worse, silently participates."""
    with pytest.raises(driver.DriverError, match="None"):
        driver.measure_chain("7ABC", runner=_fake_runner(_payload(**{field: None})))


def test_a_plddt_on_the_0_to_100_scale_is_refused_not_folded_into_the_fit():
    """The catalogue declares avg_plddt on [0.0, 1.0]. If a run came back on
    the 0-100 scale, the 0.7 slope floor becomes a no-op (every row is >= 70),
    the slope shrinks 100x, and the fit reports "the metric does not
    discriminate on this set" -- a units bug delivered as a scientific
    conclusion, after the GPU has already been paid for."""
    with pytest.raises(driver.DriverError, match="83.0"):
        driver.measure_chain("7ABC", runner=_fake_runner(_payload(avg_plddt=83.0)))

    with pytest.raises(driver.DriverError, match=r"\[0.0, 1.0\]"):
        driver.measure_chain("7ABC", runner=_fake_runner(_payload(tm_score_structure_2=91.0)))


def test_the_runner_paths_do_not_depend_on_the_working_directory():
    """`../proto` and `runner/run_chain.py` resolve only when the process
    happens to sit in `calibration/`. The live run is the one thing that
    cannot be re-run for free, so it must not depend on where it was
    launched from."""
    from pathlib import Path

    assert Path(driver.RUNNER).is_absolute()
    assert Path(driver.RUNNER).exists()
    assert Path(driver.PROTO_PROJECT).is_absolute()


def test_a_hung_runner_surfaces_as_a_driver_error(monkeypatch):
    """One ESMFold call can hang on the GPU. Without a timeout the whole
    benchmark run blocks forever with no ledger and no partial result."""
    def _hang(*a, **k):
        raise driver.subprocess.TimeoutExpired(cmd="uv", timeout=k.get("timeout"))

    monkeypatch.setattr(driver.subprocess, "run", _hang)

    with pytest.raises(driver.DriverError, match="timed out"):
        driver._subprocess_runner({"pdb_id": "7ABC"})
