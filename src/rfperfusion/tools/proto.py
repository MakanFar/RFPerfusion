"""Bridge to the isolated `proto/` proto-tools runtime.

proto-tools wraps ~56 comp-bio models (ESM2/3, ESMFold, ProteinMPNN, PyRosetta,
DSSP, FoldSeek, ...) behind a uniform `run_<tool>(Input, Config)` API and offloads
heavy compute to Modal GPUs. It lives in its own uv venv (Python 3.12) so its
heavy/conflicting deps never touch the main app.

DISCOVERY (list/schema/example) is free and offline-ish -> exposed here.
EXECUTION on Modal is BILLABLE and a tool must be DEPLOYED first (deploy = also
billable). We NEVER auto-deploy; `run_tool` refuses unless allow_deploy=True.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from ..config import PROTO_PROJECT

_UV = ["uv", "run", "--project", str(PROTO_PROJECT)]


def _proto_tools(args: list[str], timeout: int = 300) -> str:
    proc = subprocess.run(
        [*_UV, "proto-tools", *args],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"proto-tools {' '.join(args)} failed:\n{proc.stderr.strip()}")
    return proc.stdout


# --- Discovery (free) ------------------------------------------------------ #
def doctor() -> str:
    return _proto_tools(["doctor"])


def list_tools(category: Optional[str] = None) -> str:
    args = ["list"]
    if category:
        args += ["--category", category]
    return _proto_tools(args)


def schema(tool_key: str) -> dict:
    return json.loads(_proto_tools(["schema", tool_key, "--json"]))


def example_input(tool_key: str) -> dict:
    return json.loads(_proto_tools(["example-input", tool_key, "--json"]))


def signature(tool_key: str) -> str:
    return _proto_tools(["signature", tool_key])


def deployed_count() -> tuple[int, int]:
    """(#deployed, #total) parsed from `doctor`."""
    for line in doctor().splitlines():
        if line.strip().startswith("apps deployed"):
            frag = line.split(":", 1)[1].strip()          # "0 of 56"
            a, _, b = frag.split()
            return int(a), int(b)
    return (0, 0)


# --- Execution (BILLABLE) -------------------------------------------------- #
def run_tool(
    tool_key: str,
    payload: dict,
    output_dir: Path,
    *,
    allow_deploy: bool = False,
    run_on: str = "modal",
    timeout: int = 1800,
) -> dict:
    """Run a proto-tools tool via a runner script inside the proto venv.

    Refuses to execute unless allow_deploy=True, because a first run of an
    undeployed tool triggers a billable Modal deploy. Pass allow_deploy=True
    only after the human has approved the specific tool+cost.
    """
    if not allow_deploy:
        raise PermissionError(
            f"run_tool('{tool_key}') blocked: execution/deploy on Modal is billable. "
            f"Approve the specific tool, then call with allow_deploy=True."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    runner = PROTO_PROJECT / "_run_tool.py"  # written by scripts/setup, see docs
    req = {"tool_key": tool_key, "payload": payload,
           "output_dir": str(output_dir), "run_on": run_on}
    proc = subprocess.run(
        [*_UV, "python", str(runner)],
        input=json.dumps(req), capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"proto run_tool '{tool_key}' failed:\n{proc.stderr.strip()}")
    return json.loads(proc.stdout)
