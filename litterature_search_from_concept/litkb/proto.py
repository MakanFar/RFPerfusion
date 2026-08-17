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
_ENTITY_IN_DESC = re.compile(r"protein|dna|rna|ligand")


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


def _walk_properties(node):
    """Yield (name, subschema) for every property in a schema and its $defs."""
    for name, sub in (node.get("properties") or {}).items():
        yield name, sub
    for sub in (node.get("$defs") or {}).values():
        yield from _walk_properties(sub)


def parse_input_schema(schema):
    """Machine-checkable constraints from `proto-tools schema <key>`.

    Structured, so this is preferred over the prose input doc wherever it
    answers. It does not answer everything: caps stated only in a docstring
    Note (ESMFold's 2,400 residues) are invisible here, which is what
    `merge_constraints` is for.
    """
    inputs = schema.get("inputs") or {}
    fields = list(_walk_properties(inputs))
    names = {name for name, _ in fields}

    if "complexes" in names:
        input_kind = "complex"
    elif any("structure" in n or n == "sequence_structure_pairs" for n in names):
        input_kind = "structure"
    elif any("sequence" in n for n in names):
        input_kind = "sequence"
    else:
        input_kind = None

    molecules = None
    for name, sub in fields:
        if name == "entity_type":
            found = _ENTITY_IN_DESC.findall((sub.get("description") or "").lower())
            if found:
                molecules = sorted(set(found))
                break

    max_length = None
    for name, sub in fields:
        if "sequence" in name.lower():
            cap = sub.get("maxLength") or (sub.get("items") or {}).get("maxLength")
            if cap:
                max_length = int(cap)
                break

    if molecules == ["protein"]:
        alphabet = PROTEIN_ALPHABET
    elif molecules and set(molecules) <= {"dna", "rna"}:
        alphabet = NUCLEOTIDE_ALPHABET
    else:
        alphabet = None

    return {"input_kind": input_kind, "molecules": molecules,
            "alphabet": alphabet, "max_length": max_length}


_CONSTRAINT_FIELDS = ("input_kind", "molecules", "alphabet", "max_length")


def merge_constraints(from_schema, from_doc):
    """Schema first, prose only where the schema is silent.

    `constraint_source` becomes a list naming every source that actually
    contributed a value, so a thin entry is traceable to why it is thin
    rather than merely looking neglected.
    """
    merged, sources = {}, []
    for field in _CONSTRAINT_FIELDS:
        if from_schema.get(field) is not None:
            merged[field] = from_schema[field]
            if "schema" not in sources:
                sources.append("schema")
        elif from_doc.get(field) is not None:
            merged[field] = from_doc[field]
            if "docstring" not in sources:
                sources.append("docstring")
        else:
            merged[field] = None
    merged["constraint_source"] = sources
    return merged


CATALOG_SCHEMA_VERSION = 2


def build_catalog(tools, doc_fetcher, schema_fetcher, output_fetcher):
    """tools: parsed `proto-tools list --json`.

    Three sources now, in descending order of trustworthiness: the JSON
    Schema, the metric-spec table, and the prose input doc. `measures` is
    derived rather than curated -- the previous hand-curated column was
    empty for all 140 tools, which made `resolve_properties` a check that
    could not return false.
    """
    entries, failures = [], []
    for t in tools:
        key = t["key"]
        constraints = merge_constraints(
            parse_input_schema(schema_fetcher(key)),
            parse_input_doc(doc_fetcher(key)),
        )
        parsed_metrics = parse_metrics_doc(output_fetcher(key))
        failures.extend({"key": key, "line": line}
                        for line in parsed_metrics["failures"])
        entries.append({
            "key": key,
            "category": t.get("category"),
            "uses_gpu": t.get("uses_gpu"),
            "measures": parsed_metrics["measures"],
            # Derived capability, never calibration: framework section 6
            # still forbids ranking on an uncalibrated tool.
            "status": "needs_calibration",
            **constraints,
        })
    return {"schema_version": CATALOG_SCHEMA_VERSION, "tools": entries,
            "n_tools": len(entries), "parse_failures": failures}


def fetch_tools(project="../proto"):
    out = subprocess.run(
        ["uv", "run", "--project", project, "proto-tools", "list", "--json"],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out[out.index("["):out.rindex("]") + 1])


def fetch_input_doc(key, project="../proto"):
    return subprocess.run(
        ["uv", "run", "--project", project, "proto-tools", "input", key],
        capture_output=True, text=True).stdout


def fetch_schema(key, project="../proto"):
    out = subprocess.run(
        ["uv", "run", "--project", project, "proto-tools", "schema", key],
        capture_output=True, text=True).stdout
    try:
        return json.loads(out[out.index("{"):out.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return {}


def fetch_output_doc(key, project="../proto"):
    return subprocess.run(
        ["uv", "run", "--project", project, "proto-tools", "output", key],
        capture_output=True, text=True).stdout


def load_catalog(path):
    """Read a registry, refusing anything but the current schema version.

    Coercing a v1 registry would silently reinstate the empty `measures`
    column this work exists to remove, and a silently mis-read constraint
    is exactly the fail-open behaviour `check()` refuses.
    """
    with open(path) as fh:
        catalog = json.load(fh)
    version = catalog.get("schema_version")
    if version != CATALOG_SCHEMA_VERSION:
        raise ValueError(
            f"{path}: schema_version {version!r}, expected "
            f"{CATALOG_SCHEMA_VERSION}. Regenerate with `litkb proto-sync`."
        )
    return catalog


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
        checks["input_kind"] = f"fail tool needs a {kind}, artifact is a {artifact['kind']}"

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
    if artifact["kind"] not in _SEQUENCE_KINDS:
        return {"status": "unsupported_kind", "tools": [], "unverified": [],
                "rejected_by": [], "reason": f"no proto tool consumes a bare {artifact['kind']}"}

    accepted, rejected, unverified = [], [], []
    for tool in catalog["tools"]:
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


def resolve_properties(properties, catalog):
    """Map measurable properties onto tools that measure them.

    Framework §77: a class nothing can evaluate returns
    requires_new_evaluator, which is a legitimate output to hand back to the
    scientist rather than a discard."""
    wanted = set(properties or [])
    tools = sorted(t["key"] for t in catalog["tools"]
                   if wanted & set(t.get("measures") or []))
    return {"tools": tools, "requires_new_evaluator": not tools}


# `proto-tools output <key>` renders each tool's declarative `metric_spec`
# as a fixed-width table. It is a rendering of structured data, not free
# prose, which is why it is worth parsing -- unlike the input docs, whose
# phrasing varies per author.
# The `(per X item)` suffix is optional -- bindcraft-design emits a bare
# `Metrics:`.
_METRICS_HEADER = re.compile(r"^Metrics(?: \(per (.+?) item\))?:\s*$")
_METRIC_ROW = re.compile(
    # Uppercase is legal in a metric name: `dG`, `dG_per_dSASA` are real.
    r"^  (?P<name>[A-Za-z_][A-Za-z0-9_]*)\s{2,}"
    r"(?P<type>[^,]+?),\s*"
    r"range \[(?P<lo>[^,\]]+),\s*(?P<hi>[^\]]+)\],\s*"
    # Between the range and `better=` there is either an availability phrase
    # ("always", "when include_pae_matrix=True"), a unit ("REU", "Å^2"), or
    # BOTH ("%, always"). Captured whole and split below rather than guessed
    # at here.
    r"(?P<notes>.+?),\s*"
    # "context-dependent" is the literal spelling. Matching only "context"
    # fails the whole row, silently dropping 72 of the 311 rows in the
    # current catalogue.
    r"better=(?P<better>higher|lower|context-dependent)"
    r"(?P<primary>\s*\*primary)?\s*$"
)

# An availability phrase says WHEN a metric is present; a unit says what it is
# measured in. When only one annotation is given, these words identify it as
# an availability rather than a unit.
_AVAILABILITY_HINTS = ("always", "when ", "depends", "if ", "optional")


def _split_annotations(notes):
    """-> (unit, availability). Either may be empty."""
    parts = [p.strip() for p in notes.split(",") if p.strip()]
    if len(parts) >= 2:
        # Only treat the last part as availability if it actually looks like one.
        # Otherwise, the whole annotation is a unit (e.g., `log10(IC50, µM)`).
        last_part = parts[-1]
        if any(h in last_part.lower() for h in _AVAILABILITY_HINTS):
            return ", ".join(parts[:-1]), last_part
        return notes.strip(), ""
    if not parts:
        return "", ""
    only = parts[0]
    if any(h in only.lower() for h in _AVAILABILITY_HINTS):
        return "", only
    return only, ""


def _bound(text):
    """'inf'/'-inf' -> None, since JSON has no infinity literal."""
    text = text.strip()
    if text.lstrip("+-") == "inf":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_metrics_doc(text):
    """Extract the metric spec table from `proto-tools output <key>`.

    A tool with no Metrics block measures nothing -- that is a real answer
    (generators, retrievers and aligners produce no scores), not a parse
    failure, so `failures` stays empty for it. A row inside a block that
    does NOT parse is recorded, because a silently dropped metric is
    indistinguishable from a tool that never emitted it.
    """
    measures, failures, in_block = [], [], False

    for line in text.splitlines():
        if _METRICS_HEADER.match(line):
            in_block = True
            continue
        if not in_block:
            continue
        if not line.strip():
            in_block = False
            continue

        m = _METRIC_ROW.match(line)
        if m:
            unit, availability = _split_annotations(m.group("notes"))
            measures.append({
                "metric": m.group("name"),
                "type": m.group("type").strip(),
                "range": [_bound(m.group("lo")), _bound(m.group("hi"))],
                "unit": unit,
                "availability": availability,
                "better": m.group("better"),
                "primary": bool(m.group("primary")),
            })
        elif line.startswith("   "):
            # Indented more than the 2-space metric row: a continuation.
            continue
        else:
            failures.append(line.strip())

    return {"measures": measures, "failures": failures}
