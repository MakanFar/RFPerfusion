"""proto-tools catalogue: sync and constraint parsing.

Constraints are parsed from the registry's own docs rather than hand-written,
so `proto-sync` can be re-run when the catalogue moves. Anything that cannot
be parsed stays None and is treated as UNKNOWN downstream -- never as
satisfied.
"""

import json
import re
import subprocess

PROTEIN_ALPHABET = "ACDEFGHIKLMNPQRSTVWYXBZUO"
NUCLEOTIDE_ALPHABET = "ACGTUN"

_LENGTH_PATTERNS = (
    re.compile(r"must not exceed\s+([\d,]+)"),
    re.compile(r"<=\s*([\d,]+)\s*residues"),
    re.compile(r"≤\s*([\d,]+)\s*residues"),
)
_ENTITY_TYPES = re.compile(r"entity types:\s*(.+)")
_FIELD_LINE = re.compile(r"^  (?P<name>[a-z_]+)\s{2,}(?P<type>\S.*?)\s{2,}\(")

_STRUCTURE_HINTS = ("structure", "pdb", "sequence_structure_pairs")


def parse_input_doc(text):
    """Extract machine-checkable constraints from `proto-tools input <key>`."""
    max_length = None
    for pattern in _LENGTH_PATTERNS:
        m = pattern.search(text)
        if m:
            max_length = int(m.group(1).replace(",", ""))
            break

    molecules = None
    m = _ENTITY_TYPES.search(text)
    if m:
        found = re.findall(r"protein|dna|rna|ligand", m.group(1).lower())
        molecules = sorted(set(found)) or None
    elif re.search(r"only supports protein sequences", text):
        molecules = ["protein"]

    fields = [(m.group("name"), m.group("type"))
              for m in (_FIELD_LINE.match(line) for line in text.splitlines()) if m]
    input_kind = None
    for name, type_ in fields:
        blob = f"{name} {type_}".lower()
        if any(h in blob for h in _STRUCTURE_HINTS):
            input_kind = "structure"
            break
        if "sequence" in blob:
            input_kind = "sequence"
            break
        if "complex" in blob:
            input_kind = "complex"
            break

    if molecules == ["protein"]:
        alphabet = PROTEIN_ALPHABET
    elif molecules and set(molecules) <= {"dna", "rna"}:
        alphabet = NUCLEOTIDE_ALPHABET
    else:
        alphabet = None

    return {
        "input_kind": input_kind,
        "molecules": molecules,
        "alphabet": alphabet,
        "max_length": max_length,
        "constraint_source": "docstring",
    }


def build_catalog(tools, doc_fetcher):
    """tools: parsed `proto-tools list --json`. doc_fetcher: key -> input doc."""
    entries = []
    for t in tools:
        parsed = parse_input_doc(doc_fetcher(t["key"]))
        entries.append({
            "key": t["key"],
            "category": t.get("category"),
            "uses_gpu": t.get("uses_gpu"),
            # measures/status are curated by hand -- proto-tools cannot supply
            # them, and framework §6 forbids ranking on an uncalibrated tool.
            "measures": [],
            "status": "needs_calibration",
            **parsed,
        })
    return {"tools": entries, "n_tools": len(entries)}


def fetch_tools(project="../proto"):
    out = subprocess.run(
        ["uv", "run", "--project", project, "proto-tools", "list", "--json"],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out[out.index("["):out.rindex("]") + 1])


def fetch_input_doc(key, project="../proto"):
    return subprocess.run(
        ["uv", "run", "--project", project, "proto-tools", "input", key],
        capture_output=True, text=True).stdout


_SEQUENCE_KINDS = ("sequence", "subsequence")


def check(artifact, tool):
    """Three-valued constraint check. `unknown` NEVER counts as `pass` --
    failing open would silently reintroduce unusable artifacts."""
    checks = {}

    kind = tool.get("input_kind")
    if kind is None:
        checks["input_kind"] = "unknown"
    elif kind in ("sequence", "complex"):
        checks["input_kind"] = f"pass tool takes a {kind}"
    else:
        checks["input_kind"] = f"fail tool needs a {kind}, artifact is a sequence"

    molecules = tool.get("molecules")
    if molecules is None:
        checks["molecule"] = "unknown"
    elif artifact["molecule"] in molecules:
        checks["molecule"] = f"pass {artifact['molecule']}"
    else:
        checks["molecule"] = f"fail tool accepts {molecules}, artifact is {artifact['molecule']}"

    alphabet = tool.get("alphabet")
    if alphabet is None:
        checks["alphabet"] = "unknown"
    else:
        bad = sorted(set(artifact["value"].upper()) - set(alphabet))
        checks["alphabet"] = "pass" if not bad else f"fail illegal characters {bad}"

    cap = tool.get("max_length")
    if cap is None:
        checks["max_length"] = "unknown"
    elif artifact["length"] <= cap:
        checks["max_length"] = f"pass {artifact['length']}<={cap}"
    else:
        checks["max_length"] = f"fail {artifact['length']}>{cap}"

    return checks


def bind_artifact(artifact, catalog):
    """Bind one artifact to every tool that accepts it."""
    accepted, rejected, unverified = [], [], []
    for tool in catalog["tools"]:
        if artifact["kind"] not in _SEQUENCE_KINDS:
            continue
        checks = check(artifact, tool)
        failed = [k for k, v in checks.items() if v.startswith("fail")]
        unknown = [k for k, v in checks.items() if v == "unknown"]
        if failed:
            rejected.append({"key": tool["key"], "failed": failed[0],
                             "detail": checks[failed[0]]})
        elif unknown:
            unverified.append({"key": tool["key"], "checks": checks,
                               "unknown": unknown})
        else:
            accepted.append({"key": tool["key"], "checks": checks})

    if accepted:
        status = "runnable"
    elif unverified:
        status = "unverified"
    else:
        status = "rejected"
    return {"status": status, "tools": accepted,
            "unverified": unverified, "rejected_by": rejected}
