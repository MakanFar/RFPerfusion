"""Driving the proto tools for one benchmark chain.

`proto-tools` has no `run` verb -- it is discovery only. A tool call is a
Python import from inside the proto project's environment, so this module
shells out to `runner/run_chain.py` under `uv run --project ../proto python`
rather than importing proto_tools itself. That keeps proto_tools a run-time
prerequisite instead of an import dependency, which is what lets every test
here run offline with the runner faked.

The runner emits pure data. Every DECISION about that data lives here:
which of usalign's two normalisations is the real score, whether the entry
was single-chain, and whether the numbers are on the scale the catalogue
declares. A decision that lived in the runner could not be tested offline,
and a silent flip in it -- reference-normalised to query-normalised, say --
would produce plausible-looking numbers that are categorically wrong.
"""

import json
import subprocess
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
PROTO_PROJECT = str(_HERE.parent / "proto")
RUNNER = str(_HERE / "runner" / "run_chain.py")
# One ESMFold call on a cold GPU is minutes, not hours. Without a cap a hung
# call blocks the whole benchmark run with no ledger and no partial result.
TIMEOUT_S = 1800

# The catalogue declares both avg_plddt and the TM-scores on [0.0, 1.0]. A
# run that came back on the 0-100 scale would sail through the fit: the 0.7
# slope floor becomes a no-op, the slope shrinks 100x, and the harness
# reports "the metric does not discriminate" -- a units bug delivered as a
# scientific conclusion after the GPU spend.
METRIC_RANGE = (0.0, 1.0)


class DriverError(RuntimeError):
    pass


def _subprocess_runner(job):
    try:
        proc = subprocess.run(
            ["uv", "run", "--project", PROTO_PROJECT, "python", RUNNER],
            input=json.dumps(job), capture_output=True, text=True,
            timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise DriverError(
            f"{job.get('pdb_id', '?')}: runner timed out after {TIMEOUT_S}s"
        ) from exc
    if proc.returncode != 0:
        raise DriverError(f"runner exited {proc.returncode}: {proc.stderr[-2000:]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise DriverError(
            f"{job.get('pdb_id', '?')}: runner exited 0 but stdout was not "
            f"JSON ({exc}): {proc.stdout[-2000:]}") from exc


def _number(pdb_id, result, field):
    """A present, numeric field, or a DriverError naming what was seen."""
    if field not in result:
        raise DriverError(
            f"{pdb_id}: runner reported no {field}; the row is incomplete "
            f"and must not enter the fit")
    value = result[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DriverError(
            f"{pdb_id}: {field} is {value!r}, which is not a number")
    return value


def _in_metric_range(pdb_id, result, field):
    value = _number(pdb_id, result, field)
    lo, hi = METRIC_RANGE
    if not lo <= value <= hi:
        raise DriverError(
            f"{pdb_id}: {field} is {value!r}, outside the declared range "
            f"[{lo}, {hi}]. A value on the 0-100 scale would pass the 0.7 "
            f"slope floor unnoticed and shrink the fitted slope 100x, so it "
            f"is refused rather than folded into the fit")
    return value


def measure_chain(pdb_id, runner=None):
    """One chain -> one (avg_plddt, tm_score) row.

    Raises rather than returning a partial row: a chain that failed to fold
    or align must not enter the fit as a zero, which would drag the slope
    toward flat and understate the metric's discrimination.
    """
    result = (runner or _subprocess_runner)({"pdb_id": pdb_id})
    if not result.get("ok"):
        raise DriverError(
            f"{pdb_id} failed at {result.get('stage', 'unknown')}: "
            f"{result.get('error', 'no error reported')}")

    n_chains = _number(pdb_id, result, "n_protein_chains")
    if n_chains != 1:
        raise DriverError(
            f"{pdb_id}: {n_chains} protein chains, not 1; the benchmark is "
            f"single-chain so the TM-score is unambiguous")

    # structure_2 is the REFERENCE, so this is the reference-normalised
    # TM-score -- "how much of the experimental structure did the model get
    # right". structure_1 normalises by the PREDICTION, which lets a
    # truncated model score well on the fragment it did predict.
    return {"pdb_id": pdb_id,
            "avg_plddt": _in_metric_range(pdb_id, result, "avg_plddt"),
            "tm_score": _in_metric_range(pdb_id, result, "tm_score_structure_2"),
            "length": _number(pdb_id, result, "query_length")}
