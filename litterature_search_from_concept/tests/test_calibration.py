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
             "measures": [{"metric": "avg_plddt"}]},
            {"key": "esm2-embedding", "status": "needs_calibration",
             "measures": []},
        ],
        "n_tools": 2,
        "parse_failures": [],
    }


def _curation(tools):
    return {"schema_version": proto.CALIBRATION_SCHEMA_VERSION, "tools": tools}


def test_curated_tool_is_promoted_to_validated():
    """The whole point: a hand-curated promotion must reach the rebuilt
    catalogue instead of being overwritten by the generator's default."""
    out, _ = proto.apply_calibration(
        _catalog(), _curation({"esmfold-prediction": {"status": "validated"}}))

    by_key = {t["key"]: t for t in out["tools"]}
    assert by_key["esmfold-prediction"]["status"] == "validated"


def test_tool_absent_from_curation_stays_needs_calibration():
    """Silence is not a promotion. Framework section 6 forbids ranking on an
    uncalibrated tool, so the default must remain the conservative one."""
    out, _ = proto.apply_calibration(
        _catalog(), _curation({"esmfold-prediction": {"status": "validated"}}))

    by_key = {t["key"]: t for t in out["tools"]}
    assert by_key["esm2-embedding"]["status"] == "needs_calibration"


def test_curated_key_missing_from_catalogue_is_reported_not_dropped():
    """Rejections ship. A tool that was renamed or retired upstream leaves a
    curation entry pointing at nothing; dropping it silently would let
    calibration effort evaporate with no trace."""
    _, orphans = proto.apply_calibration(
        _catalog(), _curation({"tool-that-went-away": {"status": "validated"}}))

    assert orphans == ["tool-that-went-away"]


def test_unknown_status_value_is_rejected_loudly():
    """A typo like "validatd" would otherwise read as "not validated" and
    quietly fail to promote -- the calibration equivalent of failing open."""
    with pytest.raises(ValueError, match="validatd"):
        proto.apply_calibration(
            _catalog(), _curation({"esmfold-prediction": {"status": "validatd"}}))


def test_wrong_curation_schema_version_is_refused():
    """Same rule the catalogue reader already enforces: coercing an unknown
    version is how a mis-read promotion sneaks in."""
    bad = {"schema_version": 99, "tools": {}}
    with pytest.raises(ValueError, match="schema_version"):
        proto.apply_calibration(_catalog(), bad)


def test_no_curation_leaves_every_tool_uncalibrated():
    """The state of the repo today: no tool is calibrated, and applying an
    empty curation must be a no-op rather than a promotion."""
    out, orphans = proto.apply_calibration(_catalog(), _curation({}))

    assert [t["status"] for t in out["tools"]] == ["needs_calibration"] * 2
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
    """Guards the shipped pair: every key curated in registry/calibration.json
    must still exist in registry/proto_catalog.json. This is the test that
    fails when a proto-tools rename orphans real calibration work."""
    catalog = json.load(open("../registry/proto_catalog.json"))
    curation = json.load(open("../registry/calibration.json"))

    _, orphans = proto.apply_calibration(catalog, curation)

    assert orphans == [], (
        f"curated tool keys no longer in the catalogue: {orphans}")
