"""proto-tools catalogue: sync and constraint parsing.

Constraints are parsed from the registry's own docs rather than hand-written,
so `proto-sync` can be re-run when the catalogue moves. Anything that cannot
be parsed stays None and is treated as UNKNOWN downstream -- never as
satisfied.
"""

import json
import re
import subprocess

from . import vocabulary

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


_CONSTRAINT_FIELDS = ("input_kind", "max_length")


def _alphabet_for(molecules):
    """Derive the legal-character alphabet from a resolved molecule list.

    Kept in one place and always computed from the FINAL merged `molecules`,
    never taken from whichever source happened to answer `alphabet` first --
    that would let `alphabet` disagree with the `molecules` list it is
    supposed to describe.
    """
    if molecules == ["protein"]:
        return PROTEIN_ALPHABET
    if molecules and set(molecules) <= {"dna", "rna"}:
        return NUCLEOTIDE_ALPHABET
    return None


def _merge_molecules(from_schema, from_doc, sources):
    """Intersect rather than let the schema win outright.

    The schema's `entity_type` description is a shared, generic definition
    reused by every tool that accepts a `Complex` -- it lists all four
    molecule kinds regardless of what a given tool actually supports, while
    the prose Note is tool-specific and narrower. Letting the schema win
    (the general `merge_constraints` rule) turned five protein-only/DNA-RNA
    tools into "accepts everything", which `check()` then treats as a molecule
    pass and an alphabet pass (protein letters are a superset of A/C/G/T) --
    a DNA artifact silently binds to a protein-only folder. That is exactly
    the fail-open behaviour this module exists to refuse.

    So: both present -> intersection; empty intersection (a real
    contradiction) -> the SHORTER list, never the union, because a narrower
    claim only produces a false rejection (visible in `rejected_by`) while a
    broader one produces a false acceptance (invisible). Unknown never
    counts as pass, so on disagreement the more restrictive claim wins.
    """
    schema_m, doc_m = from_schema.get("molecules"), from_doc.get("molecules")
    if schema_m is not None and doc_m is not None:
        if "schema" not in sources:
            sources.append("schema")
        if "docstring" not in sources:
            sources.append("docstring")
        intersection = sorted(set(schema_m) & set(doc_m))
        if intersection:
            return intersection
        return schema_m if len(schema_m) <= len(doc_m) else doc_m
    if schema_m is not None:
        if "schema" not in sources:
            sources.append("schema")
        return schema_m
    if doc_m is not None:
        if "docstring" not in sources:
            sources.append("docstring")
        return doc_m
    return None


def merge_constraints(from_schema, from_doc):
    """Schema first, prose only where the schema is silent -- except
    `molecules`, which the schema answers with a shared generic description
    rather than a tool-specific one, so it is intersected against the prose
    instead of simply preferred (see `_merge_molecules`). `alphabet` is then
    derived from that merged `molecules`, not taken independently from
    either source.

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

    merged["molecules"] = _merge_molecules(from_schema, from_doc, sources)
    merged["alphabet"] = _alphabet_for(merged["molecules"])
    merged["constraint_source"] = sources
    return merged


CATALOG_SCHEMA_VERSION = 3


def _fetch_or_default(fetcher, key, default):
    """A fetcher may raise (proto-sync's own prefetch already guards its
    subprocess calls this way, but nothing stops a caller from handing
    `build_catalog` a raw, unguarded fetcher). One tool's failure must
    degrade that tool to unknown -- an empty doc/schema, which every
    parser below already reads as "nothing learned" -- never abort the
    whole catalogue and never fall back to a stale or fabricated value.
    """
    try:
        return fetcher(key)
    except Exception:
        return default


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
            parse_input_schema(_fetch_or_default(schema_fetcher, key, {})),
            parse_input_doc(_fetch_or_default(doc_fetcher, key, "")),
        )
        parsed_metrics = parse_metrics_doc(_fetch_or_default(output_fetcher, key, ""))
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


CALIBRATION_SCHEMA_VERSION = 2
CALIBRATION_STATUSES = ("needs_calibration", "validated")
UNCALIBRATED = {"status": "needs_calibration"}


def _check_metric_record(tool_key, metric, rec):
    """A curated record must be complete before it can promote anything."""
    if not isinstance(rec, dict):
        raise ValueError(
            f"calibration: {tool_key}:{metric} record must be a JSON object, "
            f"got {rec!r}"
        )
    status = rec.get("status")
    if status not in CALIBRATION_STATUSES:
        raise ValueError(
            f"calibration: {tool_key}:{metric} has status {status!r}, expected "
            f"one of {CALIBRATION_STATUSES}"
        )
    if status != "validated":
        return
    if not rec.get("benchmark"):
        # Framework section 6 promotes on MEASURED reliability. A bare
        # flag with no number is the claim it exists to forbid.
        raise ValueError(
            f"calibration: {tool_key}:{metric} is validated without "
            f"benchmark; a promotion needs the measurement behind it"
        )
    # `measured_error` must be checked for SHAPE, not just presence: a
    # truthy-but-empty-of-substance record like {"kind": "mae"} used to pass
    # here and then raised a bare KeyError at validate.py's
    # `c["measured_error"]["value"]`. `isinstance(rec, dict)` is checked
    # before `.get` is called on it (the `not isinstance` short-circuits the
    # `or`), and `bool` is excluded explicitly because it is a subclass of
    # `int` in Python -- `isinstance(True, int)` is True.
    err = rec.get("measured_error")
    if (not isinstance(err, dict)
            or isinstance(err.get("value"), bool)
            or not isinstance(err.get("value"), (int, float))
            or err["value"] <= 0):
        raise ValueError(
            f"calibration: {tool_key}:{metric} has measured_error {err!r}; "
            f"needs a positive numeric `value`"
        )


def derive_status(measures):
    """Tool-level status, computed from its primary metrics.

    Validated iff the tool declares at least one `primary` metric and every
    one of them is validated. `primary` is the catalogue's own statement of
    what the tool is meant to be judged on, so a tool that declares none has
    nothing to validate and never rolls up -- true for 98 of 140 tools.

    Measured against the committed catalogue: all 42 tools declaring a primary
    declare exactly one, so in practice this reads "its primary metric is
    validated"; the `all` is for tools that later declare more.
    """
    primary = [m for m in measures if m.get("primary")]
    if not primary:
        return "needs_calibration"
    if all(m.get("calibration", UNCALIBRATED).get("status") == "validated"
           for m in primary):
        return "validated"
    return "needs_calibration"


def apply_calibration(catalog, curation):
    """Overlay hand-curated per-metric calibration onto a built catalogue.

    Returns `(catalog, orphans)`.

    Calibration keys on (tool, metric) because that is what has an error bar:
    one model emits several metrics and may be characterised for some and not
    others. `status` at tool level is derived from these (see `derive_status`),
    never curated.

    `build_catalog` never reads the file it replaces, so curation lives in its
    own file and is overlaid here. Orphans -- curated keys the catalogue no
    longer has -- are returned rather than dropped, reported as "tool" or
    "tool:metric".
    """
    version = curation.get("schema_version")
    if version != CALIBRATION_SCHEMA_VERSION:
        raise ValueError(
            f"calibration: schema_version {version!r}, expected "
            f"{CALIBRATION_SCHEMA_VERSION}. v1 keyed status on the tool, which "
            f"has no metric to attach to; re-key it under "
            f"tools.<key>.metrics.<metric>."
        )
    curated = curation.get("tools") or {}
    for tool_key, entry in sorted(curated.items()):
        for metric, rec in sorted(((entry or {}).get("metrics") or {}).items()):
            _check_metric_record(tool_key, metric, rec)

    present = {t["key"]: {m["metric"] for m in t.get("measures", [])}
               for t in catalog["tools"]}
    orphans = []
    for tool_key, entry in curated.items():
        if tool_key not in present:
            orphans.append(tool_key)
            continue
        for metric in ((entry or {}).get("metrics") or {}):
            if metric not in present[tool_key]:
                orphans.append(f"{tool_key}:{metric}")

    tools = []
    for t in catalog["tools"]:
        metrics = ((curated.get(t["key"]) or {}).get("metrics") or {})
        # `dict(...)` around the whole lookup, not just the UNCALIBRATED
        # fallback: writing the curated record object in by reference let a
        # later in-place mutation of the catalogue's `calibration` entry
        # edit the curation dict out from under it.
        measures = [
            {**m, "calibration": dict(metrics.get(m["metric"], UNCALIBRATED))}
            for m in t.get("measures", [])
        ]
        tools.append({**t, "measures": measures,
                      "status": derive_status(measures)})
    return {**catalog, "tools": tools}, sorted(orphans)


def load_catalog(path):
    """Read a registry, refusing anything but the current schema version.

    v1 -> v2 added derived `measures`. v2 -> v3 added per-metric
    `calibration` on each row. Coercing an older file would silently drop the
    calibration overlay and read every metric as having no opinion rather
    than as uncalibrated -- the fail-open behaviour `check()` refuses.
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


MIN_DESIGN_LENGTH = 20

# IUPAC codes that stand for "one of several residues" rather than naming one.
# U (selenocysteine) and O (pyrrolysine) are real residues and stay legal.
_AMBIGUITY_CODES = {
    "protein": frozenset("XBZ"),
    "dna": frozenset("N"),
    "rna": frozenset("N"),
}

# Statuses that reject an artifact on its own merits, before any tool is
# consulted. `cmd_bind` reports these by name rather than as a proto failure,
# because no proto constraint is involved.
ARTIFACT_QUALITY_STATUSES = ("unspecified_sequence", "below_min_length")


def _quality_gate(artifact):
    """Reject an artifact that is not a design candidate, whatever the tool.

    Both gates exist because a live run bound `VPGXG` -- the five-residue
    elastin-like-polypeptide repeat -- to esmfold-prediction with all four
    per-tool checks reading `pass`. Neither problem is expressible in
    `check()`, whose every verdict is relative to one tool's declared
    constraints: X really is a legal PROTEIN_ALPHABET character, and ESMFold
    really will accept a 5-mer. The artifact was still not a candidate.

    Ambiguity is reported ahead of length: a sequence carrying X is not fully
    specified, which is a more fundamental objection than being short.
    """
    ambiguous = sorted(
        set(artifact["value"].upper())
        & _AMBIGUITY_CODES.get(artifact["molecule"], frozenset())
    )
    if ambiguous:
        return ("unspecified_sequence",
                f"contains IUPAC ambiguity code(s) {ambiguous} -- those "
                f"positions are unresolved, so the sequence is not fully "
                f"specified")
    if artifact["length"] < MIN_DESIGN_LENGTH:
        return ("below_min_length",
                f"{artifact['length']} residues is below the "
                f"{MIN_DESIGN_LENGTH}-residue minimum for a design candidate "
                f"-- shorter matches are motifs or fragments")
    return None


def bind_artifact(artifact, catalog):
    """Bind one artifact to every tool that accepts it."""
    if artifact["kind"] not in _SEQUENCE_KINDS:
        return {"status": "unsupported_kind", "tools": [], "unverified": [],
                "rejected_by": [], "reason": f"no proto tool consumes a bare {artifact['kind']}"}

    gated = _quality_gate(artifact)
    if gated:
        status, reason = gated
        return {"status": status, "tools": [], "unverified": [],
                "rejected_by": [], "reason": reason}

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


UNASSESSED = "unassessed"


def resolve_properties(term_ids, catalog, vocab):
    """Map assigned vocabulary terms onto tools that measure them.

    Three-valued on purpose. The old version intersected free-text
    properties against an all-empty `measures` column and so returned
    `True` unconditionally -- an answer that happened to be right for the
    RF corpus and could not have been wrong for any corpus.

    Framework section 77: a class nothing can evaluate returns
    requires_new_evaluator, which is a legitimate output to hand back to
    the scientist rather than a discard.

    `tools` answers "what can MEASURE this"; `rankable_by` answers "what may
    RANK on it", which framework section 6 restricts to calibrated
    evaluators. They are separate fields because they are separate questions:
    folding them into one would have silently changed the meaning of every
    committed `requires_new_evaluator: false`.

    Known coarseness: when an item is labelled with several vocabulary terms,
    the metrics of ALL of them are unioned before matching, and a tool is
    marked rankable if ANY of its hits is validated -- so an item labelled
    `[fold_confidence, interface_energetics]` can list a tool validated only
    on `avg_plddt` as rankable for the whole multi-term claim, not just the
    term that tool actually covers.
    """
    if not term_ids:
        return {"tools": [], "rankable_by": [],
                "requires_new_evaluator": UNASSESSED}

    wanted = vocabulary.metrics_for(term_ids, vocab)
    tools, rankable = [], []
    for t in catalog["tools"]:
        hits = [m for m in t.get("measures", []) if m["metric"] in wanted]
        if not hits:
            continue
        tools.append(t["key"])
        if any(m.get("calibration", UNCALIBRATED).get("status") == "validated"
               for m in hits):
            rankable.append(t["key"])
    return {"tools": sorted(tools), "rankable_by": sorted(rankable),
            "requires_new_evaluator": not tools}


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
