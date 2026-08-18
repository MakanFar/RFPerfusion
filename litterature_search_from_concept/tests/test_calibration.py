"""Curated calibration status must survive registry regeneration.

`proto-sync` rebuilds `registry/proto_catalog.json` from scratch every run and
writes `status: "needs_calibration"` unconditionally, never reading the file it
is about to overwrite. The litkb skill nonetheless documents `status` as "the
only field a human curates by hand afterward" -- so a promotion to `validated`
survived exactly until the next sync, and the docs tell you to sync whenever
the proto-tools catalogue moves.

Keeping the curation in a SEPARATE file and overlaying it at build time is
what makes it durable: the derived file stays fully derived (the property that
made `measures` trustworthy), and the curated fact lives somewhere the
generator never writes.

`apply_calibration` returns `(catalog, orphans)` rather than embedding the
orphan list in the catalogue, so the committed registry keeps its v2 shape and
needs no regeneration to adopt this.
"""

import json

import pytest

from litkb import proto


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


def test_missing_calibration_file_reads_as_no_curation():
    """A checkout without the file must still sync -- and must produce the
    conservative state (everything uncalibrated), never an error and never a
    promotion. `cmd_proto_sync` itself needs a live proto project and is not
    unit tested (see test_cli_snapshot.py), so the composable part is."""
    from litkb.cli import _load_calibration

    curation = _load_calibration("does/not/exist.json")

    assert curation["schema_version"] == proto.CALIBRATION_SCHEMA_VERSION
    assert curation["tools"] == {}


def test_calibration_file_is_read_from_disk_when_present(tmp_path):
    from litkb.cli import _load_calibration

    path = tmp_path / "calibration.json"
    path.write_text(json.dumps(
        {"schema_version": 1, "tools": {"esmfold-prediction": {"status": "validated"}}}))

    curation = _load_calibration(str(path))

    assert curation["tools"]["esmfold-prediction"]["status"] == "validated"


def test_committed_curation_file_parses_and_matches_the_real_catalogue():
    catalog = json.load(open("../registry/proto_catalog.json"))
    curation = json.load(open("../registry/calibration.json"))

    _, orphans = proto.apply_calibration(catalog, curation)

    assert orphans == [], f"curated keys no longer in the catalogue: {orphans}"


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
