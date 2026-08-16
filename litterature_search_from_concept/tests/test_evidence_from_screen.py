import argparse
import json

from litkb import cli, contracts, proto

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


def test_extracted_by_defaults_to_the_worker_that_actually_runs():
    """structured-extraction is gated to GXL testers on this account (see
    paperclip.py's map_papers default-worker comment) and never touches a
    real run -- item_from_mechanism must not default to naming it, the
    same rule draft_artifact.extractor already follows."""
    item = contracts.item_from_mechanism(1, "thermal", MECH, "PMC1", {"doi": "d"})
    assert item["extracted_by"] == "quick-reader"


def test_extracted_by_honours_an_explicitly_passed_worker():
    item = contracts.item_from_mechanism(1, "thermal", MECH, "PMC1", {"doi": "d"},
                                         extracted_by="eligibility-screen")
    assert item["extracted_by"] == "eligibility-screen"


def test_cmd_evidence_records_the_worker_screen_actually_used(tmp_path, monkeypatch):
    """cmd_evidence must read back the worker cmd_screen threaded through
    its own output (SCREEN_WORKER, via the `extracted_by` key) rather than
    assuming one -- this is the same wiring A2 established for cmd_dig,
    applied to the evidence stage."""
    screen_path = tmp_path / "screen.json"
    screen_path.write_text(json.dumps({
        "slug": "s",
        "extracted_by": "quick-reader",
        "papers": [{"doc_id": "PMC1", "class_id": "thermal", "mechanisms": [MECH]}],
    }))
    out_path = tmp_path / "evidence.json"
    args = argparse.Namespace(screen=str(screen_path), registry=str(tmp_path / "nope.json"),
                              out=str(out_path))

    monkeypatch.setattr(cli, "meta", lambda doc_id: {"doi": "d", "title": "t"})
    cli.cmd_evidence(args)

    result = json.loads(out_path.read_text())
    assert result["items"][0]["extracted_by"] == "quick-reader"
