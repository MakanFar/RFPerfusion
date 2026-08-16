"""Thin, deterministic wrapper around the `paperclip` CLI.

Everything here is plumbing: shell out, parse, return data. No judgement and
no LLM calls -- those belong to the agent driving these tools.

Verified against paperclip 0.7.36.
"""

import json
import re
import shutil
import subprocess

SET_ID_RE = re.compile(r"\b(s_[0-9a-f]{6,})\b")
FOUND_RE = re.compile(r"Found\s+(\d+)\s+papers")
DOC_RE = re.compile(r"^\s{2}(\S+?)/\s+\((\d+)\s+matches?\)\s*$")
TRUNC_RE = re.compile(r"^\s{4}\.\.\.\s*\+(\d+)\s+more\s*$")
HIT_RE = re.compile(r"^\s{4}(?:\[(?P<section>.*?)\]\s*)?(?P<text>.+)$")
NOMATCH_RE = re.compile(r"^No matches for ")


class PaperclipError(RuntimeError):
    pass


def _run(args):
    if shutil.which("paperclip") is None:
        raise PaperclipError(
            "`paperclip` is not on PATH. Install it, and note it needs "
            "Python >= 3.10 -- under 3.9 it fails at import."
        )
    p = subprocess.run(["paperclip", *args], capture_output=True, text=True)
    blob = p.stdout + p.stderr
    if "Not authenticated" in blob:
        raise PaperclipError("paperclip is not authenticated -- run `paperclip login`")
    # A crashed paperclip is indistinguishable from a genuine no-match unless
    # we check for this specifically. Confirmed live: under `uv run`,
    # paperclip's `#!/usr/bin/env python3` shebang picked up this project's
    # venv Python first on PATH, which doesn't have paperclip's own deps
    # installed, so it crashed at import with ModuleNotFoundError, printed a
    # traceback to stderr, produced EMPTY stdout, and exited 1 -- the same
    # code grep-style "no matches" uses. `_run` used to return that empty
    # stdout as-is, so a 23-phrase search silently reported 0 papers for
    # every phrase. A genuine "ran fine, matched nothing" result either has
    # something on stdout (e.g. "No matches for /.../ in s_xxx") or has no
    # stderr at all -- only a real crash produces nonzero exit + empty
    # stdout + nonempty stderr, so that combination is the signal to use.
    if p.returncode != 0 and not p.stdout and p.stderr:
        tail = p.stderr[-2000:]
        raise PaperclipError(
            f"paperclip {' '.join(args)} exited {p.returncode} with no "
            f"stdout and output on stderr -- this is a crash, not a "
            f"genuine no-match (stderr tail):\n{tail}"
        )
    # Exit 1 means "no results", as in grep. Anything higher is a real failure.
    if p.returncode > 1:
        raise PaperclipError(f"paperclip {' '.join(args)} failed ({p.returncode}):\n{blob}")
    return p.stdout


def count(phrase, sources="pmc", exact=False):
    """Papers matching a phrase, without saving a set.

    `exact=False` uses hybrid ranking. `exact=True` requires verbatim match."""
    args = ["search", "-s", sources, "-c"]
    if exact:
        args.append("-e")
    args.append(phrase)
    out = _run(args)
    m = FOUND_RE.search(out)
    return int(m.group(1)) if m else 0


def search(phrase, sources="pmc", n=100, exact=False):
    """One search. Returns its own set -- searches do not accumulate, and
    `paperclip merge` cannot union them.

    `exact=False` uses hybrid ranking. Curated keyword bags such as
    "CraCRY ODMR" are not phrases any author writes verbatim, so exact
    matching would return roughly nothing for them."""
    args = ["search", "-s", sources, "-n", str(n)]
    if exact:
        args.append("-e")
    args.append(phrase)
    out = _run(args)
    found = FOUND_RE.search(out)
    ids = SET_ID_RE.findall(out)
    return {"phrase": phrase, "set_id": ids[0] if ids else None,
            "n_papers": int(found.group(1)) if found else 0}


def grep_set(set_id, patterns, ignore_case=False, fixed=False):
    """Multi-pattern OR grep over one saved set. Returns flat hit dicts."""
    args = ["grep", "--from", set_id, "-n"]
    if ignore_case:
        args.append("-i")
    if fixed:
        args.append("-F")
    for p in patterns:
        args += ["-e", p]
    out = _run(args)

    hits, doc_id, current = [], None, None
    for line in out.splitlines():
        if not line.strip() or NOMATCH_RE.match(line):
            continue
        m = DOC_RE.match(line)
        if m:
            doc_id, current = m.group(1), None
            continue
        m = TRUNC_RE.match(line)
        if m:
            if hits and hits[-1]["doc_id"] == doc_id:
                hits[-1]["truncated_after"] = int(m.group(1))
            current = None
            continue
        m = HIT_RE.match(line)
        if m and doc_id:
            current = {
                "doc_id": doc_id,
                "set_id": set_id,
                "section": m.group("section"),
                "text": m.group("text").strip(),
                "truncated_after": 0,
            }
            hits.append(current)
            continue
        # Anything else is a wrapped continuation of the hit above it.
        if current is not None:
            current["text"] += " " + line.strip()
    return hits


# Default is "quick-reader", not "structured-extraction", even though the
# latter is the tier this module's callers conceptually want. Confirmed live
# (see litkb/reader.py and task-5-report.md Step 5): every non-default worker
# -- structured-extraction, exhaustive-extraction, eligibility-screen -- is
# currently gated to GXL testers on this account and fails fast with
# "[error] Parallel map workers are currently limited to GXL testers" before
# reading a single paper. quick-reader is the only worker this account can
# run, and it does support --output-schema. Pass worker= explicitly to use a
# gated tier once account access allows it -- this default should revert to
# "structured-extraction" the moment that's true, and nothing else here needs
# to change.
def map_papers(set_id, query, schema, worker="quick-reader", n=None):
    """LLM read across a saved set. Server-side Claude -- no API key here."""
    # No -j here on purpose. Confirmed live that passing -j at ANY value
    # triggers the "[error] Parallel map workers are currently limited to
    # GXL testers" gate on this account, regardless of --worker:
    #   map --from S --output-schema ... -n 1 "q"                     -> rc=0, works
    #   map --from S --output-schema ... -n 1 --worker quick-reader "q" -> rc=0, works
    #   map --from S --output-schema ... -n 1 -j 32 "q"                -> rc=1, gated
    # So concurrency is left at whatever the server defaults to -- there is
    # no parameter for it.
    args = ["map", "--from", set_id, "--worker", worker,
            "--output-schema", json.dumps(schema)]
    if n:
        args += ["-n", str(n)]
    args.append(query)
    out = _run(args)
    # `_run` treats exit 1 as "no matches" and returns stdout as-is -- but a
    # gate error also exits 1, with its message on stderr, so a gated call
    # looks identical to a legitimate empty sweep unless we check for the map
    # header we've actually observed on every successful run ("Map complete:
    # N/M papers" -- see task-5-report.md Step 5 for the captured bytes).
    if "Map complete" not in out:
        raise PaperclipError(
            f"`paperclip map --worker {worker}` produced no map output "
            '(no "Map complete" header in stdout). Only that fact is known '
            "-- not why. Plausible causes: the -j gate (see comment above), "
            "a genuinely gated worker such as structured-extraction, or an "
            "unrelated paperclip failure. This message does not assert "
            "which one occurred."
        )
    return out


def meta(doc_id):
    """Citation metadata for one document."""
    out = _run(["cat", f"/papers/{doc_id}/meta.json"])
    try:
        return json.loads(out[out.index("{"):out.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return {}
