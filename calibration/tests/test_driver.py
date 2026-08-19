import sys

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
