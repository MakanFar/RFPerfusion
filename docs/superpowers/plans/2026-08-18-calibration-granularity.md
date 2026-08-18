# Per-Metric Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move calibration from a per-tool flag to a per-(tool, metric) record carrying measured error, benchmark provenance and applicability domain, and propagate it to the two consumers that need it.

**Architecture:** Curation stays in `registry/calibration.json` and is overlaid onto the generated catalogue at the end of `proto-sync` — the pattern that shipped in `f758275`, extended one level down to `measures` rows. Tool-level `status` becomes derived from `primary` metrics so existing consumers keep working. Evidence gains an additive `rankable_by`; `formulation_agent007` gains a margin check that is inert until a metric is actually calibrated.

**Tech Stack:** Python 3.12, pytest, `uv run --project .`, pydantic (007 only).

**Spec:** `docs/superpowers/specs/2026-08-18-calibration-granularity-design.md`

## Global Constraints

- Run every litkb command from `litterature_search_from_concept/` as `uv run --project . python -m litkb <cmd>`; run 007 commands from `formulation_agent007/`.
- `paperclip` must be launched with a clean PATH (`proto.py:_clean_env`). Do not add subprocess calls that bypass it.
- Absence from `calibration.json` means `needs_calibration`. **Silence is never a promotion.**
- An unknown or malformed curated value raises. Never coerce, never default to `validated`.
- `unknown` never counts as `pass` (`proto.check`). Do not weaken this.
- Rejections ship: anything dropped must be recorded with the reason.
- The shipped `calibration.json` promotes nothing. No task may add a real promotion.
- Test counts: litkb is at **212** passing before Task 1. 007 is at **91**.

---

## Task 1: Per-metric calibration records

**Files:**
- Modify: `litterature_search_from_concept/litkb/proto.py:302-354` (`CALIBRATION_SCHEMA_VERSION`, `apply_calibration`)
- Modify: `registry/calibration.json`
- Test: `litterature_search_from_concept/tests/test_calibration.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `proto.CALIBRATION_SCHEMA_VERSION == 2`; `proto.apply_calibration(catalog, curation) -> (catalog, orphans)` where every `measures` row gains `calibration: {"status": str, ...}` and `orphans` is a sorted `list[str]` of `"tool"` or `"tool:metric"`.

- [ ] **Step 1: Write the failing tests**

Replace the body of `tests/test_calibration.py` below its module docstring with these. Keep the docstring; update `_curation` to the v2 shape.

```python
def _curation(tools):
    return {"schema_version": proto.CALIBRATION_SCHEMA_VERSION, "tools": tools}


def _validated(**over):
    rec = {"status": "validated",
           "measured_error": {"kind": "mae", "value": 0.06, "n": 312},
           "benchmark": {"name": "CAMEO 2025-H1", "held_out": True}}
    rec.update(over)
    return rec


def test_curated_metric_carries_its_calibration_onto_the_measures_row():
    out, _ = proto.apply_calibration(_catalog(), _curation(
        {"esmfold-prediction": {"metrics": {"avg_plddt": _validated()}}}))

    row = [m for t in out["tools"] if t["key"] == "esmfold-prediction"
           for m in t["measures"] if m["metric"] == "avg_plddt"][0]
    assert row["calibration"]["status"] == "validated"
    assert row["calibration"]["measured_error"]["value"] == 0.06


def test_uncurated_metric_defaults_to_needs_calibration():
    """Silence is never a promotion, at metric resolution too."""
    out, _ = proto.apply_calibration(_catalog(), _curation(
        {"esmfold-prediction": {"metrics": {"avg_plddt": _validated()}}}))

    row = [m for t in out["tools"] if t["key"] == "esmfold-prediction"
           for m in t["measures"] if m["metric"] == "ptm"][0]
    assert row["calibration"] == {"status": "needs_calibration"}


def test_validated_without_measured_error_is_rejected():
    """A promotion with no number is exactly what framework section 6 exists
    to prevent, so a bare flag must not be accepted."""
    rec = _validated()
    del rec["measured_error"]
    with pytest.raises(ValueError, match="measured_error"):
        proto.apply_calibration(_catalog(), _curation(
            {"esmfold-prediction": {"metrics": {"avg_plddt": rec}}}))


def test_validated_without_benchmark_is_rejected():
    rec = _validated()
    del rec["benchmark"]
    with pytest.raises(ValueError, match="benchmark"):
        proto.apply_calibration(_catalog(), _curation(
            {"esmfold-prediction": {"metrics": {"avg_plddt": rec}}}))


def test_unknown_status_value_is_rejected_loudly():
    with pytest.raises(ValueError, match="validatd"):
        proto.apply_calibration(_catalog(), _curation(
            {"esmfold-prediction": {"metrics": {"avg_plddt": {"status": "validatd"}}}}))


def test_orphan_tool_is_reported():
    _, orphans = proto.apply_calibration(_catalog(), _curation(
        {"tool-that-went-away": {"metrics": {"avg_plddt": _validated()}}}))
    assert orphans == ["tool-that-went-away"]


def test_orphan_metric_on_a_real_tool_is_reported_as_tool_colon_metric():
    """A tool that stopped emitting a metric orphans the calibration for it.
    Dropping that silently would let calibration effort evaporate."""
    _, orphans = proto.apply_calibration(_catalog(), _curation(
        {"esmfold-prediction": {"metrics": {"metric_that_went_away": _validated()}}}))
    assert orphans == ["esmfold-prediction:metric_that_went_away"]


def test_v1_curation_is_refused_with_a_pointer():
    """v1 keyed status on the tool, which has no metric to attach to. The
    shipped file promotes nothing, so nothing is lost by refusing it."""
    v1 = {"schema_version": 1, "tools": {"esmfold-prediction": {"status": "validated"}}}
    with pytest.raises(ValueError, match="schema_version"):
        proto.apply_calibration(_catalog(), v1)


def test_no_curation_leaves_every_row_uncalibrated():
    out, orphans = proto.apply_calibration(_catalog(), _curation({}))

    rows = [m for t in out["tools"] for m in t["measures"]]
    assert all(m["calibration"] == {"status": "needs_calibration"} for m in rows)
    assert orphans == []


def test_committed_curation_file_parses_and_matches_the_real_catalogue():
    catalog = json.load(open("../registry/proto_catalog.json"))
    curation = json.load(open("../registry/calibration.json"))

    _, orphans = proto.apply_calibration(catalog, curation)

    assert orphans == [], f"curated keys no longer in the catalogue: {orphans}"
```

Also update `_catalog()` so its tools carry `measures` rows with metric names the tests use:

```python
def _catalog():
    return {
        "schema_version": proto.CATALOG_SCHEMA_VERSION,
        "tools": [
            {"key": "esmfold-prediction", "status": "needs_calibration",
             "measures": [{"metric": "avg_plddt", "primary": True},
                          {"metric": "ptm", "primary": False}]},
            {"key": "esm2-embedding", "status": "needs_calibration",
             "measures": []},
        ],
        "n_tools": 2,
        "parse_failures": [],
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_calibration.py -q`
Expected: FAIL. The v2 tests fail because `apply_calibration` writes no `calibration` key on rows and `CALIBRATION_SCHEMA_VERSION` is still `1`.

- [ ] **Step 3: Write the implementation**

In `litkb/proto.py`, replace `CALIBRATION_SCHEMA_VERSION = 1` and the body of `apply_calibration` with:

```python
CALIBRATION_SCHEMA_VERSION = 2
CALIBRATION_STATUSES = ("needs_calibration", "validated")
UNCALIBRATED = {"status": "needs_calibration"}


def _check_metric_record(tool_key, metric, rec):
    """A curated record must be complete before it can promote anything."""
    status = (rec or {}).get("status")
    if status not in CALIBRATION_STATUSES:
        raise ValueError(
            f"calibration: {tool_key}:{metric} has status {status!r}, expected "
            f"one of {CALIBRATION_STATUSES}"
        )
    if status != "validated":
        return
    for field in ("measured_error", "benchmark"):
        if not rec.get(field):
            # Framework section 6 promotes on MEASURED reliability. A bare
            # flag with no number is the claim it exists to forbid.
            raise ValueError(
                f"calibration: {tool_key}:{metric} is validated without "
                f"{field}; a promotion needs the measurement behind it"
            )


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
        tools.append({**t, "measures": [
            {**m, "calibration": metrics.get(m["metric"], dict(UNCALIBRATED))}
            for m in t.get("measures", [])
        ]})
    return {**catalog, "tools": tools}, sorted(orphans)
```

- [ ] **Step 4: Migrate the committed curation file**

Rewrite `registry/calibration.json` to v2. It still promotes nothing.

```bash
cd /Users/skynet/test/RFPerfusion
python3 - <<'PY'
import json, pathlib
p = pathlib.Path("registry/calibration.json")
d = json.loads(p.read_text())
d["schema_version"] = 2
d["note"] = ("Hand-curated calibration, kept OUT of proto_catalog.json because "
             "that file is regenerated from proto-tools on every `litkb "
             "proto-sync` and everything in it is derived. Keyed by (tool, "
             "metric): one model emits several metrics and may be "
             "characterised for some and not others. Overlaid at build time "
             "by proto.apply_calibration. Tool-level `status` is DERIVED from "
             "these, never curated.")
d["promotion_rule"] = ("A metric becomes \"validated\" only on measured "
                       "reliability against a held-out benchmark, per "
                       "docs/PRD-framework.md section 6, and the record must "
                       "carry `measured_error` and `benchmark` or it is "
                       "refused. Absence means needs_calibration; silence is "
                       "never a promotion.")
d["tools"] = {}
d["example"] = {
    "esmfold-prediction": {"metrics": {"avg_plddt": {
        "status": "validated",
        "measured_error": {"kind": "mae", "value": 0.06, "n": 312},
        "benchmark": {"name": "CAMEO 2025-H1", "doi": "10.0000/example",
                      "held_out": True},
        "applicability_domain": {"molecules": ["protein"], "length": [30, 800],
                                 "notes": "monomers only"},
        "curated_on": "2026-08-18"}}}
}
p.write_text(json.dumps(d, indent=2) + "\n")
PY
```

Note: `example` is documentation, not curation. `apply_calibration` reads only `tools`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_calibration.py -q`
Expected: PASS, 10 tests.

- [ ] **Step 6: Run the full suite**

Run: `cd litterature_search_from_concept && uv run --project . pytest -q`
Expected: some failures in `tests/test_proto.py` / `tests/test_catalog_build.py` are acceptable ONLY if they assert on the old tool-level `status`; Task 2 fixes those. Record which fail.

- [ ] **Step 7: Commit**

```bash
git add litterature_search_from_concept/litkb/proto.py \
        litterature_search_from_concept/tests/test_calibration.py \
        registry/calibration.json
git commit -m "feat(registry): key calibration on (tool, metric)

The curated unit was a tool; the thing with an error bar is a metric. One
model emits several and may be characterised for some and not others, so
the only expressible answers were trust-all or trust-none.

A validated record must now carry measured_error and benchmark -- framework
section 6 promotes on measurement, and a bare flag is the claim it forbids.
Orphaned metrics are reported as tool:metric alongside orphaned tools."
```

---

## Task 2: Derive tool status from primary metrics

**Files:**
- Modify: `litterature_search_from_concept/litkb/proto.py` (add `derive_status`, call it from `apply_calibration`)
- Modify: `litterature_search_from_concept/tests/test_proto.py:66`, `litterature_search_from_concept/tests/test_catalog_build.py:61-63,103`
- Test: `litterature_search_from_concept/tests/test_calibration.py`

**Interfaces:**
- Consumes: `measures[].calibration` from Task 1.
- Produces: `proto.derive_status(measures) -> str`, called inside `apply_calibration` so every returned tool's `status` is derived.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_calibration.py`:

```python
def test_tool_is_validated_when_its_primary_metric_is():
    out, _ = proto.apply_calibration(_catalog(), _curation(
        {"esmfold-prediction": {"metrics": {"avg_plddt": _validated()}}}))

    by_key = {t["key"]: t for t in out["tools"]}
    assert by_key["esmfold-prediction"]["status"] == "validated"


def test_validating_a_non_primary_metric_does_not_validate_the_tool():
    """`primary` is the catalogue's own statement of what the tool is meant to
    be judged on. Calibrating a secondary readout does not license ranking."""
    out, _ = proto.apply_calibration(_catalog(), _curation(
        {"esmfold-prediction": {"metrics": {"ptm": _validated()}}}))

    by_key = {t["key"]: t for t in out["tools"]}
    assert by_key["esmfold-prediction"]["status"] == "needs_calibration"


def test_tool_with_no_primary_metric_can_never_be_validated():
    """98 of 140 catalogued tools are in this position: 92 measure nothing and
    6 emit metrics without declaring which one they are for. There is nothing
    to judge them on, so they never roll up."""
    catalog = _catalog()
    catalog["tools"].append(
        {"key": "no-primary-tool", "status": "needs_calibration",
         "measures": [{"metric": "some_score", "primary": False}]})

    out, _ = proto.apply_calibration(catalog, _curation(
        {"no-primary-tool": {"metrics": {"some_score": _validated()}}}))

    by_key = {t["key"]: t for t in out["tools"]}
    assert by_key["no-primary-tool"]["status"] == "needs_calibration"


def test_every_tool_in_the_committed_catalogue_is_still_uncalibrated():
    """The shipped curation promotes nothing, so the derived status must match
    what proto-sync wrote before this change."""
    catalog = json.load(open("../registry/proto_catalog.json"))
    curation = json.load(open("../registry/calibration.json"))

    out, _ = proto.apply_calibration(catalog, curation)

    assert {t["status"] for t in out["tools"]} == {"needs_calibration"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_calibration.py -q`
Expected: FAIL on `test_tool_is_validated_when_its_primary_metric_is` — status is still the literal written by `build_catalog`.

- [ ] **Step 3: Write the implementation**

Add to `litkb/proto.py` above `apply_calibration`:

```python
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
```

Then in `apply_calibration`, change the tool-building loop to derive status:

```python
    tools = []
    for t in catalog["tools"]:
        metrics = ((curated.get(t["key"]) or {}).get("metrics") or {})
        measures = [
            {**m, "calibration": metrics.get(m["metric"], dict(UNCALIBRATED))}
            for m in t.get("measures", [])
        ]
        tools.append({**t, "measures": measures,
                      "status": derive_status(measures)})
    return {**catalog, "tools": tools}, sorted(orphans)
```

- [ ] **Step 4: Update the tests that assert the generator's literal**

`build_catalog` still writes `needs_calibration` and that is still correct — it has no calibration input. Confirm these tests still pass unchanged and do NOT edit them unless they fail:

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_proto.py tests/test_catalog_build.py -q`
Expected: PASS unchanged. They assert on `build_catalog` output, which this task does not touch.

- [ ] **Step 5: Run the full suite**

Run: `cd litterature_search_from_concept && uv run --project . pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add litterature_search_from_concept/litkb/proto.py \
        litterature_search_from_concept/tests/test_calibration.py
git commit -m "feat(registry): derive tool status from its primary metrics

Tool status is no longer curated. A tool is validated iff it declares a
primary metric and every primary is validated, so resolve_coverage keeps
working while the real gate moves down to the metric.

A tool with no primary has nothing to be judged on and never rolls up --
98 of 140: the 92 that measure nothing plus 6 that emit metrics without
declaring which one the tool is for."
```

---

## Task 3: Catalogue schema 3 and regeneration

**Files:**
- Modify: `litterature_search_from_concept/litkb/proto.py:223` (`CATALOG_SCHEMA_VERSION`)
- Modify: `registry/proto_catalog.json` (regenerated)
- Test: `litterature_search_from_concept/tests/test_registry.py`

**Interfaces:**
- Consumes: `apply_calibration` from Tasks 1-2.
- Produces: `proto.CATALOG_SCHEMA_VERSION == 3`; every `measures` row in the committed catalogue carries `calibration`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_registry.py`:

```python
def test_committed_catalogue_is_schema_3_with_calibration_on_every_row():
    """The overlay is what makes calibration visible to readers of the
    catalogue. A row without it would read as "no opinion" rather than
    "not calibrated"."""
    import json
    from litkb import proto

    catalog = json.load(open("../registry/proto_catalog.json"))
    assert catalog["schema_version"] == proto.CATALOG_SCHEMA_VERSION == 3

    rows = [m for t in catalog["tools"] for m in t.get("measures", [])]
    assert rows, "catalogue has no metric rows at all"
    assert all("calibration" in m for m in rows)
    assert {m["calibration"]["status"] for m in rows} == {"needs_calibration"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_registry.py -q`
Expected: FAIL — `schema_version` is 2 and rows have no `calibration`.

- [ ] **Step 3: Bump the constant**

In `litkb/proto.py`, change:

```python
CATALOG_SCHEMA_VERSION = 3
```

Update `load_catalog`'s docstring to name the v2->v3 reason:

```python
def load_catalog(path):
    """Read a registry, refusing anything but the current schema version.

    v1 -> v2 added derived `measures`. v2 -> v3 added per-metric
    `calibration` on each row. Coercing an older file would silently drop the
    calibration overlay and read every metric as having no opinion rather
    than as uncalibrated -- the fail-open behaviour `check()` refuses.
    """
```

- [ ] **Step 4: Regenerate the catalogue**

This needs the proto venv and takes roughly 9.5 minutes.

```bash
cd /Users/skynet/test/RFPerfusion/litterature_search_from_concept
uv run --project . python -m litkb proto-sync \
  -o ../registry/proto_catalog.json \
  --snapshot ../registry/proto_metrics.json \
  --calibration ../registry/calibration.json
```

Expected stderr: `140 tools from proto-tools`, `0/140 validated`, no orphan warnings.

If proto-tools is unavailable, do NOT hand-edit the catalogue. Stop and report.

- [ ] **Step 5: Verify the regenerated file**

```bash
cd /Users/skynet/test/RFPerfusion
python3 -c "
import json; d=json.load(open('registry/proto_catalog.json'))
rows=[m for t in d['tools'] for m in t.get('measures',[])]
print('schema_version', d['schema_version'], '| tools', d['n_tools'],
      '| rows', len(rows), '| parse_failures', len(d['parse_failures']))
print('all rows have calibration:', all('calibration' in m for m in rows))
print('statuses:', {t['status'] for t in d['tools']})
"
```
Expected: `schema_version 3 | tools 140 | rows 311 | parse_failures 0`, `True`, `{'needs_calibration'}`.

- [ ] **Step 6: Run the full suite**

Run: `cd litterature_search_from_concept && uv run --project . pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add litterature_search_from_concept/litkb/proto.py \
        litterature_search_from_concept/tests/test_registry.py \
        registry/proto_catalog.json registry/proto_metrics.json
git commit -m "feat(registry): catalogue schema 3 carries per-metric calibration

Every measures row now carries a calibration block, overlaid from
calibration.json at the end of proto-sync. A row without one would read as
'no opinion' rather than 'not calibrated', which is the distinction the
whole change exists to make.

Regenerated: 140 tools, 311 metric rows, 0 parse failures, 0 validated."
```

---

## Task 4: `rankable_by` on evidence

**Files:**
- Modify: `litterature_search_from_concept/litkb/proto.py:449-469` (`resolve_properties`)
- Modify: `litterature_search_from_concept/litkb/contracts.py:281-320` (`apply_labels`)
- Modify: `litterature_search_from_concept/litkb/cli.py:496` (evidence `schema_version`)
- Test: `litterature_search_from_concept/tests/test_resolve_properties.py`, `litterature_search_from_concept/tests/test_label_vocabulary.py`

**Interfaces:**
- Consumes: `measures[].calibration` from Tasks 1-3.
- Produces: `resolve_properties(...)` returns `{"tools": [...], "rankable_by": [...], "requires_new_evaluator": ...}`; drafted evidence carries `testable_by.rankable_by`; evidence `schema_version` is 3.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_resolve_properties.py`:

```python
def _cat(cal_status):
    return {"schema_version": 3, "tools": [
        {"key": "esmfold-prediction", "status": "needs_calibration",
         "measures": [{"metric": "avg_plddt", "primary": True,
                       "calibration": {"status": cal_status}}]},
    ]}


_VOCAB = {"version": 1, "terms": [
    {"id": "fold_confidence", "definition": "d", "metrics": ["avg_plddt"]}]}


def test_uncalibrated_tool_can_measure_but_not_rank():
    """Framework section 6: an uncalibrated evaluator may run, and may not
    rank. Before this field there was no way to say the second half, so a
    consumer reading requires_new_evaluator=false saw 'covered'."""
    from litkb import proto

    out = proto.resolve_properties(["fold_confidence"],
                                   _cat("needs_calibration"), _VOCAB)

    assert out["tools"] == ["esmfold-prediction"]
    assert out["rankable_by"] == []
    assert out["requires_new_evaluator"] is False


def test_validated_metric_makes_its_tool_rankable():
    from litkb import proto

    out = proto.resolve_properties(["fold_confidence"], _cat("validated"), _VOCAB)

    assert out["rankable_by"] == ["esmfold-prediction"]


def test_unassessed_item_has_no_rankable_by():
    from litkb import proto

    out = proto.resolve_properties([], _cat("validated"), _VOCAB)

    assert out["rankable_by"] == []
    assert out["requires_new_evaluator"] == proto.UNASSESSED
```

Append to `tests/test_label_vocabulary.py`:

```python
def test_empty_vocabulary_assignment_still_sets_rankable_by():
    """An empty assignment is a real judgement -- 'nothing measures this' --
    and must produce a complete testable_by, not a missing key."""
    from litkb import contracts

    items = [{"id": "ev_001", "testable_by": {"properties": [], "vocabulary": [],
                                              "tools": [], "rankable_by": [],
                                              "requires_new_evaluator": "unassessed"}}]
    errors = contracts.apply_labels(
        items, [{"id": "ev_001", "vocabulary": []}],
        catalog={"schema_version": 3, "tools": []}, vocab={"version": 1, "terms": []})

    assert items[0]["testable_by"]["rankable_by"] == []
    assert items[0]["testable_by"]["requires_new_evaluator"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_resolve_properties.py tests/test_label_vocabulary.py -q`
Expected: FAIL with `KeyError: 'rankable_by'`.

- [ ] **Step 3: Write the implementation**

Replace `resolve_properties` in `litkb/proto.py`:

```python
def resolve_properties(term_ids, catalog, vocab):
    """Map assigned vocabulary terms onto tools that measure them.

    Three-valued on purpose. The old version intersected free-text properties
    against an all-empty `measures` column and so returned `True`
    unconditionally -- an answer that happened to be right for the RF corpus
    and could not have been wrong for any corpus.

    `tools` answers "what can MEASURE this"; `rankable_by` answers "what may
    RANK on it", which framework section 6 restricts to calibrated
    evaluators. They are separate fields because they are separate questions:
    folding them into one would have silently changed the meaning of every
    committed `requires_new_evaluator: false`.
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
```

In `litkb/contracts.py`, update the empty-terms branch and the assignment block:

```python
                resolved = proto.resolve_properties(terms, catalog, vocab) if terms \
                    else {"tools": [], "rankable_by": [],
                          "requires_new_evaluator": True}
            except UnknownTerm as exc:
                errors.append(f"{iid}: {exc}")
                continue
            item["testable_by"]["vocabulary"] = list(terms)
            item["testable_by"]["tools"] = resolved["tools"]
            item["testable_by"]["rankable_by"] = resolved["rankable_by"]
            item["testable_by"]["requires_new_evaluator"] = \
                resolved["requires_new_evaluator"]
```

In `litkb/contracts.py`, in `item_from_mechanism` (line 252-254), replace:

```python
        "testable_by": {"properties": mech.get("measurable_properties", []),
                        "vocabulary": [], "tools": [],
                        "requires_new_evaluator": "unassessed"},
```

with:

```python
        "testable_by": {"properties": mech.get("measurable_properties", []),
                        "vocabulary": [], "tools": [], "rankable_by": [],
                        "requires_new_evaluator": "unassessed"},
```

In `litkb/cli.py:496`, bump the evidence envelope:

```python
    _emit({"schema_version": 3, "slug": screened["slug"], "items": items,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd litterature_search_from_concept && uv run --project . pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add litterature_search_from_concept/litkb/proto.py \
        litterature_search_from_concept/litkb/contracts.py \
        litterature_search_from_concept/litkb/cli.py \
        litterature_search_from_concept/tests/
git commit -m "feat(litkb): separate what can measure from what may rank

requires_new_evaluator: false became reachable in 31a0a0a, and immediately
read as 'covered': ev_001 listed 15 tools, every one uncalibrated, with
nothing in the record saying section 6 forbids all 15 from ranking.

rankable_by is additive, so tools keeps meaning 'can measure' and no
committed false changes meaning. Empty for every item in the repo today."
```

---

## Task 5: 007 reads calibration and enforces the margin rule

**Files:**
- Modify: `litterature_search_from_concept/litkb/cli.py` (`_snapshot_from_catalog`, schema 4)
- Modify: `formulation_agent007/src/formulation_agent007/catalog.py:37-60`
- Modify: `formulation_agent007/src/formulation_agent007/validate.py:254-300`
- Modify: `formulation_agent007/src/formulation_agent007/emit.py:435-445`
- Test: `litterature_search_from_concept/tests/test_cli_snapshot.py`, `formulation_agent007/tests/test_validate.py`

**Interfaces:**
- Consumes: `measures[].calibration` from Task 3.
- Produces: snapshot `schema_version: 4` with `metrics[name]["calibration"] = {tool_key: {"status", "measured_error"}}`; `catalog.METRIC_CALIBRATION`; margin checks in `validate_proto`; uncalibrated labelling in `emit`.

- [ ] **Step 1: Write the failing snapshot test**

Append to `litterature_search_from_concept/tests/test_cli_snapshot.py`:

```python
def test_snapshot_keys_calibration_by_tool_not_by_metric_name():
    """One metric can be validated for one emitting tool and not another, so
    a metric-global flag would be a lie for whichever tool disagrees."""
    catalog = {"tools": [
        {"key": "a-tool", "category": "structure_prediction", "measures": [
            {"metric": "iptm", "better": "higher", "primary": True,
             "calibration": {"status": "validated",
                             "measured_error": {"kind": "mae", "value": 0.05}}}]},
        {"key": "b-tool", "category": "structure_prediction", "measures": [
            {"metric": "iptm", "better": "higher", "primary": False,
             "calibration": {"status": "needs_calibration"}}]},
    ]}

    snap = _snapshot_from_catalog(catalog)

    assert snap["schema_version"] == 4
    cal = snap["metrics"]["iptm"]["calibration"]
    assert cal["a-tool"]["status"] == "validated"
    assert cal["a-tool"]["measured_error"]["value"] == 0.05
    assert cal["b-tool"]["status"] == "needs_calibration"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd litterature_search_from_concept && uv run --project . pytest tests/test_cli_snapshot.py -q`
Expected: FAIL — `schema_version` is 3, no `calibration` key.

- [ ] **Step 3: Implement the snapshot change**

In `litkb/cli.py`, inside `_snapshot_from_catalog`'s metric loop, add calibration capture:

```python
            entry["calibration"][t["key"]] = m.get(
                "calibration", {"status": "needs_calibration"})
```

Add `"calibration": {}` to the `setdefault` default dict, and change the returned `schema_version` to `4`. Extend the `note` string with:

```
"`calibration` is keyed by tool because one metric can be validated for one emitting tool and not another."
```

- [ ] **Step 4: Regenerate the snapshot**

```bash
cd /Users/skynet/test/RFPerfusion/litterature_search_from_concept
uv run --project . python -m litkb proto-sync \
  -o ../registry/proto_catalog.json \
  --snapshot ../registry/proto_metrics.json \
  --calibration ../registry/calibration.json
```

- [ ] **Step 5: Write the failing validator tests**

Append these to the existing `TestProtoCascade` class in
`formulation_agent007/tests/test_validate.py`. That file drives everything off
the shared `proto` fixture and mutates gates in place — match it rather than
building a brief by hand. Add `METRIC_CALIBRATION` to the imports from
`formulation_agent007.catalog`.

Each assertion looks for the margin message specifically, not `== []`, because
mutating a gate can legitimately trip neighbouring checks too.

```python
    _CAL = {"esmfold-prediction": {
        "status": "validated",
        "measured_error": {"kind": "mae", "value": 0.06}}}

    def test_uncalibrated_metric_raises_no_margin_problem(self, proto):
        """validate_proto's output drives an LLM repair attempt
        (agent.py:120), not a warning log. With nothing calibrated, flagging
        uncalibrated gates would fire on every gate of every run and drive a
        repair that cannot succeed. The label belongs in the runbook."""
        assert not any("measured error" in p for p in validate_proto(proto))

    def test_between_window_narrower_than_twice_the_error_is_rejected(
            self, proto, monkeypatch):
        monkeypatch.setitem(METRIC_CALIBRATION, "avg_plddt", self._CAL)
        gate = proto.gates[0]
        gate.metric, gate.tool_keys = "avg_plddt", ["esmfold-prediction"]
        gate.operator = "between"
        gate.threshold, gate.threshold_upper = 0.80, 0.85

        assert any("measured error" in p for p in validate_proto(proto))

    def test_threshold_quoted_finer_than_the_measured_error_is_rejected(
            self, proto, monkeypatch):
        monkeypatch.setitem(METRIC_CALIBRATION, "avg_plddt", self._CAL)
        gate = proto.gates[0]
        gate.metric, gate.tool_keys = "avg_plddt", ["esmfold-prediction"]
        gate.operator, gate.threshold = ">=", 0.852
        gate.threshold_upper = None

        assert any("measured error" in p for p in validate_proto(proto))

    def test_threshold_coarser_than_the_measured_error_passes(
            self, proto, monkeypatch):
        monkeypatch.setitem(METRIC_CALIBRATION, "avg_plddt", self._CAL)
        gate = proto.gates[0]
        gate.metric, gate.tool_keys = "avg_plddt", ["esmfold-prediction"]
        gate.operator, gate.threshold = ">=", 0.8
        gate.threshold_upper = None

        assert not any("measured error" in p for p in validate_proto(proto))

    def test_calibration_for_a_tool_the_gate_does_not_name_is_ignored(
            self, proto, monkeypatch):
        """The gate names the tools that will actually run. A metric
        validated on some other tool says nothing about this gate."""
        monkeypatch.setitem(METRIC_CALIBRATION, "avg_plddt", self._CAL)
        gate = proto.gates[0]
        gate.metric, gate.tool_keys = "avg_plddt", ["boltz2-prediction"]
        gate.operator, gate.threshold = ">=", 0.852
        gate.threshold_upper = None

        assert not any("measured error" in p for p in validate_proto(proto))
```

- [ ] **Step 6: Run them to verify they fail**

Run: `cd formulation_agent007 && uv run --project . pytest tests/test_validate.py -q`
Expected: FAIL with `ImportError` on `METRIC_CALIBRATION`.

- [ ] **Step 7: Implement the catalogue constant and the margin check**

In `formulation_agent007/src/formulation_agent007/catalog.py`, after `METRIC_DIRECTION`:

```python
# Keyed metric -> tool key -> {"status", "measured_error"}. Keyed by tool
# because one metric can be validated for one emitting tool and not another.
METRIC_CALIBRATION: dict[str, dict[str, dict]] = {
    name: spec.get("calibration", {})
    for name, spec in _SNAPSHOT["metrics"].items()
}
```

In `validate.py`, import `METRIC_CALIBRATION` and add after the direction check inside the `for gate in gates:` loop:

```python
        # Framework section 6: no claimed design margin finer than the
        # evaluator's measured error. Fires only for metrics validated for the
        # tools THIS gate names, so it is inert until calibration lands.
        errors_for_gate = [
            c["measured_error"]["value"]
            for key, c in METRIC_CALIBRATION.get(gate.metric, {}).items()
            if key in gate.tool_keys and c.get("status") == "validated"
            and c.get("measured_error")
        ]
        if errors_for_gate:
            err = max(errors_for_gate)
            if gate.operator == "between" and gate.threshold_upper is not None:
                window = gate.threshold_upper - gate.threshold
                if window < 2 * err:
                    problems.append(
                        f"gate {gate.order} keeps a window of {window:g} on "
                        f"{gate.metric!r}, but its measured error is {err:g}; "
                        f"the window cannot be resolved"
                    )
            else:
                step = _decimal_step(gate.threshold)
                if step < err:
                    problems.append(
                        f"gate {gate.order} thresholds {gate.metric!r} at "
                        f"{gate.threshold:g}, quoted to {step:g}, but its "
                        f"measured error is {err:g}; the claimed margin is "
                        f"finer than the evaluator can resolve"
                    )
```

Add the helper at module level in `validate.py`:

```python
def _decimal_step(value: float) -> float:
    """The resolution a number is quoted to: 0.85 -> 0.01, 0.852 -> 0.001.

    Quoting more digits than the evaluator's error supports is a claim about
    precision the measurement does not carry.
    """
    text = f"{value!r}"
    if "." not in text or "e" in text or "E" in text:
        return 1.0
    return 10.0 ** -len(text.split(".")[1])
```

- [ ] **Step 8: Run the validator tests**

Run: `cd formulation_agent007 && uv run --project . pytest tests/test_validate.py -q`
Expected: PASS.

- [ ] **Step 9: Label uncalibrated gates in the runbook**

In `emit.py`, in the block that appends to `lines` around line 437, after the existing two disclaimer bullets add:

```python
    uncal = [g for g in p.ordered()
             if not any(c.get("status") == "validated"
                        for key, c in METRIC_CALIBRATION.get(g.metric, {}).items()
                        if key in g.tool_keys)]
    if uncal:
        lines.append(
            "- Gates "
            + ", ".join(str(g.order) for g in uncal)
            + " threshold metrics with no measured error on the tools named. "
              "Framework section 6 permits running them and forbids ranking on "
              "them; treat their ordering as provisional."
        )
```

Import `METRIC_CALIBRATION` in `emit.py`.

- [ ] **Step 10: Run both suites**

Run: `cd formulation_agent007 && uv run --project . pytest -q`
Expected: PASS.
Run: `cd litterature_search_from_concept && uv run --project . pytest -q`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add litterature_search_from_concept/litkb/cli.py \
        litterature_search_from_concept/tests/test_cli_snapshot.py \
        registry/proto_metrics.json registry/proto_catalog.json \
        formulation_agent007/src/formulation_agent007/ \
        formulation_agent007/tests/test_validate.py
git commit -m "feat(007): enforce section 6's margin rule

The snapshot now carries calibration keyed by tool, because one metric can
be validated for one emitting tool and not another.

validate_proto rejects a gate whose claimed margin is finer than the metric's
measured error -- a between window narrower than twice the error, or a
threshold quoted to a finer decimal step. Inert until a metric is calibrated,
live the moment one is.

Uncalibrated gates are labelled in the runbook rather than the validator:
validate_proto output drives an LLM repair attempt, so flagging them there
would fire on every gate of every run and repair nothing."
```

---

## Verification

- [ ] `registry/calibration.json` is schema 2, promotes nothing, and its `tools` map is empty
- [ ] `registry/proto_catalog.json` is schema 3 with `calibration` on all 311 metric rows and 0 parse failures
- [ ] `registry/proto_metrics.json` is schema 4 with `calibration` keyed by tool
- [ ] Every tool in the committed catalogue still reports `status: needs_calibration`
- [ ] Every evidence item in a fresh run carries `testable_by.rankable_by == []`
- [ ] `validate_proto` returns no problem for an uncalibrated gate
- [ ] A promotion lacking `measured_error` or `benchmark` is refused
- [ ] litkb suite passes; 007 suite passes
- [ ] `uv run --project . python -m litkb registry-check` on the binder plan still reports `partial`, not `full`
