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
