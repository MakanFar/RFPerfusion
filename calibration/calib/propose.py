"""Building the curation fragment a human pastes into calibration.json.

This module deliberately stops at a proposal. `registry/calibration.json` is
curated, never generated -- that separation is what makes the overlay
trustworthy, and framework section 11's "who may promote" question is still
open, so a script must not answer it by writing the file.
"""

from . import resolution

# The smallest positive value the four-decimal record can express. A fit
# tighter than that rounds to 0.0, which `apply_calibration` refuses for
# being non-positive -- so an unusually good measurement would round itself
# out of the promotion it earned.
MIN_RECORDED_ERROR = 0.0001

# "Held out" here rests on release date alone. A post-cutoff entry can still
# be a point mutant or a close homolog of a pre-cutoff structure whose
# sequence ESMFold saw, so the set is not guaranteed novel to the model and
# the resolution can come out finer than earned. Recorded rather than
# screened for: a homology screen is real work and its absence must not be
# invisible behind `held_out: true`.
NO_HOMOLOGY_SCREEN = (
    "held-out rests on the release date alone; no homology screen against "
    "pre-cutoff structures was performed, so a post-cutoff point mutant or "
    "close homolog of a training structure may remain in the set and would "
    "bias the resolution finer than earned"
)


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
                             "sd_resid": round(fit["sd_resid"], 4),
                             # Where the slope was taken, and over how many
                             # chains: `measured_error.n` counts rows IN the
                             # band, which is not the size of the benchmark.
                             "slope_band": [resolution.SLOPE_FLOOR, 1.0],
                             "n_chains_measured": len(rows)}
    benchmark.setdefault("limitations", NO_HOMOLOGY_SCREEN)

    # The domain describes where the number was MEASURED. Rows below the
    # slope floor never entered the fit, so their lengths would stretch the
    # claim over a regime nothing was measured in.
    lengths = [r.get("length") for r in resolution.in_band(rows)
               if r.get("length")]
    return {
        "promoted": True,
        tool: {"metrics": {metric: {
            "status": "validated",
            "measured_error": {
                "kind": "resolution",
                "value": max(round(fit["measured_error"], 4),
                             MIN_RECORDED_ERROR),
                "n": fit["n"]},
            "benchmark": benchmark,
            "applicability_domain": {
                "molecules": ["protein"],
                "length": [min(lengths), max(lengths)] if lengths else None,
                "notes": "single chains only; measured on this benchmark set",
            },
        }}},
    }
