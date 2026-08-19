"""Building the curation fragment a human pastes into calibration.json.

This module deliberately stops at a proposal. `registry/calibration.json` is
curated, never generated -- that separation is what makes the overlay
trustworthy, and framework section 11's "who may promote" question is still
open, so a script must not answer it by writing the file.
"""

from . import resolution


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
                             "sd_resid": round(fit["sd_resid"], 4)}
    lengths = [r.get("length") for r in rows if r.get("length")]
    return {
        "promoted": True,
        tool: {"metrics": {metric: {
            "status": "validated",
            "measured_error": {"kind": "resolution",
                               "value": round(fit["measured_error"], 4),
                               "n": fit["n"]},
            "benchmark": benchmark,
            "applicability_domain": {
                "molecules": ["protein"],
                "length": [min(lengths), max(lengths)] if lengths else None,
                "notes": "single chains only; measured on this benchmark set",
            },
        }}},
    }
