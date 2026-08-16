# litkb Proto-Bounded Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace litkb's grep-based extraction with two-tier full-text LLM reading, and keep only structural artifacts that a proto-tools tool can actually accept.

**Architecture:** `proto-sync` parses the local proto-tools registry into a constraint catalogue. `screen` and `dig` read paper full text via `paperclip map` with locked output schemas. `bind` verifies each extracted sequence against the catalogue with three-valued checks and re-greps it against its source document to catch fabrication. The grep-based `extract` stage and its `STRUCTURAL` pattern table are deleted.

**Tech Stack:** Python ≥3.10, `uv` for the venv, `pytest`, the `paperclip` CLI (0.7.36), the `proto-tools` CLI (run via `uv run --project proto`).

**Spec:** `docs/superpowers/specs/2026-08-15-litkb-proto-extraction-design.md`

## Global Constraints

- Python ≥ 3.10. Both `litkb` and `paperclip` use `str | None`; a 3.9 interpreter fails at import.
- `paperclip` must be on PATH and authenticated (`paperclip config` shows `Auth: ✓`). `paperclip login` is an interactive browser flow — never attempt it non-interactively.
- Never call the Anthropic API directly. All LLM work goes through `paperclip map`.
- Constraint checks are three-valued: `pass` / `fail` / `unknown`. **`unknown` never counts as `pass`.**
- An artifact reaches `artifacts[]` only when `verbatim` is true AND `confirmed_in_source` is true AND at least one tool returns `pass` on every check.
- Run all commands from `litterature_search_from_concept/`.
- `proto-tools` is invoked as `uv run --project ../proto proto-tools <verb>` and never guessed at — read tool keys and constraints from its output.

---

### Task 1: Test harness and proto catalogue sync

**Files:**
- Create: `litterature_search_from_concept/pyproject.toml`
- Create: `litterature_search_from_concept/litkb/proto.py`
- Test: `litterature_search_from_concept/tests/test_proto.py`

**Interfaces:**
- Consumes: nothing
- Produces: `proto.parse_input_doc(text: str) -> dict` returning keys `input_kind`, `molecules`, `max_length`, `constraint_source`; `proto.build_catalog(tools: list[dict], doc_fetcher: Callable[[str], str]) -> dict`

- [ ] **Step 1: Create the project file**

`litterature_search_from_concept/pyproject.toml`:

```toml
[project]
name = "litkb"
version = "0.2.0"
requires-python = ">=3.10"
dependencies = []

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.uv]
package = false

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write the failing test**

`litterature_search_from_concept/tests/test_proto.py`:

```python
from litkb import proto

ESMFOLD_DOC = """Input: ESMFoldInput
Attributes:
    complexes (list[Complex]): The linked length actually
        folded must not exceed 2,400.
Note:
    ESMFold only supports protein sequences (amino acids). DNA, RNA, ligands,
    and glycans are not supported.

  complexes                 list[Complex]                   (required)
"""

ESM2_DOC = """Input: ESM2ScoringInput
Attributes:
    sequences (list[str]): Protein sequence(s) to score. Each must be <= 1022
        residues (ESM-2's positional-encoding cap).

  sequences                 list[str]                       (required)
"""

MPNN_DOC = """Input: InverseFoldingInput
Attributes:
    inputs (list[InverseFoldingStructureInput]): Per-structure inputs.

  sequence_structure_pairs  list[SequenceStructurePair]     (required)
"""


def test_parses_length_cap_with_thousands_separator():
    assert proto.parse_input_doc(ESMFOLD_DOC)["max_length"] == 2400


def test_parses_length_cap_with_comparison_operator():
    assert proto.parse_input_doc(ESM2_DOC)["max_length"] == 1022


def test_protein_only_tool_lists_one_molecule():
    assert proto.parse_input_doc(ESMFOLD_DOC)["molecules"] == ["protein"]


def test_sequence_input_kind_detected():
    assert proto.parse_input_doc(ESM2_DOC)["input_kind"] == "sequence"


def test_structure_input_kind_detected():
    assert proto.parse_input_doc(MPNN_DOC)["input_kind"] == "structure"


def test_unparseable_length_is_none_not_zero():
    assert proto.parse_input_doc(MPNN_DOC)["max_length"] is None


def test_build_catalog_carries_key_and_category():
    tools = [{"key": "esm2-score", "category": "sequence_scoring", "uses_gpu": True}]
    cat = proto.build_catalog(tools, lambda key: ESM2_DOC)
    entry = cat["tools"][0]
    assert entry["key"] == "esm2-score"
    assert entry["category"] == "sequence_scoring"
    assert entry["max_length"] == 1022
    assert entry["status"] == "needs_calibration"
    assert entry["measures"] == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --project . pytest tests/test_proto.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'litkb.proto'`

- [ ] **Step 4: Write the implementation**

`litterature_search_from_concept/litkb/proto.py`:

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --project . pytest tests/test_proto.py -v`
Expected: PASS, 7 tests

- [ ] **Step 6: Commit**

```bash
git add litterature_search_from_concept/pyproject.toml litterature_search_from_concept/litkb/proto.py litterature_search_from_concept/tests/test_proto.py
git commit -m "feat(litkb): parse proto-tools constraints into a catalogue"
```

---

### Task 2: Three-valued constraint checking

**Files:**
- Modify: `litterature_search_from_concept/litkb/proto.py`
- Test: `litterature_search_from_concept/tests/test_proto_checks.py`

**Interfaces:**
- Consumes: catalogue entries from `proto.build_catalog`
- Produces: `proto.check(artifact: dict, tool: dict) -> dict[str, str]` where each value starts with `pass`, `fail`, or `unknown`; `proto.bind_artifact(artifact: dict, catalog: dict) -> dict` returning `{"status", "tools", "rejected_by"}`

- [ ] **Step 1: Write the failing test**

`litterature_search_from_concept/tests/test_proto_checks.py`:

```python
from litkb import proto

ESM2 = {"key": "esm2-score", "input_kind": "sequence", "molecules": ["protein"],
        "alphabet": proto.PROTEIN_ALPHABET, "max_length": 1022}
NOCAP = {"key": "mystery", "input_kind": "sequence", "molecules": ["protein"],
         "alphabet": proto.PROTEIN_ALPHABET, "max_length": None}
MPNN = {"key": "proteinmpnn-score", "input_kind": "structure",
        "molecules": ["protein"], "alphabet": None, "max_length": None}

PROTEIN = {"kind": "sequence", "molecule": "protein", "value": "MKVAAL", "length": 6}
DNA = {"kind": "sequence", "molecule": "dna", "value": "ATGGCC", "length": 6}
LONG = {"kind": "sequence", "molecule": "protein", "value": "M" * 2000, "length": 2000}
BAD_CHARS = {"kind": "sequence", "molecule": "protein", "value": "MKVJJZ", "length": 6}


def test_valid_protein_passes_every_check():
    checks = proto.check(PROTEIN, ESM2)
    assert all(v.startswith("pass") for v in checks.values())


def test_dna_fails_molecule_check():
    assert proto.check(DNA, ESM2)["molecule"].startswith("fail")


def test_over_length_fails():
    assert proto.check(LONG, ESM2)["max_length"].startswith("fail")


def test_non_alphabet_characters_fail():
    assert proto.check(BAD_CHARS, ESM2)["alphabet"].startswith("fail")


def test_missing_cap_is_unknown_not_pass():
    assert proto.check(PROTEIN, NOCAP)["max_length"] == "unknown"


def test_structure_tool_rejects_bare_sequence():
    assert proto.check(PROTEIN, MPNN)["input_kind"].startswith("fail")


def test_bind_marks_runnable_when_a_tool_fully_passes():
    result = proto.bind_artifact(PROTEIN, {"tools": [ESM2, MPNN]})
    assert result["status"] == "runnable"
    assert result["tools"][0]["key"] == "esm2-score"
    assert result["rejected_by"][0]["key"] == "proteinmpnn-score"


def test_bind_is_unverified_when_only_unknowns_stand_between_it_and_pass():
    result = proto.bind_artifact(PROTEIN, {"tools": [NOCAP]})
    assert result["status"] == "unverified"


def test_bind_rejects_when_every_tool_fails():
    result = proto.bind_artifact(DNA, {"tools": [ESM2]})
    assert result["status"] == "rejected"
    assert result["tools"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project . pytest tests/test_proto_checks.py -v`
Expected: FAIL with `AttributeError: module 'litkb.proto' has no attribute 'check'`

- [ ] **Step 3: Write the implementation**

Append to `litterature_search_from_concept/litkb/proto.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project . pytest tests/test_proto_checks.py -v`
Expected: PASS, 9 tests

- [ ] **Step 5: Commit**

```bash
git add litterature_search_from_concept/litkb/proto.py litterature_search_from_concept/tests/test_proto_checks.py
git commit -m "feat(litkb): three-valued proto constraint checks and artifact binding"
```

---

### Task 3: proto-sync and registry-check on the new catalogue

**Files:**
- Modify: `litterature_search_from_concept/litkb/cli.py`
- Test: `litterature_search_from_concept/tests/test_registry.py`

**Interfaces:**
- Consumes: `proto.fetch_tools`, `proto.fetch_input_doc`, `proto.build_catalog`
- Produces: CLI `proto-sync -o registry/proto_catalog.json`; `cmd_registry_check` reading `proto_catalog.json` and resolving `candidate_evaluators` against tool keys

- [ ] **Step 1: Write the failing test**

`litterature_search_from_concept/tests/test_registry.py`:

```python
import json
from litkb import cli

CATALOG = {"tools": [
    {"key": "esmfold-prediction", "category": "structure_prediction",
     "measures": ["fold_confidence"], "status": "validated"},
    {"key": "esm2-score", "category": "sequence_scoring",
     "measures": ["sequence_likelihood"], "status": "needs_calibration"},
]}


def _plan(evaluators):
    return {"objective": "o", "slug": "s", "mechanism_classes": [
        {"id": "c1", "question": "q", "search_phrases": ["p"],
         "mechanism_patterns": ["m"], "candidate_evaluators": evaluators}]}


def test_class_with_validated_tool_is_full(tmp_path):
    result = cli.resolve_coverage(_plan(["esmfold-prediction"]), CATALOG)
    assert result[0]["evaluator_coverage"] == "full"


def test_class_with_uncalibrated_tool_is_partial(tmp_path):
    result = cli.resolve_coverage(_plan(["esm2-score"]), CATALOG)
    assert result[0]["evaluator_coverage"] == "partial"
    assert result[0]["uncalibrated"] == ["esm2-score"]


def test_class_with_no_tool_requires_new_evaluator(tmp_path):
    result = cli.resolve_coverage(_plan([]), CATALOG)
    assert result[0]["requires_new_evaluator"] is True


def test_unknown_tool_key_is_unresolved(tmp_path):
    result = cli.resolve_coverage(_plan(["spin-dynamics-sim"]), CATALOG)
    assert result[0]["unresolved"] == ["spin-dynamics-sim"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project . pytest tests/test_registry.py -v`
Expected: FAIL with `AttributeError: module 'litkb.cli' has no attribute 'resolve_coverage'`

- [ ] **Step 3: Extract the resolver and add proto-sync**

In `litterature_search_from_concept/litkb/cli.py`, replace the body of `cmd_registry_check` with a call to a new module-level function, and add the sync command:

```python
def resolve_coverage(plan, catalog):
    """Resolve each mechanism class against the proto catalogue.

    §6: an uncalibrated evaluator may run but may not rank, so a class is
    `full` only when every tool it names is both known and validated."""
    known = {t["key"]: t for t in catalog["tools"]}
    classes = []
    for c in plan["mechanism_classes"]:
        wanted = c.get("candidate_evaluators", [])
        bound = [w for w in wanted if w in known]
        usable = [b for b in bound if known[b].get("status") == "validated"]
        if not wanted or not bound:
            coverage = "none"
        elif len(bound) == len(wanted) and len(usable) == len(bound):
            coverage = "full"
        else:
            coverage = "partial"
        classes.append({
            "id": c["id"],
            "evaluator_coverage": coverage,
            "bound": bound,
            "unresolved": [w for w in wanted if w not in known],
            "uncalibrated": [b for b in bound if b not in usable],
            "requires_new_evaluator": coverage == "none",
        })
    return classes


def cmd_proto_sync(args):
    tools = proto.fetch_tools(args.project)
    print(f"  {len(tools)} tools from proto-tools", file=sys.stderr)
    catalog = proto.build_catalog(tools, lambda k: proto.fetch_input_doc(k, args.project))
    parsed = sum(1 for t in catalog["tools"] if t["max_length"] is not None)
    print(f"  {parsed}/{len(tools)} have a parseable length cap", file=sys.stderr)
    _emit(catalog, args.out)


def cmd_registry_check(args):
    plan = _load(args.plan)
    path = Path(args.registry)
    if not path.exists():
        _emit({"registry": str(path), "status": "missing",
               "classes": [{"id": c["id"], "evaluator_coverage": "unknown"}
                           for c in plan["mechanism_classes"]],
               "note": "run `litkb proto-sync -o registry/proto_catalog.json` first"},
              args.out)
        return
    _emit({"registry": str(path), "status": "loaded",
           "classes": resolve_coverage(plan, _load(path))}, args.out)
```

Add `from . import proto` to the imports, and register the subcommand next to the others:

```python
    p = sub.add_parser("proto-sync", help="regenerate the proto-tools constraint catalogue")
    p.add_argument("--project", default="../proto")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_proto_sync)
```

Change the `registry-check` default: `p.add_argument("--registry", default="../registry/proto_catalog.json")`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project . pytest tests/test_registry.py -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Generate the real catalogue**

Run: `uv run --project . python -m litkb proto-sync -o ../registry/proto_catalog.json`
Expected: stderr reports 140 tools and a parseable-cap count; the file exists.

- [ ] **Step 6: Commit**

```bash
git add litterature_search_from_concept/litkb/cli.py litterature_search_from_concept/tests/test_registry.py registry/proto_catalog.json
git commit -m "feat(litkb): proto-sync command; registry-check reads the proto catalogue"
```

---

### Task 4: CSV keyword import and semantic search

**Files:**
- Modify: `litterature_search_from_concept/litkb/cli.py`
- Modify: `litterature_search_from_concept/litkb/paperclip.py:47-60`
- Test: `litterature_search_from_concept/tests/test_plan_import.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `cli.rows_to_plan(rows: list[str], objective: str, slug: str, groups: dict[str, list[str]]) -> dict`; `paperclip.search(phrase, sources, n, exact=False)` gains an `exact` keyword defaulting to `False`

- [ ] **Step 1: Write the failing test**

`litterature_search_from_concept/tests/test_plan_import.py`:

```python
from litkb import cli, contracts

ROWS = ["CraCRY ODMR", "MagLOV ODMR", "magnetothermal protein switch"]
GROUPS = {"cryptochrome_rf": ["CraCRY ODMR"],
          "lov_radical_pair": ["MagLOV ODMR"],
          "magnetothermal": ["magnetothermal protein switch"]}


def test_every_row_lands_in_exactly_one_class():
    plan = cli.rows_to_plan(ROWS, "objective", "rfp", GROUPS)
    placed = [p for c in plan["mechanism_classes"] for p in c["search_phrases"]]
    assert sorted(placed) == sorted(ROWS)


def test_generated_plan_is_schema_valid():
    plan = cli.rows_to_plan(ROWS, "objective", "rfp", GROUPS)
    assert contracts.validate_plan(plan) == []


def test_ungrouped_row_raises_rather_than_being_dropped():
    try:
        cli.rows_to_plan(ROWS + ["orphan keyword"], "o", "rfp", GROUPS)
    except contracts.ContractError as e:
        assert "orphan keyword" in str(e)
    else:
        raise AssertionError("expected ContractError for an ungrouped row")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project . pytest tests/test_plan_import.py -v`
Expected: FAIL with `AttributeError: module 'litkb.cli' has no attribute 'rows_to_plan'`

- [ ] **Step 3: Write the implementation**

Add to `litterature_search_from_concept/litkb/cli.py`:

```python
def rows_to_plan(rows, objective, slug, groups):
    """Turn curated keyword rows into a class-structured plan.

    Rows are expert-written keyword bags, not verbatim phrases, so they are
    searched semantically. An ungrouped row is an error rather than a silent
    drop -- losing an expert query without saying so is the failure mode this
    guards against."""
    grouped = {r for rs in groups.values() for r in rs}
    orphans = [r for r in rows if r not in grouped]
    if orphans:
        raise contracts.ContractError(
            f"rows not assigned to any mechanism class: {orphans}")

    return {
        "objective": objective,
        "slug": slug,
        "search_mode": "semantic",
        "mechanism_classes": [
            {"id": cid,
             "question": f"What does the literature say about {cid.replace('_', ' ')}?",
             "candidate_evaluators": [],
             "search_phrases": phrases,
             "mechanism_patterns": ["mechanism"]}
            for cid, phrases in groups.items()
        ],
        "exclusions": [],
    }


def cmd_plan_import(args):
    rows = [line.strip() for line in Path(args.csv).read_text().splitlines()[1:]
            if line.strip()]
    groups = _load(args.groups)
    _emit(rows_to_plan(rows, args.objective, args.slug, groups), args.out)
```

Register it:

```python
    p = sub.add_parser("plan-import", help="curated keyword CSV -> class-structured plan")
    p.add_argument("csv")
    p.add_argument("groups", help="JSON mapping class id -> list of CSV rows")
    p.add_argument("--objective", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_plan_import)
```

In `litterature_search_from_concept/litkb/paperclip.py`, change `search` so exact matching is opt-in:

```python
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
```

In `cmd_search`, pass the mode through: `r = search(phrase, args.sources, args.n, exact=plan.get("search_mode") != "semantic")`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project . pytest tests/test_plan_import.py -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Commit**

```bash
git add litterature_search_from_concept/litkb/cli.py litterature_search_from_concept/litkb/paperclip.py litterature_search_from_concept/tests/test_plan_import.py
git commit -m "feat(litkb): import curated keyword CSVs and search them semantically"
```

---

### Task 5: The screen pass

**Files:**
- Create: `litterature_search_from_concept/litkb/reader.py`
- Modify: `litterature_search_from_concept/litkb/paperclip.py`
- Test: `litterature_search_from_concept/tests/test_reader.py`

**Interfaces:**
- Consumes: set IDs from `cmd_search` output
- Produces: `reader.SCREEN_SCHEMA: dict`; `reader.parse_map_output(raw: str) -> list[dict]`; `paperclip.map_papers(set_id, query, schema, worker, n) -> list[dict]`

- [ ] **Step 1: Write the failing test**

`litterature_search_from_concept/tests/test_reader.py`:

```python
import json
from litkb import reader

RAW = json.dumps({"results": [
    {"doc_id": "PMC1", "output": {
        "mechanisms": [{"chain": "RF -> heating", "claim": "c",
                        "measurable_properties": ["fold_confidence"]}],
        "has_sequence": True, "sequence_location": "supplementary",
        "named_proteins": [{"name": "AsLOV2", "accession": "Q9C9W9"}]}},
    {"doc_id": "PMC2", "output": {
        "mechanisms": [], "has_sequence": False,
        "sequence_location": "none", "named_proteins": []}},
]})


def test_screen_schema_forbids_extra_keys():
    assert reader.SCREEN_SCHEMA["additionalProperties"] is False


def test_screen_schema_requires_the_sequence_flag():
    assert "has_sequence" in reader.SCREEN_SCHEMA["required"]


def test_parse_map_output_returns_one_record_per_paper():
    assert len(reader.parse_map_output(RAW)) == 2


def test_parse_map_output_keeps_doc_id_alongside_output():
    first = reader.parse_map_output(RAW)[0]
    assert first["doc_id"] == "PMC1"
    assert first["has_sequence"] is True


def test_flagged_papers_are_those_claiming_a_sequence():
    flagged = reader.flagged_for_dig(reader.parse_map_output(RAW))
    assert flagged == ["PMC1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project . pytest tests/test_reader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'litkb.reader'`

- [ ] **Step 3: Write the implementation**

`litterature_search_from_concept/litkb/reader.py`:

```python
"""Full-text reading via `paperclip map`.

Two tiers: `structured-extraction` sweeps every paper for mechanisms and flags
which ones claim sequences; `exhaustive-extraction` re-reads only the flagged
ones, where it can reach methods, tables and supplements.

Schemas are strict -- additionalProperties false, explicit required -- so a
paper that cannot produce valid output fails loudly instead of degrading.
"""

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


def parse_map_output(raw):
    """Flatten `paperclip map --output-schema` results into per-paper records."""
    import json
    data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    records = []
    for entry in data.get("results", []):
        out = entry.get("output") or {}
        records.append({"doc_id": entry.get("doc_id"), **out})
    return records


def flagged_for_dig(records):
    """Papers worth the expensive worker: those claiming a sequence exists."""
    return [r["doc_id"] for r in records if r.get("has_sequence")]
```

Add to `litterature_search_from_concept/litkb/paperclip.py`:

```python
def map_papers(set_id, query, schema, worker="structured-extraction", n=None,
               concurrency=32):
    """LLM read across a saved set. Server-side Claude -- no API key here."""
    import json as _json
    args = ["map", "--from", set_id, "--worker", worker,
            "--output-schema", _json.dumps(schema), "-j", str(concurrency)]
    if n:
        args += ["-n", str(n)]
    args.append(query)
    return _run(args)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project . pytest tests/test_reader.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Verify the assumed output shape against a real map run**

**`parse_map_output` is written against an assumed `{"results": [{"doc_id",
"output"}]}` shape. That shape has not been confirmed against a live run.**
Confirm it before building anything on top, using the smallest possible call —
one paper, so the LLM cost is negligible.

```bash
paperclip search -s pmc -n 1 -e "radical pair mechanism"     # note the s_ id
paperclip map --from <s_id> --worker structured-extraction -n 1 \
  --output-schema '{"type":"object","additionalProperties":false,"required":["has_sequence"],"properties":{"has_sequence":{"type":"boolean"}}}' \
  "Does this paper report an explicit amino-acid sequence?"
```

Inspect the JSON envelope: the key holding the per-paper list, the key holding
each paper's identifier, and the key holding the schema'd payload. If any
differs from `results` / `doc_id` / `output`, correct the three names in
`parse_map_output` and the fixture in `tests/test_reader.py`, then re-run the
test. Record the confirmed shape in a comment above `parse_map_output`.

- [ ] **Step 6: Commit**

```bash
git add litterature_search_from_concept/litkb/reader.py litterature_search_from_concept/litkb/paperclip.py litterature_search_from_concept/tests/test_reader.py
git commit -m "feat(litkb): screen pass over full text via paperclip map"
```

---

### Task 6: The dig pass and source confirmation

**Files:**
- Modify: `litterature_search_from_concept/litkb/reader.py`
- Test: `litterature_search_from_concept/tests/test_dig.py`

**Interfaces:**
- Consumes: `reader.flagged_for_dig`, `paperclip.grep_set`
- Produces: `reader.DIG_SCHEMA: dict`; `reader.confirm_in_source(artifact: dict, grep_fn: Callable[[str, list[str]], list[dict]]) -> bool`

- [ ] **Step 1: Write the failing test**

`litterature_search_from_concept/tests/test_dig.py`:

```python
from litkb import reader

REAL = {"value": "MKVAALLPQR", "provenance": {"doc_id": "PMC1", "set_id": "s_1"},
        "verbatim": True}
FABRICATED = {"value": "QQQWWWEEEE", "provenance": {"doc_id": "PMC1", "set_id": "s_1"},
              "verbatim": True}


def grep_fn(set_id, patterns):
    corpus = "the construct MKVAALLPQR was expressed"
    return [{"doc_id": "PMC1", "text": corpus}] if patterns[0] in corpus else []


def test_dig_schema_requires_the_verbatim_flag():
    item = reader.DIG_SCHEMA["properties"]["sequences"]["items"]
    assert "verbatim" in item["required"]


def test_sequence_present_in_source_is_confirmed():
    assert reader.confirm_in_source(REAL, grep_fn) is True


def test_sequence_absent_from_source_is_not_confirmed():
    assert reader.confirm_in_source(FABRICATED, grep_fn) is False


def test_non_verbatim_sequence_is_never_confirmed():
    claimed = dict(REAL, verbatim=False)
    assert reader.confirm_in_source(claimed, grep_fn) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project . pytest tests/test_dig.py -v`
Expected: FAIL with `AttributeError: module 'litkb.reader' has no attribute 'DIG_SCHEMA'`

- [ ] **Step 3: Write the implementation**

Append to `litterature_search_from_concept/litkb/reader.py`:

```python
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


def confirm_in_source(artifact, grep_fn):
    """Re-grep an extracted sequence against its own source document.

    An LLM asked for a sequence will produce a plausible one, and a fabricated
    sequence passes every alphabet and length check perfectly. This is the only
    check that distinguishes real from well-formed."""
    if not artifact.get("verbatim"):
        return False
    hits = grep_fn(artifact["provenance"]["set_id"], [artifact["value"]])
    return any(h["doc_id"] == artifact["provenance"]["doc_id"] for h in hits)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project . pytest tests/test_dig.py -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add litterature_search_from_concept/litkb/reader.py litterature_search_from_concept/tests/test_dig.py
git commit -m "feat(litkb): dig pass with verbatim discipline and source confirmation"
```

---

### Task 7: Wire screen, dig and bind into the CLI; delete the grep path

**Files:**
- Modify: `litterature_search_from_concept/litkb/cli.py`
- Modify: `litterature_search_from_concept/litkb/contracts.py`
- Delete: `litterature_search_from_concept/litkb/patterns.py`
- Test: `litterature_search_from_concept/tests/test_artifacts.py`

**Interfaces:**
- Consumes: `reader.SCREEN_SCHEMA`, `reader.DIG_SCHEMA`, `reader.confirm_in_source`, `proto.bind_artifact`
- Produces: `contracts.draft_artifact(index, sequence_record, doc_id, set_id) -> dict`; CLI commands `screen`, `dig`, `bind`

- [ ] **Step 1: Write the failing test**

`litterature_search_from_concept/tests/test_artifacts.py`:

```python
from litkb import contracts

RECORD = {"value": "MKVAAL", "molecule": "protein", "name": "AsLOV2",
          "region": [404, 546], "where": "Table S1", "verbatim": True}


def test_draft_artifact_has_a_stable_id():
    a = contracts.draft_artifact(7, RECORD, "PMC1", "s_1")
    assert a["id"] == "art_007"


def test_region_makes_it_a_subsequence():
    assert contracts.draft_artifact(1, RECORD, "PMC1", "s_1")["kind"] == "subsequence"


def test_absent_region_makes_it_a_sequence():
    record = dict(RECORD, region=None)
    assert contracts.draft_artifact(1, record, "PMC1", "s_1")["kind"] == "sequence"


def test_length_is_computed_from_the_value():
    assert contracts.draft_artifact(1, RECORD, "PMC1", "s_1")["length"] == 6


def test_confirmation_starts_false_until_checked():
    a = contracts.draft_artifact(1, RECORD, "PMC1", "s_1")
    assert a["provenance"]["confirmed_in_source"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project . pytest tests/test_artifacts.py -v`
Expected: FAIL with `AttributeError: module 'litkb.contracts' has no attribute 'draft_artifact'`

- [ ] **Step 3: Write the implementation**

Add to `litterature_search_from_concept/litkb/contracts.py`:

```python
def draft_artifact(index, record, doc_id, set_id):
    """One extracted sequence -> one ProtoArtifact, unbound and unconfirmed."""
    return {
        "id": f"art_{index:03d}",
        "kind": "subsequence" if record.get("region") else "sequence",
        "molecule": record["molecule"],
        "value": record["value"],
        "length": len(record["value"]),
        "parent": {"name": record.get("name"), "accession": None,
                   "region": record.get("region")},
        "evidence_refs": [],
        "provenance": {
            "doc_id": doc_id,
            "set_id": set_id,
            "where": record.get("where"),
            "verbatim": record.get("verbatim", False),
            "confirmed_in_source": False,
            "extractor": "exhaustive-extraction",
        },
        "proto_binding": {"status": "unbound", "tools": [],
                          "unverified": [], "rejected_by": []},
    }
```

Add the three commands to `litterature_search_from_concept/litkb/cli.py`:

```python
def cmd_screen(args):
    found = _load(args.search)
    records = []
    for cls in found["classes"]:
        for s in cls["sets"]:
            raw = map_papers(s["set_id"], reader.SCREEN_QUERY,
                             reader.SCREEN_SCHEMA, "structured-extraction", args.n)
            for rec in reader.parse_map_output(raw):
                rec["class_id"] = cls["id"]
                rec["set_id"] = s["set_id"]
                records.append(rec)
            print(f"  {cls['id']:<28} {s['set_id']} read", file=sys.stderr)
    flagged = reader.flagged_for_dig(records)
    print(f"  {len(flagged)}/{len(records)} papers claim a sequence", file=sys.stderr)
    _emit({"slug": found["slug"], "papers": records, "flagged": flagged}, args.out)


def cmd_dig(args):
    screened = _load(args.screen)
    flagged = set(screened["flagged"])
    by_set = {}
    for rec in screened["papers"]:
        if rec["doc_id"] in flagged:
            by_set.setdefault(rec["set_id"], []).append(rec["doc_id"])

    artifacts, n = [], 0
    for set_id, docs in by_set.items():
        raw = map_papers(set_id, reader.DIG_QUERY, reader.DIG_SCHEMA,
                         "exhaustive-extraction", args.n)
        for rec in reader.parse_map_output(raw):
            if rec["doc_id"] not in flagged:
                continue
            for seq in rec.get("sequences", []):
                n += 1
                artifacts.append(contracts.draft_artifact(n, seq, rec["doc_id"], set_id))
    print(f"  {len(artifacts)} candidate sequences", file=sys.stderr)
    _emit({"slug": screened["slug"], "artifacts": artifacts}, args.out)


def cmd_bind(args):
    dug = _load(args.artifacts)
    catalog = _load(args.registry)
    kept, rejections = [], []

    for art in dug["artifacts"]:
        art["provenance"]["confirmed_in_source"] = reader.confirm_in_source(
            {"value": art["value"], "verbatim": art["provenance"]["verbatim"],
             "provenance": art["provenance"]}, grep_set)
        if not art["provenance"]["confirmed_in_source"]:
            rejections.append({"kind": "not_confirmed_in_source", "id": art["id"],
                               "doc_id": art["provenance"]["doc_id"],
                               "reason": "sequence does not literally appear in its source document"})
            continue
        art["proto_binding"] = proto.bind_artifact(art, catalog)
        if art["proto_binding"]["status"] == "runnable":
            kept.append(art)
        else:
            rejections.append({"kind": f"proto_{art['proto_binding']['status']}",
                               "id": art["id"],
                               "reason": art["proto_binding"]["rejected_by"] or
                                         art["proto_binding"]["unverified"]})

    print(f"  {len(kept)} runnable, {len(rejections)} rejected", file=sys.stderr)
    _emit({"slug": dug["slug"], "artifacts": kept, "rejections": rejections}, args.out)
```

Add `from . import proto, reader` and `from .paperclip import map_papers` to the imports.

Register all three:

```python
    p = sub.add_parser("screen", help="cheap full-text sweep for mechanisms")
    p.add_argument("search")
    p.add_argument("-n", type=int, default=None)
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_screen)

    p = sub.add_parser("dig", help="deep read of papers that claim a sequence")
    p.add_argument("screen")
    p.add_argument("-n", type=int, default=None)
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_dig)

    p = sub.add_parser("bind", help="verify artifacts against the proto catalogue")
    p.add_argument("artifacts")
    p.add_argument("--registry", default="../registry/proto_catalog.json")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_bind)
```

Delete the `extract` subcommand registration and `cmd_extract`, and remove the `patterns` import.

- [ ] **Step 4: Delete the grep extraction path**

```bash
git rm litterature_search_from_concept/litkb/patterns.py
```

Verify nothing still imports it:

Run: `grep -rn "patterns" litterature_search_from_concept/litkb/`
Expected: no matches for `from . import patterns` or `patterns.STRUCTURAL`

- [ ] **Step 5: Run the full suite**

Run: `uv run --project . pytest -v`
Expected: PASS, all tests from Tasks 1-7

- [ ] **Step 6: Commit**

```bash
git add -A litterature_search_from_concept/
git commit -m "feat(litkb): screen/dig/bind commands; delete the grep extraction path"
```

---

### Task 8: Rebuild evidence from screen output, with testable_by

Task 7 deleted `extract`, so nothing now produces the `hits.json` that
`cmd_evidence` consumed. Mechanism evidence must come from `screen` instead —
and because `screen` already writes the claim, `label` is left supplying only
`support`, `claim_type`, `evidence_kind` and `confidence`.

**Files:**
- Modify: `litterature_search_from_concept/litkb/proto.py`
- Modify: `litterature_search_from_concept/litkb/contracts.py`
- Modify: `litterature_search_from_concept/litkb/cli.py`
- Test: `litterature_search_from_concept/tests/test_evidence_from_screen.py`

**Interfaces:**
- Consumes: `screen` output records, `proto.build_catalog` output
- Produces: `proto.resolve_properties(properties: list[str], catalog: dict) -> dict` with keys `tools` and `requires_new_evaluator`; `contracts.item_from_mechanism(index, class_id, mech, doc_id, citation) -> dict`

- [ ] **Step 1: Write the failing test**

`litterature_search_from_concept/tests/test_evidence_from_screen.py`:

```python
from litkb import contracts, proto

CATALOG = {"tools": [
    {"key": "esmfold-prediction", "measures": ["fold_confidence"], "status": "validated"},
    {"key": "esm2-score", "measures": ["sequence_likelihood"], "status": "needs_calibration"},
]}

MECH = {"chain": "RF -> nanoparticle heating -> TRPV1 gating",
        "claim": "Alternating fields heat nanoparticles enough to gate TRPV1",
        "measurable_properties": ["fold_confidence"]}


def test_property_resolves_to_the_measuring_tool():
    r = proto.resolve_properties(["fold_confidence"], CATALOG)
    assert r["tools"] == ["esmfold-prediction"]
    assert r["requires_new_evaluator"] is False


def test_unmeasurable_property_requires_a_new_evaluator():
    r = proto.resolve_properties(["spin_coherence_time"], CATALOG)
    assert r["tools"] == []
    assert r["requires_new_evaluator"] is True


def test_empty_property_list_requires_a_new_evaluator():
    assert proto.resolve_properties([], CATALOG)["requires_new_evaluator"] is True


def test_mechanism_becomes_an_evidence_item_with_the_claim_filled():
    item = contracts.item_from_mechanism(3, "thermal", MECH, "PMC1", {"doi": "d"})
    assert item["id"] == "ev_003"
    assert item["question_id"] == "thermal"
    assert item["claim"] == MECH["claim"]
    assert item["claim_type"] == "mechanism"


def test_support_is_still_left_for_the_labeller():
    item = contracts.item_from_mechanism(1, "thermal", MECH, "PMC1", {"doi": "d"})
    assert item["support"] is None


def test_chain_is_kept_as_provenance():
    item = contracts.item_from_mechanism(1, "thermal", MECH, "PMC1", {"doi": "d"})
    assert item["provenance"]["span"] == MECH["chain"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project . pytest tests/test_evidence_from_screen.py -v`
Expected: FAIL with `AttributeError: module 'litkb.proto' has no attribute 'resolve_properties'`

- [ ] **Step 3: Write the implementation**

Append to `litterature_search_from_concept/litkb/proto.py`:

```python
def resolve_properties(properties, catalog):
    """Map measurable properties onto tools that measure them.

    Framework §77: a class nothing can evaluate returns
    requires_new_evaluator, which is a legitimate output to hand back to the
    scientist rather than a discard."""
    wanted = set(properties or [])
    tools = sorted(t["key"] for t in catalog["tools"]
                   if wanted & set(t.get("measures") or []))
    return {"tools": tools, "requires_new_evaluator": not tools}
```

Append to `litterature_search_from_concept/litkb/contracts.py`:

```python
def item_from_mechanism(index, class_id, mech, doc_id, citation):
    """One mechanism read out of a paper -> one EvidenceItem.

    `claim` arrives filled because `screen` is itself an LLM call. `support`
    stays null: how well established a claim is cannot be read off a single
    paper's own wording."""
    return {
        "id": f"ev_{index:03d}",
        "question_id": class_id,
        "claim": mech["claim"],
        "claim_type": "mechanism",
        "quantitative": None,
        "support": None,
        "citation": citation,
        "evidence_kind": None,
        "extracted_by": "structured-extraction",
        "confidence": None,
        "testable_by": {"properties": mech.get("measurable_properties", []),
                        "tools": [], "requires_new_evaluator": True},
        "provenance": {
            "doc_id": doc_id,
            "section": None,
            "category": "mechanism",
            "span": mech["chain"],
            "url": f"https://paperclip.gxl.ai/citations/papers/{doc_id}",
        },
    }
```

Replace `cmd_evidence` in `litterature_search_from_concept/litkb/cli.py`:

```python
def cmd_evidence(args):
    screened = _load(args.screen)
    catalog = _load(args.registry) if Path(args.registry).exists() else {"tools": []}
    items, cache, n = [], {}, 0

    for rec in screened["papers"]:
        doc = rec["doc_id"]
        if doc not in cache:
            cache[doc] = contracts.citation_from_meta(meta(doc))
        for mech in rec.get("mechanisms", []):
            n += 1
            item = contracts.item_from_mechanism(n, rec["class_id"], mech, doc, cache[doc])
            item["testable_by"] = {
                "properties": mech.get("measurable_properties", []),
                **proto.resolve_properties(mech.get("measurable_properties", []), catalog),
            }
            items.append(item)

    need_eval = sum(1 for i in items if i["testable_by"]["requires_new_evaluator"])
    print(f"  {len(items)} items, {need_eval} need a new evaluator", file=sys.stderr)
    _emit({"slug": screened["slug"], "items": items,
           "unlabelled": len(contracts.validate_items(items))}, args.out)
```

Update its parser: replace the `hits` argument with `screen`, and add
`p.add_argument("--registry", default="../registry/proto_catalog.json")`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project . pytest tests/test_evidence_from_screen.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Run the full suite**

Run: `uv run --project . pytest -v`
Expected: PASS, all tests from Tasks 1-8

- [ ] **Step 6: Commit**

```bash
git add litterature_search_from_concept/litkb/ litterature_search_from_concept/tests/test_evidence_from_screen.py
git commit -m "feat(litkb): build evidence from screen output and resolve testable_by"
```

---

### Task 9: Report artifacts, refresh docs, run the RF instance

**Files:**
- Modify: `litterature_search_from_concept/litkb/report.py`
- Modify: `litterature_search_from_concept/readme.txt`
- Modify: `.claude/skills/litkb/SKILL.md`
- Test: `litterature_search_from_concept/tests/test_report.py`

**Interfaces:**
- Consumes: `bind` output
- Produces: `report.render(evidence, search=None, artifacts=None) -> str`

- [ ] **Step 1: Write the failing test**

`litterature_search_from_concept/tests/test_report.py`:

```python
from litkb import report

EVIDENCE = {"slug": "rfp", "items": []}
ARTIFACTS = {"artifacts": [
    {"id": "art_001", "kind": "sequence", "molecule": "protein",
     "value": "MKVAAL", "length": 6,
     "parent": {"name": "AsLOV2", "accession": None, "region": None},
     "provenance": {"doc_id": "PMC1", "where": "Table S1",
                    "verbatim": True, "confirmed_in_source": True},
     "proto_binding": {"status": "runnable",
                       "tools": [{"key": "esm2-score", "checks": {}}]}}],
    "rejections": [{"kind": "not_confirmed_in_source", "id": "art_002",
                    "reason": "sequence does not literally appear in its source document"}]}


def test_report_names_the_bound_tool():
    text = report.render(EVIDENCE, None, ARTIFACTS)
    assert "esm2-score" in text


def test_report_shows_the_sequence_and_its_source():
    text = report.render(EVIDENCE, None, ARTIFACTS)
    assert "MKVAAL" in text and "Table S1" in text


def test_report_surfaces_rejected_artifacts():
    text = report.render(EVIDENCE, None, ARTIFACTS)
    assert "not_confirmed_in_source" in text


def test_report_without_artifacts_still_renders():
    assert "knowledge base" in report.render(EVIDENCE)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project . pytest tests/test_report.py -v`
Expected: FAIL with `TypeError: render() takes from 1 to 2 positional arguments but 3 were given`

- [ ] **Step 3: Write the implementation**

Change the signature in `litterature_search_from_concept/litkb/report.py` to
`def render(evidence, search=None, artifacts=None):` and append before the
final `return`:

```python
    if artifacts:
        kept = artifacts.get("artifacts", [])
        out += ["", "", RULE, f"## PROTO-RUNNABLE ARTIFACTS  ({len(kept)})", RULE,
                "# Every artifact below is confirmed present in its source document",
                "# and accepted by at least one proto tool. Acceptance is a schema",
                "# check, not a run -- nothing here has been executed."]
        for a in kept:
            tools = ", ".join(t["key"] for t in a["proto_binding"]["tools"])
            parent = a["parent"].get("name") or "unnamed"
            out.append(f"[{a['id']}] {a['kind']} :: {parent} :: {a['length']} aa :: {tools}")
            out.append(f"    {a['value'][:120]}")
            out.append(f"    {a['provenance']['doc_id']} :: {a['provenance']['where']}")

        rejected = artifacts.get("rejections", [])
        if rejected:
            out += ["", f"### rejected artifacts ({len(rejected)})"]
            for r in rejected:
                out.append(f"- [{r['kind']}] {r.get('id')}: {r.get('reason')}")
```

Update `cmd_report` to pass it through, and register the flag:

```python
    p.add_argument("--artifacts")
```

with `text = report.render(ev, _load(args.search) if args.search else None, _load(args.artifacts) if args.artifacts else None)`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project . pytest tests/test_report.py -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Update the docs**

In `litterature_search_from_concept/readme.txt`, replace the PIPELINE block's
`extract` line with `screen -> dig -> bind`, add `proto-sync` and `plan-import`
to the command list, and replace the KNOWN LIMITS entry about
`registry/evaluators.json` with a note that `proto-sync` generates
`registry/proto_catalog.json`.

In `.claude/skills/litkb/SKILL.md`, replace the pipeline diagram and command
table with the new stages, and add a section stating that `bind` verifies
schema compatibility only, never runnability, and that a sequence not
confirmed in its source document is rejected regardless of constraint status.

- [ ] **Step 6: Write the class grouping for the curated keywords**

All 23 rows of `rf_protein_literature_keywords.csv` must appear, or
`plan-import` raises rather than silently dropping an expert query.

`litterature_search_from_concept/groups.json`:

```json
{
  "cryptochrome_rf": [
    "CraCRY ODMR",
    "cryptochrome RF radical pair FAD",
    "CraCRY C-terminal extension conformational change",
    "cryptochrome flavin redox conformational switching",
    "cryptochrome ODMR heating artifact",
    "RF cryptochrome null result",
    "radical pair conformational coupling",
    "cryptochrome magnetic effect reproducibility"
  ],
  "lov_radical_pair": [
    "MagLOV ODMR",
    "AsLOV2 C450A radical pair",
    "iLOV ODMR",
    "LOV2 Jalpha helix conformational change",
    "FMN radical pair allostery",
    "C450A LOV signaling loss",
    "LOV radical pair not involved signaling",
    "MagLOV ODMR artifact",
    "RF flavoprotein conformational change"
  ],
  "magnetothermal": [
    "radiofrequency thermolysin nanoparticle",
    "magnetothermal protein switch",
    "magnetic nanoparticle local heating protein",
    "nanoscale heating controversy magnetic nanoparticles",
    "specific absorption rate protein conjugate",
    "bulk heating control RF nanoparticle"
  ]
}
```

- [ ] **Step 7: Run the RF instance end to end**

Confirm `paperclip config` reports `Auth: ✓` first; if not, stop and ask the
user to run `paperclip login`.

```bash
uv run --project . python -m litkb plan-import rf_protein_literature_keywords.csv groups.json \
    --objective "$(cat context.txt)" --slug rfp -o rfp_plan.json
uv run --project . python -m litkb search   rfp_plan.json -n 20 -o rfp_search.json
uv run --project . python -m litkb screen   rfp_search.json -o rfp_screen.json
uv run --project . python -m litkb dig      rfp_screen.json -o rfp_dug.json
uv run --project . python -m litkb bind     rfp_dug.json -o rfp_artifacts.json
uv run --project . python -m litkb evidence rfp_screen.json -o rfp_evidence.json
uv run --project . python -m litkb report   rfp_evidence.json --search rfp_search.json \
    --artifacts rfp_artifacts.json -o knowledge_base_rfp.txt
```

Expected: `rfp_artifacts.json` contains at least one artifact with
`proto_binding.status == "runnable"` and `provenance.confirmed_in_source == true`.
Report the runnable count, the rejected count, and the reason breakdown.

- [ ] **Step 8: Commit**

```bash
git add -A litterature_search_from_concept/ .claude/skills/litkb/SKILL.md
git commit -m "feat(litkb): report proto-runnable artifacts; refresh docs"
```

---

## Verification

After Task 9, confirm each spec success criterion:

- [ ] `proto-sync` produced an entry for every tool `proto-tools list` reports — compare `n_tools` against `uv run --project ../proto proto-tools list --json | jq length`
- [ ] Every kept artifact names at least one tool and its passed checks
- [ ] Every rejected artifact names the check it failed
- [ ] No artifact in `artifacts[]` has `confirmed_in_source: false`
- [ ] An artifact whose only obstacle is an `unknown` check reports `unverified`, never `runnable`
- [ ] A mechanism class with no resolvable tool reports `requires_new_evaluator`
- [ ] `litkb/patterns.py` no longer exists and nothing imports it
