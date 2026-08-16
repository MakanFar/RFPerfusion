"""Thin wrapper over the `paperclip` CLI (a virtual filesystem of full-text
biomedical papers + protein DBs). Laptop-only, no Modal cost.

Deterministic helpers used by the Literature and Scaffold stages. For the
LLM-agent version, a literature worker calls the CLI itself via Bash; these
helpers give the deterministic driver the same reach.
"""

from __future__ import annotations

import json
import subprocess
from typing import Optional

BIN = "paperclip"
DEFAULT_TIMEOUT = 180


def _run(args: list[str], timeout: int = DEFAULT_TIMEOUT) -> str:
    proc = subprocess.run(
        [BIN, *args],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"paperclip {' '.join(args)} failed:\n{proc.stderr.strip()}")
    return proc.stdout


def search(query: str, source: str = "pmc", n: int = 8, extra: Optional[list[str]] = None) -> str:
    """Semantic + keyword search. Returns raw CLI output (result set + IDs)."""
    args = ["search", query, "-s", source, "-n", str(n)]
    if extra:
        args += extra
    return _run(args)


def search_proteins(query: str, n: int = 5) -> str:
    """Search UniProt/PDB/ChEMBL (the /proteins/ VFS)."""
    return search(query, source="proteins", n=n)


def cat(path: str) -> str:
    """Read a file in the paperclip VFS (e.g. /proteins/<ACC>/meta.json)."""
    return _run(["cat", path])


def grep(pattern: str, path: str, extra: Optional[list[str]] = None) -> str:
    args = ["grep", pattern, path]
    if extra:
        args += extra
    return _run(args)


def protein_meta(accession: str) -> dict:
    """Parse /proteins/<ACCESSION>/meta.json into a dict."""
    raw = cat(f"/proteins/{accession}/meta.json")
    return json.loads(raw)
