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
