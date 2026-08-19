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
