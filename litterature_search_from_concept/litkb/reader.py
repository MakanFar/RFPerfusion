"""Full-text reading via `paperclip map`.

Two tiers: `structured-extraction` sweeps every paper for mechanisms and flags
which ones claim sequences; `exhaustive-extraction` re-reads only the flagged
ones, where it can reach methods, tables and supplements.

Schemas are strict -- additionalProperties false, explicit required -- so a
paper that cannot produce valid output fails loudly instead of degrading.
"""

import json
import re

SCREEN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["mechanisms", "has_sequence", "sequence_location", "named_proteins"],
    "properties": {
        "mechanisms": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["chain", "claim", "measurable_properties"],
                "properties": {
                    "chain": {"type": "string"},
                    "claim": {"type": "string"},
                    "measurable_properties": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "has_sequence": {"type": "boolean"},
        "sequence_location": {
            "type": "string",
            "enum": ["supplementary", "methods", "figure", "none"],
        },
        "named_proteins": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "accession"],
                "properties": {
                    "name": {"type": "string"},
                    "accession": {"type": ["string", "null"]},
                },
            },
        },
    },
}

SCREEN_QUERY = (
    "What physical mechanism does this paper establish for actuating a protein, "
    "and what property of a designed protein would have to be measured to test it? "
    "Does the paper report an explicit amino-acid or nucleotide sequence, and where "
    "(supplementary, methods, figure)? Name every protein it characterises."
)


# Confirmed shape (paperclip CLI, live run against PMC6200754, worker
# quick-reader with --output-schema; see task-5-report.md Step 5 for the
# exact command and raw bytes): `paperclip map` does NOT return a JSON
# envelope at all -- stdout is the same human-formatted text style used
# by `search`/`grep`. There is no top-level `{"results": [...]}` object;
# the assumed shape was wrong in kind, not just in key names. Each paper
# is a block:
#
#     Map complete: 1/1 papers
#     Results ID: m_7b867fc1
#
#       ✓ An open quantum system approach to the radical pair mechanism
#         PMC6200754 · 2594ms
#         {"has_sequence":false}
#
#     Tip: These per-paper answers are ready to use -- synthesize them to respond.
#     [4.0s, saved to m_7b867fc1]
#
# i.e. a title line, then a "<doc_id> · <n>ms" line, then the schema'd
# JSON payload (compact, one line per case observed) up to the next blank
# line. `parse_map_output` locates the doc_id line by its "<n>ms" timing
# suffix (robust to whatever separator character sits between doc_id and
# timing) and treats everything up to the next blank line as the payload.
_TIMING_LINE_RE = re.compile(r"^\s*(?P<doc_id>\S+)\s+\S+\s+\d+ms\s*$")


def parse_map_output(raw):
    """Flatten `paperclip map --output-schema` stdout into per-paper records.

    A paper whose payload has no braces, or fails to parse, is NOT silently
    folded into an empty `{}` -- that would be indistinguishable from "the
    LLM validly reported nothing" and would vanish from `flagged_for_dig`
    without a trace, contradicting this module's fail-loudly design. Instead
    such a paper gets `extraction_failed: True` plus a `raw` snippet, and is
    countable via `failed_extractions`.
    """
    records = []
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        m = _TIMING_LINE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        doc_id = m.group("doc_id")
        i += 1
        body_lines = []
        while i < len(lines) and lines[i].strip():
            body_lines.append(lines[i])
            i += 1
        body = "\n".join(body_lines)
        out = None
        if "{" in body and "}" in body:
            try:
                out = json.loads(body[body.index("{"):body.rindex("}") + 1])
            except (ValueError, json.JSONDecodeError):
                out = None
        if out is None:
            records.append({"doc_id": doc_id, "extraction_failed": True,
                            "raw": body[:300]})
        else:
            records.append({"doc_id": doc_id, "extraction_failed": False, **out})
    return records


def flagged_for_dig(records):
    """Papers worth the expensive worker: those claiming a sequence exists.

    A record with `extraction_failed: True` has no `has_sequence` key, so it
    is excluded here too -- a failed read never auto-triggers tier-2 spend.
    See `failed_extractions` to surface it instead of losing it silently.
    """
    return [r["doc_id"] for r in records if r.get("has_sequence")]


def failed_extractions(records):
    """Papers whose screen output could not be parsed. Never silently
    folded into "no sequence" -- a failed read is not a negative result."""
    return [r["doc_id"] for r in records if r.get("extraction_failed")]


DIG_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sequences", "mutations"],
    "properties": {
        "sequences": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["value", "molecule", "name", "region", "where", "verbatim"],
                "properties": {
                    "value": {"type": "string"},
                    "molecule": {"type": "string", "enum": ["protein", "dna", "rna"]},
                    "name": {"type": ["string", "null"]},
                    "region": {"type": ["array", "null"], "items": {"type": "integer"}},
                    "where": {"type": "string"},
                    "verbatim": {"type": "boolean"},
                },
            },
        },
        "mutations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["parent", "mutation", "effect"],
                "properties": {
                    "parent": {"type": "string"},
                    "mutation": {"type": "string"},
                    "effect": {"type": "string"},
                },
            },
        },
    },
}

DIG_QUERY = (
    "Extract every explicit amino-acid or nucleotide sequence in this paper, "
    "including supplementary tables and figure captions. Copy each sequence "
    "character for character from the source. If you cannot copy it exactly -- "
    "if you would have to reconstruct, translate, or infer it -- set verbatim "
    "to false. Do not produce a sequence that is not written in the paper. "
    "Also list every point mutation and the effect the paper attributes to it."
)


def confirm_in_source(artifact, grep_fn, literal=False):
    """Re-grep an extracted sequence against its own source document.

    An LLM asked for a sequence will produce a plausible one, and a fabricated
    sequence passes every alphabet and length check perfectly. This is the only
    check that distinguishes real from well-formed.

    `literal` tells this function what kind of matching `grep_fn` actually
    performed -- it cannot infer that from the hits alone, so the caller must
    assert it:

    - `literal=True`: the caller ran a fixed-string grep (e.g.
      `grep_set(..., fixed=True)`, i.e. `paperclip grep -F`). A hit whose
      `doc_id` matches the claimed document is trusted outright -- `-F`
      already guarantees the matched span equals the pattern byte for byte.
      We deliberately do NOT also require `artifact["value"] in h["text"]`
      here: confirmed live (art_001, TAGTTCCTTCTTTCAGCAGTTT in PMC2040520),
      `paperclip grep`'s `text` field is a truncated, elided DISPLAY SNIPPET
      that can come from a different paragraph than the actual match --
      not an authoritative carrier of the matched span. Requiring the
      substring there produced false rejections of genuinely present
      sequences.
    - `literal=False` (default): grep_fn's matching mode is unknown or
      regex-based, so the grep itself cannot be trusted -- a sequence
      containing `*` (stop codon) or `.` (masked/ambiguous residue) is not
      a literal string and could match text that is not actually the
      sequence. As a conservative fallback we additionally require
      `artifact["value"] in h["text"]`, accepting that this will sometimes
      false-reject a real match (per the truncation issue above) in
      exchange for never false-confirming a fabricated one.
    """
    if not artifact.get("verbatim"):
        return False
    hits = grep_fn(artifact["provenance"]["set_id"], [artifact["value"]])
    if literal:
        return any(h["doc_id"] == artifact["provenance"]["doc_id"] for h in hits)
    return any(h["doc_id"] == artifact["provenance"]["doc_id"] and
               artifact["value"] in h["text"] for h in hits)
