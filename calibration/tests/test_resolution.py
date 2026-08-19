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
