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
