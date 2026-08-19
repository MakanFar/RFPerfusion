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
