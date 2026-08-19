"""Composing selection, measurement and proposal into one run.

Without this the operator writes the glue at the console, and that glue holds
a decision nobody reviewed: `try/except: pass` around a failing chain drops
it silently. If failures correlate with anything -- long chains, ESMFold OOM,
obsoleted PDB entries -- the surviving set is no longer the set that was
selected and nothing records the difference. `benchmark.select` names every
rejection so the set can be audited; a chain lost AFTER selection is exactly
as capable of biasing the resolution, so it is named too.

The writer writes under `calibration/out/` and nowhere else. It never touches
`registry/calibration.json`: that file is curated, a human promotes into it,
and framework section 11's "who may promote" is still open -- a script must
not answer it by writing the file.
"""

import csv
import json
from pathlib import Path

from . import driver, propose

OUT_DIR = Path(__file__).resolve().parent.parent / "out"

CSV_COLUMNS = ("pdb_id", "length", "avg_plddt", "tm_score")


def measure_all(pdb_ids, runner=None, measure=None):
    """Measure every id. Returns `(rows, exclusions)`.

    Only `DriverError` becomes an exclusion. Anything else is a defect in the
    harness rather than a fact about a chain, and laundering it into the
    ledger would report a bug as a property of the benchmark.
    """
    measure = measure or driver.measure_chain
    rows, exclusions = [], []
    for pdb_id in pdb_ids:
        try:
            rows.append(measure(pdb_id, runner=runner))
        except driver.DriverError as exc:
            exclusions.append({"pdb_id": pdb_id, "reason": str(exc)})
    return rows, exclusions


def write_proposal(tool, metric, rows, exclusions, benchmark_meta,
                   out_dir=None):
    """Write the proposal and the raw measurements. Returns their paths.

    A refusal is written too: "no promotion" is a real outcome of the design,
    not an error, and it leaves the same audit trail as a promotion.
    """
    out_dir = Path(out_dir) if out_dir is not None else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = dict(benchmark_meta)
    meta["exclusions"] = list(exclusions)
    document = propose.build(tool, metric, rows, meta)
    if not document.get("promoted"):
        # A refusal carries no benchmark block, so the ledger would vanish
        # with it. It is the half of the audit trail that survives either way.
        document["exclusions"] = list(exclusions)

    proposal = out_dir / f"proposed_{tool}_{metric}.json"
    proposal.write_text(json.dumps(document, indent=2) + "\n")

    measurements = out_dir / "measurements.csv"
    with measurements.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c) for c in CSV_COLUMNS})

    return {"proposal": proposal, "measurements": measurements}
