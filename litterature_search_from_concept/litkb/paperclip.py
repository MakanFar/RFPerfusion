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


def grep_set(set_id, patterns, ignore_case=False):
    """Multi-pattern OR grep over one saved set. Returns flat hit dicts."""
    args = ["grep", "--from", set_id, "-n"]
    if ignore_case:
        args.append("-i")
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
def map_papers(set_id, query, schema, worker="quick-reader", n=None,
               concurrency=32):
    """LLM read across a saved set. Server-side Claude -- no API key here."""
    args = ["map", "--from", set_id, "--worker", worker,
            "--output-schema", json.dumps(schema), "-j", str(concurrency)]
    if n:
        args += ["-n", str(n)]
    args.append(query)
    return _run(args)


def meta(doc_id):
    """Citation metadata for one document."""
    out = _run(["cat", f"/papers/{doc_id}/meta.json"])
    try:
        return json.loads(out[out.index("{"):out.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return {}
