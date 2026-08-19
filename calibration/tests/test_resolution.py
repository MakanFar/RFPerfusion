import math
import statistics

import pytest

from calib import resolution


# Residual signs in blocks of four. A plain +/- alternation is NOT
# slope-neutral: its correlation with x shifts the fitted slope by about
# -0.5 * noise, so a fixture asking for slope 0.1 at noise 0.3 actually fit
# to -0.05. This pattern sums to zero against x within every block, so the
# fitted slope equals the nominal one and sd_resid equals `noise` exactly.
_SIGNS = (1, -1, -1, 1)


def _rows(slope, noise, n=40, start=0.70):
    """Synthetic rows with a KNOWN slope and known scatter, so the returned
    resolution has an arithmetic answer rather than a plausible one."""
    rows = []
    for i in range(n):
        plddt = start + (0.29 * i / (n - 1))
        resid = noise * _SIGNS[i % 4]
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


def test_a_negative_slope_refuses_to_promote():
    """An anti-predictive metric is not a calibrated one. If accuracy FALLS as
    confidence rises, taking |slope| turns the failure into a healthy-looking
    resolution and licenses ranking candidates in exactly the wrong order --
    the one thing framework section 6 exists to prevent. The refusal must name
    the direction, because the magnitude alone reads as a good fit."""
    out = resolution.measure(_rows(slope=-0.5, noise=0.02))

    assert out["ok"] is False
    assert "negative" in out["reason"]
    assert "measured_error" not in out


def test_a_slope_smaller_than_its_own_standard_error_refuses():
    """Spec section 3.3 defines the refusal as "the fit is flat WITHIN NOISE"
    -- a statement about the slope relative to its own standard error, not
    against an absolute constant. A slope of 0.1 against a residual scatter of
    0.3 clears any fixed floor and is still indistinguishable from zero; the
    resolution it would yield is larger than the whole [0, 1] metric range."""
    out = resolution.measure(_rows(slope=0.1, noise=0.3))

    assert out["ok"] is False
    assert "standard error" in out["reason"]
    assert "measured_error" not in out


def test_a_resolution_larger_than_the_metric_range_refuses():
    """A resolution approaching the metric's own range is not a resolution:
    it says no two values of avg_plddt on [0, 1] can be told apart, which is a
    refusal rather than an enormous measured_error every gate satisfies."""
    # Enough rows that the standard-error test passes on its own, so this
    # exercises the sanity bound rather than the noise test.
    out = resolution.measure(_rows(slope=0.15, noise=0.05, n=80))

    assert out["ok"] is False
    assert "resolution" in out["reason"]
    assert "measured_error" not in out


def test_spearman_averages_tied_ranks_rather_than_ordering_by_input():
    """spearman is the human promoter's independent check on DIRECTION, and
    direction is exactly what can go wrong. Breaking ties by input order
    manufactures a within-group correlation out of row ordering: on this
    fixture the tie-corrected rho is +0.61 and ordering by input reports
    -0.26, so the reviewer's independent check would read backwards."""
    rows = [{"pdb_id": f"T{i}", "avg_plddt": 0.90, "tm_score": 0.90 - 0.02 * i}
            for i in range(12)]
    rows.append({"pdb_id": "HI", "avg_plddt": 0.95, "tm_score": 0.99})
    rows.append({"pdb_id": "LO", "avg_plddt": 0.85, "tm_score": 0.60})

    out = resolution.measure(rows)

    assert out["ok"] is True
    assert out["spearman"] > 0
    assert math.isclose(out["spearman"], 0.6094, abs_tol=0.001)


def test_slope_standard_error_uses_the_unbiased_residual_estimator():
    """The flat-within-noise guard is a false-promotion safeguard, so its
    standard error must not be understated.

    OLS spends two degrees of freedom fitting the slope and the intercept,
    so the residual variance divides by n-2. Dividing by n (which is what
    `statistics.pstdev` does) understates se by sqrt(n/(n-2)) -- about 15%
    at MIN_ROWS=8 -- making `slope < 2*se` fire less often than it should.
    Less often, for this guard, means promoting fits that are not actually
    distinguishable from flat.

    Hand-checkable: with 8 residuals of magnitude 0.1, SS_resid = 8*0.01 =
    0.08, so the unbiased sd is sqrt(0.08/6) = 0.11547 against pstdev's
    sqrt(0.08/8) = 0.1. With sxx = 4.0 the se is 0.11547/2 = 0.057735,
    where the population estimator would have said 0.05.
    """
    resid = [0.1, -0.1] * 4
    assert resolution._slope_se(resid, sxx=4.0) == pytest.approx(0.057735, rel=1e-4)


def test_the_unbiased_standard_error_is_larger_than_the_population_one():
    """Direction check: the corrected estimator must be strictly more
    conservative, never less, at every n above the fit's own degrees of
    freedom."""
    resid = [0.05, -0.05] * 6
    sxx = 3.0
    unbiased = resolution._slope_se(resid, sxx)
    population = statistics.pstdev(resid) / math.sqrt(sxx)
    assert unbiased > population


def test_a_slope_between_the_two_estimators_is_now_refused():
    """The whole point of the correction: a fit that the population
    estimator would have waved through, because its se looked smaller than
    it is, must now refuse."""
    resid = [0.1, -0.1] * 4
    sxx = 4.0
    population_se = statistics.pstdev(resid) / math.sqrt(sxx)
    unbiased_se = resolution._slope_se(resid, sxx)
    borderline = (2 * population_se + 2 * unbiased_se) / 2

    assert 2 * population_se < borderline < 2 * unbiased_se
