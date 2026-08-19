"""Driving the proto tools for one benchmark chain.

`proto-tools` has no `run` verb -- it is discovery only. A tool call is a
Python import from inside the proto project's environment, so this module
shells out to `runner/run_chain.py` under `uv run --project ../proto python`
rather than importing proto_tools itself. That keeps proto_tools a run-time
prerequisite instead of an import dependency, which is what lets every test
here run offline with the runner faked.
"""

import json
import subprocess

PROTO_PROJECT = "../proto"
RUNNER = "runner/run_chain.py"


class DriverError(RuntimeError):
    pass


def _subprocess_runner(job):
    proc = subprocess.run(
        ["uv", "run", "--project", PROTO_PROJECT, "python", RUNNER],
        input=json.dumps(job), capture_output=True, text=True)
    if proc.returncode != 0:
        raise DriverError(f"runner exited {proc.returncode}: {proc.stderr[-2000:]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise DriverError(
            f"{job.get('pdb_id', '?')}: runner exited 0 but stdout was not "
            f"JSON ({exc}): {proc.stdout[-2000:]}") from exc


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
    return {"pdb_id": pdb_id,
            "avg_plddt": result["avg_plddt"],
            "tm_score": result["tm_score"],
            "length": result["length"]}
