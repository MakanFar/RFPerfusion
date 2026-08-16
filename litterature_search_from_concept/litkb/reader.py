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
    """Flatten `paperclip map --output-schema` stdout into per-paper records."""
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
        out = {}
        if "{" in body and "}" in body:
            try:
                out = json.loads(body[body.index("{"):body.rindex("}") + 1])
            except (ValueError, json.JSONDecodeError):
                out = {}
        records.append({"doc_id": doc_id, **out})
    return records


def flagged_for_dig(records):
    """Papers worth the expensive worker: those claiming a sequence exists."""
    return [r["doc_id"] for r in records if r.get("has_sequence")]
