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


def test_slope_just_below_min_slope_threshold_refuses_to_promote():
    """Operator flip on MIN_SLOPE comparison (< to <=) would let a
    non-discriminating metric promote. This test pins that a fitted slope
    below the threshold refuses, catching the fail-open guard."""
    # Nominal slope 0.04 should fit very close to 0.04, below MIN_SLOPE=0.05
    out = resolution.measure(_rows(slope=0.04, noise=0.01))
    assert out["ok"] is False
    assert "slope" in out["reason"]
    assert "measured_error" not in out


def test_slope_just_above_min_slope_threshold_proceeds():
    """Operator flip on MIN_SLOPE comparison would prevent a barely-discriminating
    metric from promoting. This test pins the boundary: a slope just above
    the threshold must proceed, protecting the valid promotion case."""
    # Nominal slope 0.06 should fit very close to 0.06, above MIN_SLOPE=0.05
    out = resolution.measure(_rows(slope=0.06, noise=0.01))
    assert out["ok"] is True
    assert "measured_error" in out


def test_exactly_min_rows_produces_a_fit():
    """Operator flip on MIN_ROWS comparison (< to <=) would reject the minimum
    valid sample. This test pins that exactly MIN_ROWS=8 rows produce a fit."""
    rows = _rows(slope=0.5, noise=0.01, n=8, start=0.70)
    out = resolution.measure(rows)
    assert out["ok"] is True
    assert out["n"] == 8
    assert "measured_error" in out


def test_one_below_min_rows_refuses_to_fit():
    """Below MIN_ROWS, insufficient data for reliable fit. This test pins
    the boundary: n=7 must refuse, protecting the comparison operator from
    accidental flips that would allow underpowered fits."""
    rows = _rows(slope=0.5, noise=0.01, n=7, start=0.70)
    out = resolution.measure(rows)
    assert out["ok"] is False
    assert "rows" in out["reason"]
    assert out["n"] == 7
    assert "measured_error" not in out
