import argparse
import json

from litkb import cli, contracts

BRIEF_PLAN = {
    "search_phrases": ["radio frequency protein", "magnetothermal switch"],
    "mechanism_patterns": ["dielectric heating", "nanoparticle-mediated gating"],
    "notes": "Excluded generic protein searches; focused on RF-gated actuation.",
}


def test_adopted_plan_is_schema_valid():
    plan = contracts.adopt_brief_plan(BRIEF_PLAN, "objective text", "rfp", "brief/plan_rfp.json")
    assert contracts.validate_plan(plan) == []


def test_adopted_plan_has_exactly_one_class():
    plan = contracts.adopt_brief_plan(BRIEF_PLAN, "objective text", "rfp", "brief/plan_rfp.json")
    assert len(plan["mechanism_classes"]) == 1


def test_search_phrases_survive_verbatim():
    plan = contracts.adopt_brief_plan(BRIEF_PLAN, "objective text", "rfp", "brief/plan_rfp.json")
    assert plan["mechanism_classes"][0]["search_phrases"] == BRIEF_PLAN["search_phrases"]


def test_mechanism_patterns_survive_verbatim():
    plan = contracts.adopt_brief_plan(BRIEF_PLAN, "objective text", "rfp", "brief/plan_rfp.json")
    assert plan["mechanism_classes"][0]["mechanism_patterns"] == BRIEF_PLAN["mechanism_patterns"]


def test_search_mode_is_exact_not_semantic():
    """The brief's phrases were written for paperclip_kb.py, which matches
    them as strict literals -- plan-adopt must not silently switch them to
    hybrid/semantic ranking."""
    plan = contracts.adopt_brief_plan(BRIEF_PLAN, "objective text", "rfp", "brief/plan_rfp.json")
    assert plan["search_mode"] == "exact"


def test_class_id_is_derived_from_slug():
    plan = contracts.adopt_brief_plan(BRIEF_PLAN, "objective text", "rf-protein", "p.json")
    assert plan["mechanism_classes"][0]["id"] == "rf_protein"


def test_question_comes_from_notes():
    plan = contracts.adopt_brief_plan(BRIEF_PLAN, "objective text", "rfp", "p.json")
    assert plan["mechanism_classes"][0]["question"] == BRIEF_PLAN["notes"]


def test_empty_notes_falls_back_to_a_stated_question():
    empty_notes_plan = dict(BRIEF_PLAN, notes="")
    plan = contracts.adopt_brief_plan(empty_notes_plan, "gate a channel with RF", "rfp", "p.json")
    q = plan["mechanism_classes"][0]["question"]
    assert q and "gate a channel with RF" in q


def test_notes_carried_into_exclusions_as_one_entry():
    plan = contracts.adopt_brief_plan(BRIEF_PLAN, "objective text", "rfp", "p.json")
    assert len(plan["exclusions"]) == 1
    assert plan["exclusions"][0]["excluded"] == BRIEF_PLAN["notes"]
    assert "brief" in plan["exclusions"][0]["reason"]


def test_provenance_records_the_source_path():
    plan = contracts.adopt_brief_plan(BRIEF_PLAN, "objective text", "rfp", "brief/plan_rfp.json")
    assert plan["provenance"]["adopted_from"] == "brief_plan"
    assert plan["provenance"]["source_path"] == "brief/plan_rfp.json"


def test_one_class_plan_reports_framework_minimum_not_met():
    """Documents the honest consequence, per the task: a flat brief plan
    genuinely carries one mechanism class, so `litkb search`'s coverage gate
    (>=6 classes) will read false on an adopted plan. That is accurate, not
    a defect in plan-adopt."""
    plan = contracts.adopt_brief_plan(BRIEF_PLAN, "objective text", "rfp", "p.json")
    assert len(plan["mechanism_classes"]) < 6


def test_missing_key_fails_with_a_message_naming_it():
    incomplete = {"search_phrases": ["x"], "notes": "n"}  # mechanism_patterns missing
    try:
        contracts.adopt_brief_plan(incomplete, "o", "s", "p.json")
    except contracts.ContractError as e:
        assert "mechanism_patterns" in str(e)
    else:
        raise AssertionError("expected ContractError naming the missing key")


def test_missing_multiple_keys_names_all_of_them():
    bare = {}
    try:
        contracts.adopt_brief_plan(bare, "o", "s", "p.json")
    except contracts.ContractError as e:
        msg = str(e)
        assert "search_phrases" in msg
        assert "mechanism_patterns" in msg
        assert "notes" in msg
    else:
        raise AssertionError("expected ContractError naming all missing keys")


def test_empty_search_phrases_list_is_rejected():
    plan = dict(BRIEF_PLAN, search_phrases=[])
    try:
        contracts.adopt_brief_plan(plan, "o", "s", "p.json")
    except contracts.ContractError as e:
        assert "search_phrases" in str(e)
    else:
        raise AssertionError("expected ContractError for empty search_phrases")


def test_cmd_plan_adopt_writes_a_schema_valid_plan(tmp_path):
    plan_path = tmp_path / "plan_rfp.json"
    plan_path.write_text(json.dumps(BRIEF_PLAN))
    out_path = tmp_path / "adopted.json"

    args = argparse.Namespace(plan=str(plan_path), objective="gate TRPV1 with RF",
                              slug="rfp", out=str(out_path))
    cli.cmd_plan_adopt(args)

    result = json.loads(out_path.read_text())
    assert contracts.validate_plan(result) == []
    assert result["provenance"]["source_path"] == str(plan_path)
