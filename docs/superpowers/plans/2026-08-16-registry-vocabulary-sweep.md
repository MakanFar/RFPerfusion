# Evaluator Registry & Property Vocabulary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `requires_new_evaluator` a question that can actually return false, by deriving tool capabilities from proto-tools instead of hand-typed lists, and bridging free-text evidence properties to tool metrics through a closed vocabulary.

**Architecture:** `litkb proto-sync` becomes the single generator of truth, reading `proto-tools schema` (input constraints) and `proto-tools output` (metric specs) instead of regex-scraping prose. A versioned `registry/property_vocabulary.json` maps ~12 addressable property terms onto real metric names. `resolve_properties` matches in vocabulary space and returns three values. `formulation_agent007` stops hand-typing tool keys and metrics and loads a committed snapshot of the same registry.

**Tech Stack:** Python ≥3.10 (litkb) / ≥3.12 (007), `uv`, pytest. No new third-party dependencies. All tests offline; proto-tools and paperclip stay monkeypatched.

**Spec:** `docs/superpowers/specs/2026-08-16-registry-vocabulary-sweep-design.md`

## Global Constraints

- **Unknown never counts as pass.** `proto.check()`'s three-valued logic is unchanged and guarded by a regression test in Task 6.
- **Rejections ship.** Anything unparsed is recorded (`parse_failures`), never silently dropped.
- **`status: needs_calibration` stays on every tool.** This work adds capability facts, not accuracy claims. Do not add ranking based on metrics.
- **The committed RF run must not light up.** Most of its 45 evidence items should still report `requires_new_evaluator: true` after relabelling. A change that flips them to `false` en masse is a bug, not progress.
- **`registry/proto_catalog.json` carries `schema_version: 2`.** A reader seeing version 1 must raise, never coerce.
- **litkb tests run from `litterature_search_from_concept/`** — its `--registry` and `--project` defaults are relative (`../registry`, `../proto`).
- **Regenerating the registry needs the proto venv** (`uv run --project proto`). It is not offline. CI validates the committed file, never freshness.
- Existing runs under `outputs/` are historical records. Do not rewrite them.

---

## Phase 1 — Hygiene and CI

### Task 1: Remove tracked junk, fix the broken doc pointer, run all four suites in CI

**Files:**
- Delete: `_to_delete/git-index.lock`, `_to_delete/git-index.lock2`
- Modify: `litterature_search_from_concept/readme.txt:43`
- Modify: `.github/workflows/tests.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: a CI matrix that every later task's tests run under.

- [ ] **Step 1: Remove the tracked lock files**

```bash
git rm -r _to_delete/
```

- [ ] **Step 2: Fix the dangling design reference**

In `litterature_search_from_concept/readme.txt`, the line reads:

```
Design: docs/superpowers/specs/2026-08-15-litkb-proto-extraction-design.md
```

That file does not exist. Replace it with the real path:

```
Design: docs/superpowers/plans/2026-08-15-litkb-proto-extraction.md
```

- [ ] **Step 3: Verify the new path resolves**

Run: `test -f docs/superpowers/plans/2026-08-15-litkb-proto-extraction.md && echo OK`
Expected: `OK`

- [ ] **Step 4: Replace the CI workflow with a four-project matrix**

Write `.github/workflows/tests.yml`:

```yaml
name: tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  suites:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          # No credentials needed anywhere: every test is offline, with
          # paperclip and proto-tools calls monkeypatched.
          - name: litkb
            dir: litterature_search_from_concept
            args: ""
          - name: formulation_agent007
            dir: formulation_agent007
            args: ""
          - name: formulation_agent
            dir: formulation_agent
            # 4 tests hit the live Paperclip corpus and need an account.
            args: '-m "not live"'
          - name: biophys_triage
            dir: biophysical_triage_pipeline
            args: ""
    name: ${{ matrix.name }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Run the ${{ matrix.name }} suite
        working-directory: ${{ matrix.dir }}
        run: uv run --project . pytest -q ${{ matrix.args }}
```

- [ ] **Step 5: Verify each matrix leg locally**

Run each, from the repository root:

```bash
(cd litterature_search_from_concept && uv run --project . pytest -q)
(cd formulation_agent007        && uv run --project . pytest -q)
(cd formulation_agent           && uv run --project . pytest -q -m "not live")
(cd biophysical_triage_pipeline && uv run --project . pytest -q)
```

Expected: `119 passed`, `44 passed`, `24 passed, 4 deselected`, `16 passed`. Total 203.

- [ ] **Step 6: Commit**

```bash
git add -A .github/workflows/tests.yml litterature_search_from_concept/readme.txt
git commit -m "ci: run all four suites; drop tracked lock files; fix design pointer"
```

---

## Phase 2 — `proto-sync` derives the registry from proto-tools

### Task 2: Parse the metrics table from `proto-tools output`

**Files:**
- Modify: `litterature_search_from_concept/litkb/proto.py`
- Test: `litterature_search_from_concept/tests/test_metrics_parse.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `proto.parse_metrics_doc(text: str) -> dict` returning
  `{"measures": list[dict], "failures": list[str]}`. Each measure is
  `{"metric": str, "type": str, "range": [float|None, float|None],
  "unit": str, "availability": str,
  "better": "higher"|"lower"|"context-dependent", "primary": bool}`.

**Row formats observed live — all four must parse.** Verified against all 140
tools: with these handled, 311 rows across 48 tools parse and **zero** rows are
left over.

```
avg_plddt      float, range [0.0, 1.0], always, better=higher  *primary   # availability only
dG             float, range [-inf, inf], REU, better=lower                # unit only
helix_pct      float, range [0.0, 100.0], %, always, better=higher        # unit AND availability
dSASA          float, range [0.0, inf], Å^2, better=context-dependent     # non-ASCII unit
```

Three traps, each of which silently drops rows rather than failing:
`better=context-dependent` is the literal spelling (not `context`); metric names
contain uppercase (`dG`, `dG_per_dSASA`); and the header is sometimes the bare
`Metrics:` with no `(per X item)` suffix. A name pattern of `[a-z_][a-z0-9_]*`
plus a `context` alternative loses 100 of the 311 rows while looking like it
works.

- [ ] **Step 1: Write the failing tests**

Create `litterature_search_from_concept/tests/test_metrics_parse.py`. The three
doc bodies below are captured verbatim from real `proto-tools output` runs —
do not paraphrase them, they are the formats the parser must survive.

```python
from litkb import proto

ESMFOLD_OUT = """Output: ESMFoldOutput

  structures                list[Structure]                 (required)

Metrics (per structures item):
  avg_plddt                 float, range [0.0, 1.0], always, better=higher  *primary
  ptm                       float, range [0.0, 1.0], depends on model output, better=higher
  avg_pae                   float, range [0.0, inf], depends on model output, better=lower
  pae                       list[list[float]], range [0.0, inf], when include_pae_matrix=True, better=lower
"""

# Captured verbatim from `proto-tools output bindcraft-design`. Note the bare
# `Metrics:` header, the uppercase metric names, the non-ASCII unit, and
# `context-dependent` rather than `context`.
BINDCRAFT_OUT = """Output: BindCraftOutput

Metrics:
  dG                        float, range [-inf, inf], REU, better=lower
  dSASA                     float, range [0.0, inf], Å^2, better=context-dependent
  dG_per_dSASA              float, range [-inf, inf], REU/Å^2, better=lower
  interface_sasa_pct        float, range [0.0, 100.0], percent, better=context-dependent
"""

# From `proto-tools output dssp-secondary-structure`: a unit AND an
# availability between the range and better=.
DSSP_OUT = """Output: DSSPOutput

Metrics (per structures item):
  helix_pct                 float, range [0.0, 100.0], %, always, better=higher
"""

ABLANG_OUT = """Output: AbLangScoreOutput

Metrics (per sequences item):
  log_likelihood            float, range [-inf, 0.0], always, better=higher
      Sum over all positions. Grows with sequence length, so compare only at
      equal length.
  perplexity                float, range [1.0, inf], always, better=lower
"""

NO_METRICS_OUT = """Output: UniProtFetchOutput

  records                   list[Record]                    (required)
"""


def test_parses_primary_flag_and_bounded_range():
    m = proto.parse_metrics_doc(ESMFOLD_OUT)["measures"]
    first = m[0]
    assert first["metric"] == "avg_plddt"
    assert first["range"] == [0.0, 1.0]
    assert first["better"] == "higher"
    assert first["primary"] is True
    assert first["availability"] == "always"


def test_infinite_bound_becomes_null():
    m = {d["metric"]: d for d in proto.parse_metrics_doc(ESMFOLD_OUT)["measures"]}
    assert m["avg_pae"]["range"] == [0.0, None]
    assert m["pae"]["type"] == "list[list[float]]"


def test_only_one_metric_is_primary():
    m = proto.parse_metrics_doc(ESMFOLD_OUT)["measures"]
    assert [d["metric"] for d in m if d["primary"]] == ["avg_plddt"]


def test_bare_metrics_header_is_recognised():
    # bindcraft-design uses `Metrics:` with no `(per X item)` suffix.
    assert len(proto.parse_metrics_doc(BINDCRAFT_OUT)["measures"]) == 4


def test_uppercase_metric_names_are_parsed():
    # `dG` and `dG_per_dSASA` are real names; a lowercase-only pattern drops them.
    m = {d["metric"]: d for d in proto.parse_metrics_doc(BINDCRAFT_OUT)["measures"]}
    assert "dG" in m and "dG_per_dSASA" in m


def test_single_annotation_is_read_as_a_unit():
    m = {d["metric"]: d for d in proto.parse_metrics_doc(BINDCRAFT_OUT)["measures"]}
    assert m["dG"]["unit"] == "REU"
    assert m["dG"]["availability"] == ""
    assert m["dG"]["range"] == [None, None]


def test_unit_and_availability_together_are_split():
    m = {d["metric"]: d for d in proto.parse_metrics_doc(DSSP_OUT)["measures"]}
    assert m["helix_pct"]["unit"] == "%"
    assert m["helix_pct"]["availability"] == "always"


def test_availability_only_row_has_no_unit():
    m = {d["metric"]: d for d in proto.parse_metrics_doc(ESMFOLD_OUT)["measures"]}
    assert m["avg_plddt"]["availability"] == "always"
    assert m["avg_plddt"]["unit"] == ""


def test_better_context_dependent_is_the_literal_spelling():
    m = {d["metric"]: d for d in proto.parse_metrics_doc(BINDCRAFT_OUT)["measures"]}
    assert m["dSASA"]["better"] == "context-dependent"


def test_non_ascii_unit_survives():
    m = {d["metric"]: d for d in proto.parse_metrics_doc(BINDCRAFT_OUT)["measures"]}
    assert m["dSASA"]["unit"] == "Å^2"


def test_indented_continuation_lines_are_not_metrics():
    parsed = proto.parse_metrics_doc(ABLANG_OUT)
    assert [d["metric"] for d in parsed["measures"]] == ["log_likelihood", "perplexity"]
    assert parsed["failures"] == []


def test_tool_without_a_metrics_block_measures_nothing():
    parsed = proto.parse_metrics_doc(NO_METRICS_OUT)
    assert parsed["measures"] == []
    assert parsed["failures"] == []


def test_unparseable_row_is_recorded_not_dropped():
    doc = "Metrics (per structures item):\n  weird_metric  float, no range given\n"
    parsed = proto.parse_metrics_doc(doc)
    assert parsed["measures"] == []
    assert "weird_metric" in parsed["failures"][0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_metrics_parse.py -q`
Expected: FAIL — `AttributeError: module 'litkb.proto' has no attribute 'parse_metrics_doc'`

- [ ] **Step 3: Implement the parser**

Add to `litterature_search_from_concept/litkb/proto.py`:

```python
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
        return ", ".join(parts[:-1]), parts[-1]
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
        elif line.startswith("      "):
            # Deeper indent than a row: a continuation of the row above.
            continue
        else:
            failures.append(line.strip())

    return {"measures": measures, "failures": failures}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_metrics_parse.py -q`
Expected: `11 passed`

- [ ] **Step 5: Commit**

```bash
git add litterature_search_from_concept/litkb/proto.py litterature_search_from_concept/tests/test_metrics_parse.py
git commit -m "feat(litkb): parse the metric_spec table from proto-tools output"
```

### Task 3: Read input constraints from the JSON Schema, falling back to prose

**Files:**
- Modify: `litterature_search_from_concept/litkb/proto.py`
- Test: `litterature_search_from_concept/tests/test_schema_parse.py` (create)

**Interfaces:**
- Consumes: nothing from Task 2.
- Produces: `proto.parse_input_schema(schema: dict) -> dict` returning
  `{"input_kind": str|None, "molecules": list[str]|None, "alphabet": str|None,
  "max_length": int|None}`, and `proto.merge_constraints(schema_parsed, doc_parsed) -> dict`
  which adds `constraint_source: list[str]`.

- [ ] **Step 1: Write the failing tests**

Create `litterature_search_from_concept/tests/test_schema_parse.py`:

```python
from litkb import proto

# Shape captured from `proto-tools schema esmfold-prediction`.
ESMFOLD_SCHEMA = {
    "inputs": {
        "$defs": {
            "Chain": {
                "properties": {
                    "sequence": {"type": "string",
                                 "description": "Sequence of the chain"},
                    "entity_type": {
                        "description": "Entity type: 'protein', 'dna', 'rna', "
                                       "or 'ligand'. Auto-inferred if None.",
                    },
                }
            }
        },
        "properties": {"complexes": {"type": "array"}},
    }
}

SEQ_ONLY_SCHEMA = {
    "inputs": {
        "$defs": {},
        "properties": {
            "sequences": {"type": "array", "items": {"type": "string",
                                                     "maxLength": 1022}}
        },
    }
}

OPAQUE_SCHEMA = {"inputs": {"$defs": {}, "properties": {}}}


def test_entity_type_description_yields_molecules():
    got = proto.parse_input_schema(ESMFOLD_SCHEMA)
    assert got["molecules"] == ["dna", "ligand", "protein", "rna"]


def test_complexes_field_is_a_complex_input():
    assert proto.parse_input_schema(ESMFOLD_SCHEMA)["input_kind"] == "complex"


def test_sequences_field_is_a_sequence_input():
    assert proto.parse_input_schema(SEQ_ONLY_SCHEMA)["input_kind"] == "sequence"


def test_declared_maxlength_is_used():
    assert proto.parse_input_schema(SEQ_ONLY_SCHEMA)["max_length"] == 1022


def test_opaque_schema_yields_all_unknown():
    got = proto.parse_input_schema(OPAQUE_SCHEMA)
    assert got == {"input_kind": None, "molecules": None,
                   "alphabet": None, "max_length": None}


def test_prose_supplies_a_cap_the_schema_never_declares():
    # ESMFold's 2,400 cap lives only in the docstring Note, never in the schema.
    doc = proto.parse_input_doc(
        "Attributes:\n    complexes: must not exceed 2,400.\n"
    )
    merged = proto.merge_constraints(proto.parse_input_schema(ESMFOLD_SCHEMA), doc)
    assert merged["max_length"] == 2400
    assert merged["constraint_source"] == ["schema", "docstring"]


def test_schema_wins_over_prose_when_both_supply_a_field():
    doc = proto.parse_input_doc("Note:\n    only supports protein sequences\n")
    merged = proto.merge_constraints(proto.parse_input_schema(SEQ_ONLY_SCHEMA), doc)
    assert merged["max_length"] == 1022


def test_source_records_docstring_only_when_prose_contributed():
    merged = proto.merge_constraints(
        proto.parse_input_schema(SEQ_ONLY_SCHEMA),
        {"input_kind": None, "molecules": None, "alphabet": None,
         "max_length": None, "constraint_source": "docstring"},
    )
    assert merged["constraint_source"] == ["schema"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_schema_parse.py -q`
Expected: FAIL — `AttributeError: module 'litkb.proto' has no attribute 'parse_input_schema'`

- [ ] **Step 3: Implement schema parsing and the merge**

Add to `litterature_search_from_concept/litkb/proto.py`:

```python
_ENTITY_IN_DESC = re.compile(r"protein|dna|rna|ligand")


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
    for _, sub in fields:
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_schema_parse.py -q`
Expected: `11 passed`

- [ ] **Step 5: Confirm the existing prose parser still passes**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_proto.py -q`
Expected: all pass — `parse_input_doc` is untouched and stays the fallback.

- [ ] **Step 6: Commit**

```bash
git add litterature_search_from_concept/litkb/proto.py litterature_search_from_concept/tests/test_schema_parse.py
git commit -m "feat(litkb): read input constraints from proto-tools JSON Schema, prose as fallback"
```

### Task 4: Assemble the v2 registry and regenerate it

**Files:**
- Modify: `litterature_search_from_concept/litkb/proto.py` (`build_catalog`, fetchers)
- Modify: `litterature_search_from_concept/litkb/cli.py:492-498` (`cmd_proto_sync`)
- Modify: `registry/proto_catalog.json` (regenerated)
- Test: `litterature_search_from_concept/tests/test_catalog_build.py` (create)

**Interfaces:**
- Consumes: `parse_metrics_doc`, `parse_input_schema`, `merge_constraints` from Tasks 2–3.
- Produces: registry v2 on disk with top-level keys `schema_version` (int, `2`),
  `tools` (list), `n_tools` (int), `parse_failures` (list of `{key, line}`).
  Each tool gains `measures` (list) and `constraint_source` (list).
  Also `proto.load_catalog(path) -> dict`, which raises `ValueError` on
  `schema_version != 2`.

- [ ] **Step 1: Write the failing tests**

Create `litterature_search_from_concept/tests/test_catalog_build.py`:

```python
import pytest

from litkb import proto

TOOLS = [
    {"key": "esmfold-prediction", "category": "structure_prediction", "uses_gpu": True},
    {"key": "uniprot-fetch", "category": "database_retrieval", "uses_gpu": False},
]

SCHEMAS = {
    "esmfold-prediction": {
        "inputs": {
            "$defs": {"Chain": {"properties": {
                "entity_type": {"description": "'protein', 'dna', 'rna', or 'ligand'"}}}},
            "properties": {"complexes": {"type": "array"}},
        }
    },
    "uniprot-fetch": {"inputs": {"$defs": {}, "properties": {}}},
}

OUTPUTS = {
    "esmfold-prediction": (
        "Metrics (per structures item):\n"
        "  avg_plddt                 float, range [0.0, 1.0], always, better=higher  *primary\n"
        "  bogus row with no range\n"
    ),
    "uniprot-fetch": "Output: UniProtFetchOutput\n",
}

DOCS = {"esmfold-prediction": "must not exceed 2,400", "uniprot-fetch": ""}


def _build():
    return proto.build_catalog(
        TOOLS,
        doc_fetcher=lambda k: DOCS[k],
        schema_fetcher=lambda k: SCHEMAS[k],
        output_fetcher=lambda k: OUTPUTS[k],
    )


def test_registry_declares_schema_version_2():
    assert _build()["schema_version"] == 2


def test_measures_are_attached_per_tool():
    tools = {t["key"]: t for t in _build()["tools"]}
    assert tools["esmfold-prediction"]["measures"][0]["metric"] == "avg_plddt"


def test_tool_measuring_nothing_gets_an_empty_list():
    tools = {t["key"]: t for t in _build()["tools"]}
    assert tools["uniprot-fetch"]["measures"] == []


def test_unparsed_rows_are_surfaced_with_their_tool():
    failures = _build()["parse_failures"]
    assert failures == [{"key": "esmfold-prediction", "line": "bogus row with no range"}]


def test_status_stays_needs_calibration():
    # Capability is not accuracy. Framework section 6 is unaffected by this work.
    assert all(t["status"] == "needs_calibration" for t in _build()["tools"])


def test_constraint_source_is_a_list():
    tools = {t["key"]: t for t in _build()["tools"]}
    assert tools["esmfold-prediction"]["constraint_source"] == ["schema", "docstring"]


def test_load_catalog_rejects_a_version_1_registry(tmp_path):
    import json
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"tools": [], "n_tools": 0}))
    with pytest.raises(ValueError, match="schema_version"):
        proto.load_catalog(old)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_catalog_build.py -q`
Expected: FAIL — `build_catalog() got an unexpected keyword argument 'schema_fetcher'`

- [ ] **Step 3: Rewrite `build_catalog` and add the fetchers and loader**

Replace `build_catalog` in `litterature_search_from_concept/litkb/proto.py` and
add the fetchers beside the existing ones:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_catalog_build.py -q`
Expected: `7 passed`

- [ ] **Step 5: Update `cmd_proto_sync` to pass the new fetchers**

Replace `cmd_proto_sync` in `litterature_search_from_concept/litkb/cli.py`:

```python
def cmd_proto_sync(args):
    tools = proto.fetch_tools(args.project)
    print(f"  {len(tools)} tools from proto-tools", file=sys.stderr)
    catalog = proto.build_catalog(
        tools,
        doc_fetcher=lambda k: proto.fetch_input_doc(k, args.project),
        schema_fetcher=lambda k: proto.fetch_schema(k, args.project),
        output_fetcher=lambda k: proto.fetch_output_doc(k, args.project),
    )
    capped = sum(1 for t in catalog["tools"] if t["max_length"] is not None)
    scoring = sum(1 for t in catalog["tools"] if t["measures"])
    print(f"  {capped}/{len(tools)} have a parseable length cap", file=sys.stderr)
    print(f"  {scoring}/{len(tools)} publish metrics", file=sys.stderr)
    if catalog["parse_failures"]:
        print(f"  {len(catalog['parse_failures'])} metric rows did not parse "
              f"(recorded in parse_failures)", file=sys.stderr)
    _emit(catalog, args.out)
```

- [ ] **Step 6: Regenerate the registry**

Requires the proto venv; this step is not offline.

```bash
cd litterature_search_from_concept
uv run --project . python -m litkb proto-sync -o ../registry/proto_catalog.json
```

Expected on stderr: `140 tools from proto-tools`, and `48/140 publish metrics`.
If the metric count is far below 48, the parser regressed — do not commit.

- [ ] **Step 7: Sanity-check the regenerated registry**

```bash
python3 -c "
import json; c=json.load(open('registry/proto_catalog.json'))
print('version', c['schema_version'], '| tools', c['n_tools'])
print('with measures', sum(1 for t in c['tools'] if t['measures']))
print('parse_failures', len(c['parse_failures']))
m={x['metric'] for t in c['tools'] for x in t['measures']}
print('distinct metrics', len(m)); assert 'avg_plddt' in m
"
```

Expected: `version 2 | tools 140`, `with measures 48`, `distinct metrics 170`,
`parse_failures 0`.

- [ ] **Step 8: Commit**

```bash
git add litterature_search_from_concept/litkb/proto.py litterature_search_from_concept/litkb/cli.py \
        litterature_search_from_concept/tests/test_catalog_build.py registry/proto_catalog.json
git commit -m "feat(litkb): derive measures and constraints from proto-tools; registry schema_version 2"
```

---

## Phase 3 — The property vocabulary

### Task 5: Add the vocabulary and the invariant that keeps it honest

**Files:**
- Create: `registry/property_vocabulary.json`
- Create: `litterature_search_from_concept/litkb/vocabulary.py`
- Test: `litterature_search_from_concept/tests/test_vocabulary.py` (create)

**Interfaces:**
- Consumes: registry v2 from Task 4.
- Produces: `vocabulary.load(path) -> dict`;
  `vocabulary.metrics_for(term_ids: list[str], vocab: dict) -> set[str]`;
  `vocabulary.validate(vocab, catalog) -> list[str]` (errors, empty when valid);
  `vocabulary.UnknownTerm` (raised by `metrics_for` on an unrecognised id).

- [ ] **Step 1: Write the vocabulary file**

Create `registry/property_vocabulary.json`. Every `metrics` entry below is a
real metric name present in the regenerated registry — that is enforced by the
test in Step 3, so do not add a term speculatively.

```json
{
  "version": 1,
  "note": "Closed set of properties the proto-tools catalogue can actually address. A property with no evaluator is expressed by assigning NO term, never by adding an unbacked one. Every term must resolve to at least one metric in registry/proto_catalog.json; tests/test_vocabulary.py enforces it.",
  "terms": [
    {"id": "fold_confidence",
     "definition": "Model confidence that a predicted monomer fold is correct.",
     "metrics": ["avg_plddt", "plddt", "complex_plddt", "avg_ss_plddt", "chain_plddt", "ptm"]},
    {"id": "interface_confidence",
     "definition": "Model confidence in a predicted inter-chain interface.",
     "metrics": ["iptm", "chain_pair_iptm", "pdockq2", "avg_iplddt", "complex_iplddt", "avg_interface_plddt"]},
    {"id": "predicted_error",
     "definition": "Predicted positional error in a structure prediction.",
     "metrics": ["avg_pae", "pae"]},
    {"id": "sequence_likelihood",
     "definition": "How probable a sequence is under a protein or nucleotide language model.",
     "metrics": ["perplexity", "log_likelihood", "avg_log_likelihood"]},
    {"id": "structural_validity",
     "definition": "Whether a predicted structure is physically self-consistent.",
     "metrics": ["has_clash"]},
    {"id": "interface_energetics",
     "definition": "Estimated energetic favourability of a designed interface.",
     "metrics": ["dG", "dG_per_dSASA"]},
    {"id": "interface_geometry",
     "definition": "Size and shape of a designed interface.",
     "metrics": ["dSASA", "interface_sasa_pct"]},
    {"id": "surface_character",
     "definition": "Hydrophobic character of a surface or interface.",
     "metrics": ["surface_hydrophobicity", "interface_hydrophobicity"]},
    {"id": "design_ranking",
     "definition": "A tool's own aggregate ranking of the designs it produced.",
     "metrics": ["ranking_score", "confidence_score"]}
  ]
}
```

- [ ] **Step 2: Write the failing tests**

Create `litterature_search_from_concept/tests/test_vocabulary.py`:

```python
import json
from pathlib import Path

import pytest

from litkb import proto, vocabulary

REGISTRY = Path(__file__).resolve().parents[2] / "registry" / "proto_catalog.json"
VOCAB = Path(__file__).resolve().parents[2] / "registry" / "property_vocabulary.json"


def test_every_term_resolves_to_a_real_metric():
    """The invariant that stops the vocabulary rotting as the catalogue moves.

    A term resolving to nothing would silently make an assessable property
    unassessable, which is the failure this whole design removes.
    """
    catalog = proto.load_catalog(REGISTRY)
    assert vocabulary.validate(vocabulary.load(VOCAB), catalog) == []


def test_term_ids_are_unique():
    vocab = vocabulary.load(VOCAB)
    ids = [t["id"] for t in vocab["terms"]]
    assert len(ids) == len(set(ids))


def test_metrics_for_unions_across_terms():
    vocab = {"version": 1, "terms": [
        {"id": "a", "definition": "x", "metrics": ["m1", "m2"]},
        {"id": "b", "definition": "y", "metrics": ["m2", "m3"]},
    ]}
    assert vocabulary.metrics_for(["a", "b"], vocab) == {"m1", "m2", "m3"}


def test_metrics_for_ignores_no_terms():
    vocab = vocabulary.load(VOCAB)
    assert vocabulary.metrics_for([], vocab) == set()


def test_validate_reports_a_term_backed_by_no_metric():
    vocab = {"version": 1, "terms": [
        {"id": "phlogiston", "definition": "not a thing", "metrics": ["nope"]},
    ]}
    catalog = {"schema_version": 2, "tools": [
        {"key": "t", "measures": [{"metric": "avg_plddt"}]}]}
    errors = vocabulary.validate(vocab, catalog)
    assert len(errors) == 1 and "phlogiston" in errors[0]


def test_unknown_term_id_is_rejected():
    vocab = vocabulary.load(VOCAB)
    with pytest.raises(vocabulary.UnknownTerm):
        vocabulary.metrics_for(["not_a_term"], vocab)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_vocabulary.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'litkb.vocabulary'`

- [ ] **Step 4: Implement the vocabulary module**

Create `litterature_search_from_concept/litkb/vocabulary.py`:

```python
"""The bridge between what a paper measured and what a tool can measure.

Evidence properties arrive as free text in the language of the experiment
("time-resolved EPR", "reorganization energy"); tools emit metric names
("avg_plddt", "iptm"). The two share no namespace, so intersecting them
directly can never match -- which is why `resolve_properties` returned
`requires_new_evaluator: true` for 45/45 items in the committed RF run
regardless of input.

This module holds the closed set of properties the catalogue can actually
address. Assigning NO term is the correct way to say "nothing measures
this"; inventing a term with no backing metric is not.
"""

import json


class UnknownTerm(ValueError):
    pass


def load(path):
    with open(path) as fh:
        return json.load(fh)


def metrics_for(ids, vocab):
    by_id = {t["id"]: t for t in vocab["terms"]}
    unknown = sorted(set(ids) - by_id.keys())
    if unknown:
        raise UnknownTerm(f"unknown vocabulary term(s): {', '.join(unknown)}")
    return {m for i in ids for m in by_id[i]["metrics"]}


def validate(vocab, catalog):
    """Every term must resolve to at least one metric the catalogue emits."""
    known = {m["metric"] for t in catalog["tools"] for m in t.get("measures", [])}
    errors = []
    for term in vocab["terms"]:
        if not set(term["metrics"]) & known:
            errors.append(
                f"vocabulary term '{term['id']}' resolves to no metric in the "
                f"registry; its metrics {term['metrics']} are all absent"
            )
    return errors
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_vocabulary.py -q`
Expected: `6 passed`

If `test_every_term_resolves_to_a_real_metric` fails, a term names a metric the
catalogue does not emit. Fix the **vocabulary**, not the test — drop the missing
metric from that term, and drop the term entirely if nothing backs it.

- [ ] **Step 6: Commit**

```bash
git add registry/property_vocabulary.json litterature_search_from_concept/litkb/vocabulary.py \
        litterature_search_from_concept/tests/test_vocabulary.py
git commit -m "feat(litkb): add the closed property vocabulary and its resolves-to-a-metric invariant"
```

### Task 6: Make `requires_new_evaluator` three-valued

**Files:**
- Modify: `litterature_search_from_concept/litkb/proto.py` (`resolve_properties`)
- Modify: `litterature_search_from_concept/litkb/contracts.py:230-264` (`item_from_mechanism`)
- Modify: `litterature_search_from_concept/litkb/cli.py:406-436` (`cmd_evidence`)
- Test: `litterature_search_from_concept/tests/test_resolve_properties.py` (create)

**Interfaces:**
- Consumes: `vocabulary.metrics_for` from Task 5.
- Produces: `proto.UNASSESSED = "unassessed"`;
  `proto.resolve_properties(term_ids: list[str]|None, catalog: dict, vocab: dict) -> dict`
  returning `{"tools": list[str], "requires_new_evaluator": bool | "unassessed"}`.
  Evidence items gain `testable_by.vocabulary: list[str]`, and evidence files gain
  `schema_version: 2`.

- [ ] **Step 1: Write the failing tests**

Create `litterature_search_from_concept/tests/test_resolve_properties.py`:

```python
from litkb import contracts, proto

VOCAB = {"version": 1, "terms": [
    {"id": "fold_confidence", "definition": "x", "metrics": ["avg_plddt"]},
    {"id": "interface_confidence", "definition": "y", "metrics": ["iptm"]},
    {"id": "orphan", "definition": "z", "metrics": ["nothing_emits_this"]},
]}

CATALOG = {"schema_version": 2, "tools": [
    {"key": "esmfold-prediction", "measures": [{"metric": "avg_plddt"}]},
    {"key": "boltz2-prediction", "measures": [{"metric": "iptm"}]},
    {"key": "uniprot-fetch", "measures": []},
]}


def test_no_terms_assigned_is_unassessed_not_true():
    """An unmade assessment must not read as a completed one.

    This is the same rule as check()'s `unknown`, which never counts as pass.
    """
    got = proto.resolve_properties(None, CATALOG, VOCAB)
    assert got["requires_new_evaluator"] == proto.UNASSESSED
    assert got["tools"] == []


def test_empty_list_is_also_unassessed():
    got = proto.resolve_properties([], CATALOG, VOCAB)
    assert got["requires_new_evaluator"] == proto.UNASSESSED


def test_mapped_term_with_a_tool_returns_false():
    got = proto.resolve_properties(["fold_confidence"], CATALOG, VOCAB)
    assert got["requires_new_evaluator"] is False
    assert got["tools"] == ["esmfold-prediction"]


def test_mapped_term_with_no_tool_returns_true():
    got = proto.resolve_properties(["orphan"], CATALOG, VOCAB)
    assert got["requires_new_evaluator"] is True
    assert got["tools"] == []


def test_multiple_terms_union_their_tools():
    got = proto.resolve_properties(
        ["fold_confidence", "interface_confidence"], CATALOG, VOCAB)
    assert got["tools"] == ["boltz2-prediction", "esmfold-prediction"]


def test_drafted_item_starts_unassessed_with_free_text_kept():
    mech = {"claim": "TlpA melts near 44 C", "chain": "abc",
            "measurable_properties": ["melting temperature"]}
    item = contracts.item_from_mechanism(1, "c1", mech, "doc1", {"title": "t"})
    assert item["testable_by"]["requires_new_evaluator"] == proto.UNASSESSED
    assert item["testable_by"]["vocabulary"] == []
    assert item["testable_by"]["properties"] == ["melting temperature"]


def test_unknown_never_counts_as_pass_regression():
    """Guard on the rule this work must not weaken."""
    artifact = {"kind": "sequence", "molecule": "protein", "value": "MKV", "length": 3}
    tool = {"key": "t", "input_kind": None, "molecules": None,
            "alphabet": None, "max_length": None}
    checks = proto.check(artifact, tool)
    assert set(checks.values()) == {"unknown"}
    assert proto.bind_artifact(artifact, {"tools": [tool]})["status"] == "unverified"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_resolve_properties.py -q`
Expected: FAIL — `resolve_properties() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: Rewrite `resolve_properties`**

Replace it in `litterature_search_from_concept/litkb/proto.py`:

```python
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
    """
    if not term_ids:
        return {"tools": [], "requires_new_evaluator": UNASSESSED}

    wanted = vocabulary.metrics_for(term_ids, vocab)
    tools = sorted(
        t["key"] for t in catalog["tools"]
        if wanted & {m["metric"] for m in t.get("measures", [])}
    )
    return {"tools": tools, "requires_new_evaluator": not tools}
```

Add `from . import vocabulary` to the imports at the top of `proto.py`.

- [ ] **Step 4: Update the draft builder**

In `litterature_search_from_concept/litkb/contracts.py`, change the
`testable_by` block of `item_from_mechanism` to:

```python
        # `vocabulary` is filled by `litkb label`, like every other
        # judgement field -- the tool drafts, the agent judges. Until then
        # the assessment is unmade, and says so.
        "testable_by": {"properties": mech.get("measurable_properties", []),
                        "vocabulary": [], "tools": [],
                        "requires_new_evaluator": "unassessed"},
```

- [ ] **Step 5: Update `cmd_evidence` to stop calling the resolver at draft time**

In `litterature_search_from_concept/litkb/cli.py`, replace the `item["testable_by"] = {...}`
assignment inside `cmd_evidence` — drafting no longer resolves anything, because
no terms are assigned yet:

```python
            item = contracts.item_from_mechanism(n, rec["class_id"], mech, doc, cache[doc],
                                                 extracted_by=extracted_by)
            items.append(item)
```

Then replace the summary line and the emitted payload:

```python
    print(f"  {len(items)} items drafted, all testable_by unassessed until "
          f"`litkb label` runs", file=sys.stderr)
    _emit({"schema_version": 2, "slug": screened["slug"], "items": items,
           "unlabelled": len(contracts.validate_items(items))},
          _resolve_out(args, f"evidence_{screened['slug']}.json"))
```

The `catalog = _load(args.registry) ...` line at the top of `cmd_evidence` is now
unused — delete it, and delete the `--registry` argument from the `evidence`
subparser at `cli.py:656`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_resolve_properties.py -q`
Expected: `7 passed`

- [ ] **Step 7: Run the whole litkb suite and repair fallout**

Run: `cd litterature_search_from_concept && uv run --project . pytest -q`
Expected: all pass. `tests/test_evidence_from_screen.py` asserts on the old
`testable_by` shape and will need updating to expect `"unassessed"` and the new
`vocabulary` key. Update the assertions; do not weaken them.

- [ ] **Step 8: Commit**

```bash
git add litterature_search_from_concept/litkb litterature_search_from_concept/tests
git commit -m "feat(litkb): three-valued requires_new_evaluator; drafts start unassessed"
```

### Task 7: Let `litkb label` assign vocabulary terms

**Files:**
- Modify: `litterature_search_from_concept/litkb/contracts.py:284-315` (`apply_labels`)
- Modify: `litterature_search_from_concept/litkb/cli.py:438-449` (`cmd_label`)
- Test: `litterature_search_from_concept/tests/test_label_vocabulary.py` (create)

**Interfaces:**
- Consumes: `vocabulary`, `proto.resolve_properties` from Tasks 5–6.
- Produces: `contracts.apply_labels(items, labels, catalog=None, vocab=None)`.
  When both are supplied, a label carrying `vocabulary` re-resolves that item's
  `testable_by.tools` and `requires_new_evaluator`.

- [ ] **Step 1: Write the failing tests**

Create `litterature_search_from_concept/tests/test_label_vocabulary.py`:

```python
from litkb import contracts, proto

VOCAB = {"version": 1, "terms": [
    {"id": "fold_confidence", "definition": "x", "metrics": ["avg_plddt"]},
]}
CATALOG = {"schema_version": 2, "tools": [
    {"key": "esmfold-prediction", "measures": [{"metric": "avg_plddt"}]},
]}


def _item():
    return {"id": "ev_001", "testable_by": {
        "properties": ["fold stability"], "vocabulary": [], "tools": [],
        "requires_new_evaluator": "unassessed"}}


def test_assigning_a_term_resolves_tools_and_flips_the_flag():
    items = [_item()]
    applied, errors = contracts.apply_labels(
        items, [{"id": "ev_001", "vocabulary": ["fold_confidence"]}],
        catalog=CATALOG, vocab=VOCAB)
    assert (applied, errors) == (1, [])
    tb = items[0]["testable_by"]
    assert tb["vocabulary"] == ["fold_confidence"]
    assert tb["tools"] == ["esmfold-prediction"]
    assert tb["requires_new_evaluator"] is False


def test_assigning_an_empty_list_is_a_real_assessment_not_unassessed():
    """'I looked, and nothing in the catalogue measures this' is a finding."""
    items = [_item()]
    contracts.apply_labels(items, [{"id": "ev_001", "vocabulary": []}],
                           catalog=CATALOG, vocab=VOCAB)
    assert items[0]["testable_by"]["requires_new_evaluator"] is True
    assert items[0]["testable_by"]["tools"] == []


def test_unknown_term_is_rejected_and_item_untouched():
    items = [_item()]
    applied, errors = contracts.apply_labels(
        items, [{"id": "ev_001", "vocabulary": ["phlogiston"]}],
        catalog=CATALOG, vocab=VOCAB)
    assert applied == 0
    assert "phlogiston" in errors[0]
    assert items[0]["testable_by"]["requires_new_evaluator"] == "unassessed"


def test_free_text_properties_survive_labelling():
    items = [_item()]
    contracts.apply_labels(items, [{"id": "ev_001", "vocabulary": ["fold_confidence"]}],
                           catalog=CATALOG, vocab=VOCAB)
    assert items[0]["testable_by"]["properties"] == ["fold stability"]


def test_testable_by_cannot_be_overwritten_wholesale():
    items = [_item()]
    applied, errors = contracts.apply_labels(
        items, [{"id": "ev_001", "testable_by": {"tools": ["made-up"]}}],
        catalog=CATALOG, vocab=VOCAB)
    assert applied == 0
    assert "testable_by" in errors[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_label_vocabulary.py -q`
Expected: FAIL — `apply_labels() got an unexpected keyword argument 'catalog'`

- [ ] **Step 3: Extend `apply_labels`**

In `litterature_search_from_concept/litkb/contracts.py`, change the signature and
add two branches inside the per-field loop. The full replacement:

```python
def apply_labels(items, labels, catalog=None, vocab=None):
    """Merge agent-supplied judgements into draft items, by id.

    `vocabulary` is the one label that has a computed consequence: assigning
    terms re-resolves `testable_by`. Assigning an EMPTY list is meaningful
    and different from never labelling -- it records that the agent looked
    and found nothing in the catalogue, which is a finding worth shipping.
    """
    from . import proto  # local import: proto imports contracts-free helpers

    by_id = {it["id"]: it for it in items}
    errors, applied = [], 0

    for lab in labels:
        iid = lab.get("id")
        if iid not in by_id:
            errors.append(f"unknown evidence id '{iid}'")
            continue
        item = by_id[iid]

        if "vocabulary" in lab:
            terms = lab["vocabulary"]
            if not isinstance(terms, list):
                errors.append(f"{iid}: vocabulary must be a list of term ids")
                continue
            if vocab is None or catalog is None:
                errors.append(f"{iid}: cannot apply vocabulary without a "
                              f"registry and a vocabulary file")
                continue
            try:
                resolved = proto.resolve_properties(terms, catalog, vocab) if terms \
                    else {"tools": [], "requires_new_evaluator": True}
            except vocabulary_error() as exc:
                errors.append(f"{iid}: {exc}")
                continue
            item["testable_by"]["vocabulary"] = list(terms)
            item["testable_by"]["tools"] = resolved["tools"]
            item["testable_by"]["requires_new_evaluator"] = \
                resolved["requires_new_evaluator"]

        bad_field = False
        for field, value in lab.items():
            if field in ("id", "vocabulary"):
                continue
            if field == "support" and value not in SUPPORT_LEVELS:
                errors.append(f"{iid}: support must be one of {SUPPORT_LEVELS}, got '{value}'")
                bad_field = True
                continue
            if field == "claim_type" and value not in CLAIM_TYPES:
                errors.append(f"{iid}: claim_type must be one of {CLAIM_TYPES}, got '{value}'")
                bad_field = True
                continue
            if field == "evidence_kind" and value not in EVIDENCE_KINDS:
                errors.append(f"{iid}: evidence_kind must be one of {EVIDENCE_KINDS}, got '{value}'")
                bad_field = True
                continue
            if field == "confidence" and not (isinstance(value, (int, float)) and 0 <= value <= 1):
                errors.append(f"{iid}: confidence must be a number in [0, 1], got '{value}'")
                bad_field = True
                continue
            if field == "provenance":
                errors.append(f"{iid}: provenance is tool-owned and cannot be relabelled")
                bad_field = True
                continue
            if field == "testable_by":
                errors.append(f"{iid}: testable_by is resolved from `vocabulary`, "
                              f"not set directly")
                bad_field = True
                continue
            item[field] = value
        if not bad_field:
            applied += 1
    return applied, errors


def vocabulary_error():
    from .vocabulary import UnknownTerm
    return UnknownTerm
```

Note the behaviour change: `applied` no longer counts a label whose fields were
all rejected. `tests/test_artifacts.py` may assert the old count — update it if so.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_label_vocabulary.py -q`
Expected: `5 passed`

- [ ] **Step 5: Wire the registry and vocabulary into `cmd_label`**

Replace `cmd_label` in `litterature_search_from_concept/litkb/cli.py`:

```python
def cmd_label(args):
    ev = _load(args.evidence)
    labels = _load(args.labels)
    if isinstance(labels, dict):
        labels = labels.get("labels", [])
    catalog = proto.load_catalog(args.registry) if Path(args.registry).exists() else None
    vocab = vocabulary.load(args.vocabulary) if Path(args.vocabulary).exists() else None
    applied, errors = contracts.apply_labels(ev["items"], labels,
                                             catalog=catalog, vocab=vocab)
    if errors:
        print(f"applied {applied} labels, {len(errors)} rejected:", file=sys.stderr)
        _fail(errors)
    ev["unlabelled"] = len(contracts.validate_items(ev["items"]))
    _emit(ev, args.out or args.evidence)
```

Add `from litkb import vocabulary` to the imports at the top of `cli.py`, and add
two arguments to the `label` subparser (around `cli.py:661`):

```python
    p.add_argument("--registry", default="../registry/proto_catalog.json")
    p.add_argument("--vocabulary", default="../registry/property_vocabulary.json")
```

- [ ] **Step 6: Run the whole litkb suite**

Run: `cd litterature_search_from_concept && uv run --project . pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add litterature_search_from_concept/litkb litterature_search_from_concept/tests
git commit -m "feat(litkb): label assigns vocabulary terms and re-resolves testable_by"
```

---

## Phase 4 — `formulation_agent007` reads generated data

### Task 8: Replace the hand-typed tool keys and metrics with a generated snapshot

**Files:**
- Modify: `litterature_search_from_concept/litkb/cli.py` (`cmd_proto_sync` writes the snapshot)
- Create: `registry/proto_metrics.json`
- Modify: `formulation_agent007/src/formulation_agent007/catalog.py:23-215`
- Modify: `formulation_agent007/tests/conftest.py` (gate fixtures)
- Test: `formulation_agent007/tests/test_catalog_snapshot.py` (create)

**Interfaces:**
- Consumes: registry v2 from Task 4.
- Produces: `registry/proto_metrics.json` with
  `{"schema_version": 2, "tool_keys": [...], "metrics": {"<name>": {"better": "...", "tools": [...]}}, "categories": {"<category>": [...]}}`;
  and in `catalog.py`, `PROTO_TOOL_KEYS: frozenset[str]`, `PROTO_METRICS: frozenset[str]`,
  `METRIC_DIRECTION: dict[str, str]`, `cost_tier(tool_key: str) -> str` (unchanged signature).

Why this task exists beyond the spec: measured against the live catalogue,
**only 1 of 007's 59 tool keys (`pdockq2`) is a real key** — 51 are bare model
names (`esmfold`) where the catalogue uses `<model>-<action>`
(`esmfold-prediction`), and 7 match nothing. Separately, **20 of its 27 metrics
are emitted by no tool**, including `dg_fold` and `population_fraction`, both
advertised in its README. Every emitted cascade therefore names unrunnable keys.

- [ ] **Step 1: Have `proto-sync` also write the 007 snapshot**

Append to `cmd_proto_sync` in `litterature_search_from_concept/litkb/cli.py`,
before `_emit(catalog, args.out)`:

```python
    if args.snapshot:
        metrics = {}
        for t in catalog["tools"]:
            for m in t["measures"]:
                entry = metrics.setdefault(
                    m["metric"], {"better": m["better"], "tools": []})
                entry["tools"].append(t["key"])
        categories = {}
        for t in catalog["tools"]:
            categories.setdefault(t["category"] or "uncategorised", []).append(t["key"])
        snapshot = {
            "schema_version": 2,
            "note": ("Generated by `litkb proto-sync`. formulation_agent007 reads "
                     "this instead of hand-typing keys and metrics, which had "
                     "drifted to 1/59 real keys and 7/27 real metrics."),
            "tool_keys": sorted(t["key"] for t in catalog["tools"]),
            "metrics": {k: {"better": v["better"], "tools": sorted(v["tools"])}
                        for k, v in sorted(metrics.items())},
            "categories": {k: sorted(v) for k, v in sorted(categories.items())},
        }
        Path(args.snapshot).write_text(json.dumps(snapshot, indent=2) + "\n")
        print(f"  snapshot -> {args.snapshot}", file=sys.stderr)
```

Add to the `proto-sync` subparser (around `cli.py:671`):

```python
    p.add_argument("--snapshot", default="../registry/proto_metrics.json",
                   help="also write the formulation_agent007 vocabulary snapshot")
```

- [ ] **Step 2: Generate the snapshot**

```bash
cd litterature_search_from_concept
uv run --project . python -m litkb proto-sync -o ../registry/proto_catalog.json \
    --snapshot ../registry/proto_metrics.json
```

Verify:

```bash
python3 -c "
import json; s=json.load(open('registry/proto_metrics.json'))
print('keys', len(s['tool_keys']), '| metrics', len(s['metrics']))
assert 'esmfold-prediction' in s['tool_keys']
assert s['metrics']['avg_pae']['better'] == 'lower'
"
```

Expected: `keys 140 | metrics 170`.

- [ ] **Step 3: Write the failing tests**

Create `formulation_agent007/tests/test_catalog_snapshot.py`:

```python
import json
from pathlib import Path

import pytest

from formulation_agent007 import catalog

SNAPSHOT = Path(__file__).resolve().parents[2] / "registry" / "proto_metrics.json"


def test_tool_keys_come_from_the_snapshot():
    snap = json.loads(SNAPSHOT.read_text())
    assert catalog.PROTO_TOOL_KEYS == frozenset(snap["tool_keys"])


def test_real_catalogue_keys_are_accepted():
    assert catalog.unknown_tools(["esmfold-prediction", "boltz2-prediction"]) == []


def test_bare_model_names_are_now_rejected():
    """A model name alone is not a proto-tools key; 51 of the old 59 were."""
    assert catalog.unknown_tools(["esmfold"]) == ["esmfold"]


def test_metrics_no_tool_emits_are_gone():
    for absent in ("mean_plddt", "dg_fold", "population_fraction", "tm_score"):
        assert absent not in catalog.PROTO_METRICS


def test_real_metrics_are_present():
    for present in ("avg_plddt", "iptm", "perplexity"):
        assert present in catalog.PROTO_METRICS


def test_direction_is_available_per_metric():
    assert catalog.METRIC_DIRECTION["avg_pae"] == "lower"
    assert catalog.METRIC_DIRECTION["avg_plddt"] == "higher"


def test_cost_tier_resolves_by_model_family():
    # Cost is a curated judgement the registry cannot supply, so the tiers
    # stay hand-maintained -- but keyed by family so real keys resolve.
    assert catalog.cost_tier("esmfold-prediction") == "cheap"
    assert catalog.cost_tier("boltz2-prediction") == "moderate"
    assert catalog.cost_tier("bioemu-sampling") == "expensive"


def test_unknown_family_is_treated_as_costly():
    assert catalog.cost_tier("never-heard-of-it") == "expensive"


@pytest.mark.slow
def test_snapshot_matches_the_live_catalogue():
    """Marked so it never runs offline or in CI. Run by hand after a
    proto-tools upgrade: `pytest -m slow`."""
    import subprocess
    out = subprocess.run(
        ["uv", "run", "--project", "../proto", "proto-tools", "list", "--json"],
        capture_output=True, text=True, check=True).stdout
    live = {t["key"] for t in json.loads(out[out.index("["):out.rindex("]") + 1])}
    assert live == set(json.loads(SNAPSHOT.read_text())["tool_keys"]), \
        "registry/proto_metrics.json is stale; re-run `litkb proto-sync --snapshot`"
```

Register the marker in `formulation_agent007/pyproject.toml` under
`[tool.pytest.ini_options]`:

```toml
markers = ["slow: needs the proto venv and a live proto-tools catalogue"]
addopts = "-m 'not slow'"
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd formulation_agent007 && uv run --project . pytest tests/test_catalog_snapshot.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'METRIC_DIRECTION'`

- [ ] **Step 5: Rewrite the catalog vocabulary**

In `formulation_agent007/src/formulation_agent007/catalog.py`, delete the
`STRUCTURE_PREDICTION` … `NUCLEIC_ACID` sets, the `PROTO_TOOL_KEYS` union, and
the `PROTO_METRICS` / `INTERFACE_METRICS` frozensets. Replace with:

```python
import json
from pathlib import Path

# Generated by `litkb proto-sync --snapshot`. Committed so this project stays
# offline and has no runtime dependency on the `proto` venv.
#
# This replaces a hand-transcribed list that had drifted badly: measured
# against the live catalogue, 1 of its 59 tool keys was real (the rest were
# bare model names, where proto-tools keys are `<model>-<action>`), and 20 of
# its 27 metrics were emitted by no tool at all. A hallucination guard that
# rejects the real names and accepts invented ones is worse than none.
_SNAPSHOT_PATH = Path(__file__).resolve().parents[3] / "registry" / "proto_metrics.json"

with _SNAPSHOT_PATH.open() as _fh:
    _SNAPSHOT = json.load(_fh)

PROTO_TOOL_KEYS: frozenset[str] = frozenset(_SNAPSHOT["tool_keys"])
PROTO_METRICS: frozenset[str] = frozenset(_SNAPSHOT["metrics"])
METRIC_DIRECTION: dict[str, str] = {
    name: spec["better"] for name, spec in _SNAPSHOT["metrics"].items()
}
TOOLS_BY_CATEGORY: dict[str, list[str]] = _SNAPSHOT["categories"]

# A metric is an interface metric when every tool emitting it is a complex
# scorer. Derived rather than listed, so it cannot drift independently.
INTERFACE_METRICS: frozenset[str] = frozenset(
    name for name in _SNAPSHOT["metrics"]
    if name.startswith(("iptm", "chain_pair_iptm", "ipsae", "pdockq"))
    or "interface" in name
    or "iplddt" in name
)
```

Then make cost tiers family-based. Replace the `CHEAP` / `MODERATE` / `EXPENSIVE`
sets and `cost_tier` with:

```python
# Cost is a curated engineering judgement that the registry cannot supply, so
# these stay hand-maintained -- but keyed by MODEL FAMILY (the part before the
# first '-') so that real `<model>-<action>` keys resolve.
CHEAP_FAMILIES = {
    "ablang", "blast", "codonfm", "dssp", "esm2", "esm3", "esmc", "esm_if1",
    "esmfold", "esmfold2", "evo1", "evo2", "foldmason", "foldseek", "mafft",
    "mmseqs2", "progen2", "progen3", "proteinmpnn", "tmalign", "usalign",
    "uniprot", "pdb", "ncbi", "ensembl", "alphafold",
}
MODERATE_FAMILIES = {
    "boltz2", "chai1", "protenix", "ligandmpnn", "fampnn", "metal3d",
    "pdockq2", "ipsae", "vina", "pyrosetta", "opendde",
}
EXPENSIVE_FAMILIES = {
    "alphafold2", "alphafold3", "rf3", "bioemu", "bindcraft", "freebindcraft",
    "germinal",
}

COST_TIERS = ("cheap", "moderate", "expensive")
_COST_RANK = {tier: i for i, tier in enumerate(COST_TIERS)}


def _family(tool_key: str) -> str:
    return tool_key.split("-", 1)[0]


def cost_tier(tool_key: str) -> str:
    """Best-known cost tier for a tool key; unknown families are costly."""
    family = _family(tool_key)
    if family in EXPENSIVE_FAMILIES:
        return "expensive"
    if family in MODERATE_FAMILIES:
        return "moderate"
    if family in CHEAP_FAMILIES:
        return "cheap"
    return "expensive"
```

Finally, rewrite `catalogue_digest()` to group from `TOOLS_BY_CATEGORY` rather
than the deleted sets:

```python
def catalogue_digest() -> str:
    """Compact tool listing for a prompt. Grouped so selection is informed."""
    lines = []
    for category, keys in sorted(TOOLS_BY_CATEGORY.items()):
        lines.append(f"{category.replace('_', ' ')}: {', '.join(sorted(keys))}")
    return "\n".join(lines)
```

- [ ] **Step 6: Update the test fixtures to use real keys and metrics**

In `formulation_agent007/tests/conftest.py`, the `proto` fixture uses metrics and
keys that no longer validate. Change the four gates to:

- gate 1: `tool_keys=["esmfold-prediction"]`, `metric="avg_plddt"`, `threshold=0.75`
- gate 2: `tool_keys=["boltz2-prediction"]`, `metric="iptm"`, `operator="<="`, `threshold=0.45`
- gate 3: `tool_keys=["boltz2-prediction"]`, `metric="iptm"`, `operator=">="`, `threshold=0.8`
- gate 4: `tool_keys=["boltz2-prediction"]`, `metric="confidence_score"`,
  `operator="between"`, `threshold=0.15`, `threshold_upper=0.85`,
  `cost_tier="moderate"`

Gate 4 changes tool and metric because `bioemu` publishes no metrics block, so
no gate can threshold on it until it does. Note that in the fixture's
`known_limitations`.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd formulation_agent007 && uv run --project . pytest -q`
Expected: all pass, including the pre-existing 44.

- [ ] **Step 8: Commit**

```bash
git add registry/proto_metrics.json litterature_search_from_concept/litkb/cli.py \
        formulation_agent007/src/formulation_agent007/catalog.py \
        formulation_agent007/tests formulation_agent007/pyproject.toml
git commit -m "fix(007): load tool keys and metrics from the generated registry snapshot"
```

### Task 9: Reject gates whose direction contradicts the metric

**Files:**
- Modify: `formulation_agent007/src/formulation_agent007/validate.py:278-282`
- Test: `formulation_agent007/tests/test_gate_direction.py` (create)

**Interfaces:**
- Consumes: `catalog.METRIC_DIRECTION` from Task 8.
- Produces: no new public names; extends the `problems` list `validate_gates` returns.

- [ ] **Step 1: Write the failing tests**

Create `formulation_agent007/tests/test_gate_direction.py`:

```python
import pytest

from formulation_agent007 import validate
from formulation_agent007.models import FitnessGate, GateState, ProtoBrief


def _gate(metric, operator, **kw):
    return FitnessGate(
        order=1, name="g", purpose="p", tool_keys=["esmfold-prediction"],
        input_description="d", state=GateState.SINGLE, metric=metric,
        operator=operator, threshold=0.5, kill_rule="drop", cost_tier="cheap",
        **kw)


def _problems(gate):
    """A one-gate brief trips unrelated rules (no decisive gate, and so on),
    so filter to the direction check this task adds."""
    all_problems = validate.validate_proto(ProtoBrief(gates=[gate]))
    return [p for p in all_problems if "direction is inverted" in p]


def test_higher_is_better_metric_with_a_ceiling_is_rejected():
    # avg_plddt is better=higher, so `<= 0.5` gates out the GOOD candidates.
    assert _problems(_gate("avg_plddt", "<="))


def test_higher_is_better_metric_with_a_floor_is_accepted():
    assert _problems(_gate("avg_plddt", ">=")) == []


def test_lower_is_better_metric_with_a_floor_is_rejected():
    assert _problems(_gate("avg_pae", ">="))


def test_lower_is_better_metric_with_a_ceiling_is_accepted():
    assert _problems(_gate("avg_pae", "<=")) == []


def test_between_is_never_a_direction_error():
    gate = _gate("avg_plddt", "between", threshold_upper=0.9)
    assert _problems(gate) == []


def test_context_metrics_are_exempt():
    """`better=context-dependent` means direction is not decidable; do not guess."""
    from formulation_agent007 import catalog
    contextual = [m for m, d in catalog.METRIC_DIRECTION.items()
                  if d == "context-dependent"]
    if not contextual:
        pytest.skip("no better=context metrics in the current snapshot")
    assert _problems(_gate(contextual[0], ">=")) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd formulation_agent007 && uv run --project . pytest tests/test_gate_direction.py -q`
Expected: FAIL — the direction problems are never produced, so the "rejected"
tests fail.

- [ ] **Step 3: Add the direction check**

In `formulation_agent007/src/formulation_agent007/validate.py`, extend the
existing catalog import block (currently at lines 27–33) to:

```python
from .catalog import (
    INTERFACE_METRICS,
    METRIC_DIRECTION,
    PROTO_METRICS,
    cost_rank,
    gate_cost_tier,
    unknown_tools,
)
```

Then insert this inside `validate_proto`'s `for gate in gates:` loop, after the
`gate.metric not in PROTO_METRICS` block:

```python
        # A gate thresholding a better=higher metric with `<=` keeps the worst
        # candidates and kills the best. The cascade still reads fluently, which
        # is exactly why this needs checking mechanically.
        direction = METRIC_DIRECTION.get(gate.metric)
        if direction and gate.operator != "between":
            floor = gate.operator in (">=", ">")
            if direction == "higher" and not floor:
                problems.append(
                    f"gate {gate.order} keeps {gate.metric!r} {gate.operator} "
                    f"{gate.threshold:g}, but higher is better for that metric; "
                    f"the direction is inverted"
                )
            elif direction == "lower" and floor:
                problems.append(
                    f"gate {gate.order} keeps {gate.metric!r} {gate.operator} "
                    f"{gate.threshold:g}, but lower is better for that metric; "
                    f"the direction is inverted"
                )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd formulation_agent007 && uv run --project . pytest tests/test_gate_direction.py -q`
Expected: `6 passed`

- [ ] **Step 5: Run the whole 007 suite**

Run: `cd formulation_agent007 && uv run --project . pytest -q`
Expected: all pass. If a conftest gate now trips the direction check, the
fixture is wrong — fix the fixture, not the check.

- [ ] **Step 6: Commit**

```bash
git add formulation_agent007/src/formulation_agent007/validate.py formulation_agent007/tests/test_gate_direction.py
git commit -m "feat(007): reject fitness gates whose comparison inverts the metric direction"
```

---

## Phase 5 — litkb becomes the default handoff

### Task 10: Collapse the mirrored `validate_plan` into one shared module

**Files:**
- Create: `litterature_search_from_concept/plan_contract.py`
- Modify: `litterature_search_from_concept/paperclip_kb.py:67-82`
- Modify: `litterature_search_from_concept/litkb/contracts.py:66-82`
- Test: `litterature_search_from_concept/tests/test_plan_contract.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `plan_contract.BRIEF_PLAN_KEYS: tuple[str, ...]`;
  `plan_contract.check(plan) -> list[str]` (errors, empty when valid).
  `contracts.validate_brief_plan` and `paperclip_kb.validate_plan` both delegate
  to it and keep their existing signatures and exception behaviour.

The module lives at the project root (not inside `litkb/`) and imports nothing,
which is what `contracts.py`'s comment asks for: it mirrors rather than imports
"so litkb has no import dependency on the sibling script". A shared
dependency-free module honours that reason instead of overriding it.

- [ ] **Step 1: Write the failing tests**

Create `litterature_search_from_concept/tests/test_plan_contract.py`:

```python
import pytest

import plan_contract
from litkb import contracts

GOOD = {"search_phrases": ["a phrase here"], "mechanism_patterns": ["a pattern"],
        "notes": "why things were left out"}


def test_valid_plan_has_no_errors():
    assert plan_contract.check(GOOD) == []


def test_missing_key_is_named():
    plan = {k: v for k, v in GOOD.items() if k != "notes"}
    assert "notes" in plan_contract.check(plan)[0]


def test_empty_list_is_rejected():
    plan = dict(GOOD, search_phrases=[])
    assert any("search_phrases" in e for e in plan_contract.check(plan))


def test_non_string_entries_are_rejected():
    plan = dict(GOOD, mechanism_patterns=[1, 2])
    assert any("mechanism_patterns" in e for e in plan_contract.check(plan))


def test_litkb_and_the_script_agree_on_every_case():
    """The anti-drift guarantee, now structural rather than by inspection."""
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "paperclip_kb.py"
    spec = importlib.util.spec_from_file_location("paperclip_kb", path)
    kb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kb)

    cases = [GOOD,
             {k: v for k, v in GOOD.items() if k != "notes"},
             dict(GOOD, search_phrases=[]),
             dict(GOOD, notes=123)]
    for plan in cases:
        litkb_errors = contracts.validate_brief_plan(plan)
        try:
            kb.validate_plan(plan)
            kb_failed = False
        except (TypeError, ValueError):
            kb_failed = True
        assert bool(litkb_errors) == kb_failed, plan
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_plan_contract.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'plan_contract'`

- [ ] **Step 3: Write the shared module**

Create `litterature_search_from_concept/plan_contract.py`:

```python
"""The design-brief plan contract, in exactly one place.

`design-brief-007` emits a FLAT plan with three keys. Both consumers here --
`paperclip_kb.py` and `litkb` -- must accept precisely the same set, and they
used to enforce it with two hand-mirrored copies. This module imports
nothing, so sharing it does not give litkb an import dependency on the
sibling script, which is the reason the mirror existed.

See .claude/skills/design-brief-007/references/handoff-contract.md.
"""

BRIEF_PLAN_KEYS = ("search_phrases", "mechanism_patterns", "notes")


def check(plan):
    """Return a list of problems; empty means the plan is acceptable."""
    if not isinstance(plan, dict):
        return ["brief plan must be a JSON object"]

    missing = [k for k in BRIEF_PLAN_KEYS if k not in plan]
    if missing:
        return [f"brief plan is missing required key(s): {', '.join(missing)}"]

    errors = []
    for key in ("search_phrases", "mechanism_patterns"):
        values = plan[key]
        if not isinstance(values, list) or not values:
            errors.append(f"brief plan.{key} must be a non-empty list")
        elif not all(isinstance(v, str) and v.strip() for v in values):
            errors.append(f"brief plan.{key} must contain non-empty strings")
    if not isinstance(plan.get("notes"), str):
        errors.append("brief plan.notes must be a string")
    return errors
```

- [ ] **Step 4: Delegate from both consumers**

In `litterature_search_from_concept/litkb/contracts.py`, replace the
`BRIEF_PLAN_KEYS` constant and the body of `validate_brief_plan` with:

```python
from plan_contract import BRIEF_PLAN_KEYS, check as _check_brief_plan


def validate_brief_plan(plan):
    return _check_brief_plan(plan)
```

In `litterature_search_from_concept/paperclip_kb.py`, replace the body of
`validate_plan` (keeping its raising contract, which callers depend on):

```python
def validate_plan(plan: object) -> dict:
    import plan_contract

    if not isinstance(plan, dict):
        raise TypeError("plan must be a JSON object")
    errors = plan_contract.check(plan)
    if errors:
        if any("must be a string" in e for e in errors):
            raise TypeError("; ".join(errors))
        raise ValueError("; ".join(errors))
    return plan
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd litterature_search_from_concept && uv run --project . pytest -q`
Expected: all pass, including `tests/test_paperclip_kb.py` and
`tests/test_plan_adopt.py`.

- [ ] **Step 6: Confirm 007's cross-project check still passes**

Run: `cd formulation_agent007 && uv run --project . pytest tests/test_emit.py -q`
Expected: pass — `conftest.py` still imports the real `paperclip_kb.validate_plan`
by path, so the anti-drift guarantee is preserved through the delegation.

- [ ] **Step 7: Commit**

```bash
git add litterature_search_from_concept/plan_contract.py litterature_search_from_concept/litkb/contracts.py \
        litterature_search_from_concept/paperclip_kb.py litterature_search_from_concept/tests/test_plan_contract.py
git commit -m "refactor: one shared brief-plan contract instead of two mirrored copies"
```

### Task 11: Emit the litkb chain as the default handoff

**Files:**
- Modify: `formulation_agent007/src/formulation_agent007/emit.py:29,95-147`
- Test: `formulation_agent007/tests/test_run_script.py` (create)

**Interfaces:**
- Consumes: nothing from Tasks 8–10.
- Produces: `run_literature.sh` containing two labelled blocks. `emit.KB_SCRIPT`
  is retained; `emit.LITKB_DIR = "litterature_search_from_concept"` is added.

- [ ] **Step 1: Write the failing tests**

Create `formulation_agent007/tests/test_run_script.py`:

```python
from pathlib import Path

from formulation_agent007.emit import save_brief


def _script(brief, tmp_path) -> str:
    save_brief(brief, str(tmp_path))
    return (tmp_path / "run_literature.sh").read_text()


def test_litkb_chain_is_the_default_block(brief, tmp_path):
    script = _script(brief, tmp_path)
    for stage in ("plan-adopt", "search", "screen", "dig", "bind",
                  "evidence", "report", "manifest"):
        assert f"litkb {stage}" in script or f"-m litkb {stage}" in script


def test_grep_path_is_retained_and_labelled(brief, tmp_path):
    script = _script(brief, tmp_path)
    assert "paperclip_kb.py" in script
    assert "no LLM read quota" in script


def test_litkb_block_precedes_the_grep_block(brief, tmp_path):
    script = _script(brief, tmp_path)
    assert script.index("plan-adopt") < script.index("paperclip_kb.py")


def test_script_names_the_directory_litkb_must_run_from(brief, tmp_path):
    # litkb's --registry and --project defaults are relative to that directory.
    script = _script(brief, tmp_path)
    assert "cd litterature_search_from_concept" in script


def test_script_is_still_bash_strict_mode(brief, tmp_path):
    assert "set -euo pipefail" in _script(brief, tmp_path)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd formulation_agent007 && uv run --project . pytest tests/test_run_script.py -q`
Expected: FAIL — `assert 'litkb plan-adopt' in script`

- [ ] **Step 3: Rewrite `_run_script`**

In `formulation_agent007/src/formulation_agent007/emit.py`, add beside `KB_SCRIPT`:

```python
LITKB_DIR = "litterature_search_from_concept"
```

Replace the `return f"""..."""` block at the end of `_run_script` with:

```python
    plan_rel = f"../{plan}" if not plan.startswith("/") else plan
    run_rel = f"../{run_dir}" if not run_dir.startswith("/") else run_dir

    return f"""#!/usr/bin/env bash
# Literature mining for: {brief.question}
# Run from the repository root. Requires `paperclip` on PATH.
set -euo pipefail

# ---------------------------------------------------------------------------
# DEFAULT PATH -- litkb: typed evidence and tool-bound sequences.
#
# Reads full text with `paperclip map` and emits EvidenceItem / ProtoArtifact
# records rather than grep lines. Costs LLM reads, which are capped per day.
# `-n` caps papers per query and is the cost dial -- start small.
#
# Must run from {LITKB_DIR}/: litkb's --registry and --project
# defaults are relative to that directory.
# ---------------------------------------------------------------------------
cd {LITKB_DIR}

uv run --project . python -m litkb plan-adopt {plan_rel} \\
    --objective {shlex.quote(brief.question)} --slug {slug} --output-dir {run_rel}
uv run --project . python -m litkb search   {run_rel}/plan_{slug}.json -n 4 --output-dir {run_rel}
uv run --project . python -m litkb screen   {run_rel}/search_{slug}.json -n 1 --output-dir {run_rel}
uv run --project . python -m litkb dig      {run_rel}/screen_{slug}.json --output-dir {run_rel}
uv run --project . python -m litkb bind     {run_rel}/dig_{slug}.json --output-dir {run_rel}
uv run --project . python -m litkb evidence {run_rel}/screen_{slug}.json --output-dir {run_rel}
uv run --project . python -m litkb report   {run_rel}/evidence_{slug}.json \\
    --search {run_rel}/search_{slug}.json --artifacts {run_rel}/artifacts_{slug}.json \\
    --output-dir {run_rel}
uv run --project . python -m litkb manifest {run_rel}/evidence_{slug}.json --output-dir {run_rel}
cd -

# Every evidence item lands with testable_by.requires_new_evaluator =
# "unassessed". Run `litkb label` to assign vocabulary terms from
# registry/property_vocabulary.json; until then no claim is made about what
# can test it.

# ---------------------------------------------------------------------------
# ALTERNATIVE PATH -- paperclip_kb.py: regex grep, no LLM read quota.
#
# Cheaper reconnaissance over the same corpus. Emits a categorized knowledge
# base rather than typed records. Use when the daily read cap matters more
# than machine-consumable output.
# ---------------------------------------------------------------------------

# 1. Dry run. Validates plan_{slug}.json through the shared brief-plan
#    contract and prints every search command without issuing one.
{dry}

# 2. Real run, same reviewed plan. This one searches.
{live}

# Outputs land in {run_dir}/:
#   plan_{slug}.json            the phrases and patterns actually used
#   knowledge_base_{slug}.txt   categorized grep hits
#   manifest_{slug}.json        set id + evidence_status=discovery_only_unverified
"""
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd formulation_agent007 && uv run --project . pytest tests/test_run_script.py -q`
Expected: `5 passed`

- [ ] **Step 5: Update the skill and README references**

In `.claude/skills/design-brief-007/SKILL.md` and
`formulation_agent007/README.md`, the `run_literature.sh` row currently reads
"the two mining commands, dry run first". Change it to "the litkb chain, plus
the grep path as an alternative". In
`litterature_search_from_concept/readme.txt`, replace the "WHICH ONE" paragraph
ending "a team decision that has not been taken" with:

```
design-brief-007 now emits the litkb chain as the default handoff, with the
paperclip_kb.py commands retained in the same script as the cheaper path with
no LLM read quota. Decision recorded in
docs/superpowers/specs/2026-08-16-registry-vocabulary-sweep-design.md.
```

- [ ] **Step 6: Run every suite**

```bash
(cd litterature_search_from_concept && uv run --project . pytest -q)
(cd formulation_agent007        && uv run --project . pytest -q)
(cd formulation_agent           && uv run --project . pytest -q -m "not live")
(cd biophysical_triage_pipeline && uv run --project . pytest -q)
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add formulation_agent007 litterature_search_from_concept/readme.txt .claude/skills/design-brief-007/SKILL.md
git commit -m "feat(007): emit the litkb chain as the default literature handoff"
```

---

## Final verification

- [ ] **Confirm the RF run still reads honestly**

The point of the whole change is that the answer is earned, not that it flips.

```bash
python3 -c "
import json
e=json.load(open('litterature_search_from_concept/outputs/20260816T043704Z-rfp/evidence_rfp.json'))
print('this committed run is historical and untouched:', 'schema_version' not in e)
"
```

Expected: `True` — Task 6 added `schema_version: 2` to newly written evidence
only. Historical runs are records and are not rewritten.

- [ ] **Confirm the vocabulary invariant holds against the committed registry**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_vocabulary.py -q`
Expected: pass. This is the check that stops the vocabulary rotting as the
catalogue moves; it must be green before merge.
