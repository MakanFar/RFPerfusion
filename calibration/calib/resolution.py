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

The slope enters that division SIGNED. Taking its magnitude would read
"confidence predicts inaccuracy" as though it were "confidence predicts
accuracy" and hand back a healthy-looking number, licensing the system to
rank candidates in precisely the wrong order.
"""

import math
import statistics

SLOPE_FLOOR = 0.7
MIN_ROWS = 8
# An absolute floor. Below this the metric moves outcome so little that the
# division manufactures an enormous "resolution" every gate trivially
# satisfies, however tightly the slope itself happens to be pinned.
MIN_SLOPE = 0.05
# Spec section 3.3 defines the refusal as "flat WITHIN NOISE", which is a
# statement about the slope relative to its own standard error rather than
# against any constant. Two standard errors is the usual "distinguishable
# from zero" bar; MIN_SLOPE and this test catch different failures, so both
# are applied.
SE_MULTIPLE = 2.0
# avg_plddt lives on [0.0, 1.0] (the catalogue's declared range). A claimed
# resolution approaching the metric's own range is not a resolution: it says
# no two values of the metric can be told apart, which is a refusal, not an
# enormous measured_error that every gate satisfies by construction.
MAX_RESOLUTION = 0.3


def in_band(rows, slope_floor=SLOPE_FLOOR):
    """The rows that actually enter the fit.

    Exposed because the proposal must describe the set it measured on, not
    the set it was handed: rows below the floor are never fitted, so their
    lengths do not belong in the applicability domain.
    """
    return [r for r in rows if r["avg_plddt"] >= slope_floor]


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
    """Rank correlation, with TIED ranks averaged.

    Breaking ties by input order manufactures a within-group correlation out
    of nothing but row ordering, and it can invert the reported sign. This
    figure is the human promoter's independent check on direction, so a sign
    it can get wrong is worse than no figure at all.
    """
    def ranks(vs):
        order = sorted(range(len(vs)), key=lambda i: vs[i])
        r = [0.0] * len(vs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vs[order[j + 1]] == vs[order[i]]:
                j += 1
            shared = (i + j) / 2.0
            for k in range(i, j + 1):
                r[order[k]] = shared
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    slope, _ = _linfit(rx, ry)
    sdx, sdy = statistics.pstdev(rx), statistics.pstdev(ry)
    return 0.0 if sdx == 0 or sdy == 0 else slope * sdx / sdy


def measure(rows, slope_floor=SLOPE_FLOOR):
    """Resolution of the metric, in metric units, or a refusal."""
    used = in_band(rows, slope_floor)
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

    def refuse(reason):
        return {"ok": False, "n": n, "slope": slope,
                "sd_resid": sd_resid, "reason": reason}

    if slope < 0:
        return refuse(
            f"slope {slope:.4f} is negative: accuracy FALLS as confidence "
            f"rises, so the metric is anti-predictive on this set. Its "
            f"magnitude is not a resolution -- promoting on it would license "
            f"ranking candidates in exactly the wrong order")

    if slope < MIN_SLOPE:
        return refuse(
            f"slope {slope:.4f} is below the floor {MIN_SLOPE}; the metric "
            f"does not discriminate on this set, so its resolution is "
            f"undefined and it must not be promoted")

    mx = statistics.fmean(xs)
    sxx = sum((x - mx) ** 2 for x in xs)
    se = sd_resid / math.sqrt(sxx) if sxx > 0 else float("inf")
    if slope < SE_MULTIPLE * se:
        return refuse(
            f"slope {slope:.4f} is flat within noise: below {SE_MULTIPLE:g}x "
            f"its own standard error {se:.4f}, so it is not distinguishable "
            f"from zero and the resolution it implies is not measured")

    measured_error = sd_resid / slope
    if measured_error > MAX_RESOLUTION:
        return refuse(
            f"resolution {measured_error:.4f} exceeds the {MAX_RESOLUTION} "
            f"bound: a figure approaching the metric's own [0.0, 1.0] range "
            f"says no two values can be told apart, which is a refusal rather "
            f"than a measured error")

    return {"ok": True, "measured_error": measured_error, "n": n,
            "slope": slope, "sd_resid": sd_resid,
            "spearman": _spearman(xs, ys)}
