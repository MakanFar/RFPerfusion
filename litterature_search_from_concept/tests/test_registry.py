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
    # Every row carries a calibration block -- that is the guard, and it is
    # what makes an uncalibrated row read as "not calibrated" rather than as
    # "no opinion". Exactly one row is validated (esmfold-prediction's
    # avg_plddt); asserting every row is uncalibrated stopped being the right
    # check at the first promotion.
    validated = [m for m in rows if m["calibration"]["status"] == "validated"]
    assert len(validated) == 1
    assert validated[0]["metric"] == "avg_plddt"
    assert {m["calibration"]["status"] for m in rows} <= {"needs_calibration", "validated"}
