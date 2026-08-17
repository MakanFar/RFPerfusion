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
