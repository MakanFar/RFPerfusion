import pytest

import plan_contract
from litkb import contracts

GOOD = {"search_phrases": ["a phrase here"], "mechanism_patterns": ["a pattern"],
        "notes": "why things were left out"}


def _load_paperclip_kb():
    """Load the real paperclip_kb.py by path, exactly as
    formulation_agent007/tests/test_emit.py does, so this suite exercises
    the actual function rather than a restatement of its rules."""
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "paperclip_kb.py"
    spec = importlib.util.spec_from_file_location("paperclip_kb", path)
    kb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kb)
    return kb


def test_valid_plan_has_no_errors():
    assert plan_contract.check(GOOD) == []


def test_missing_key_is_named():
    plan = {k: v for k, v in GOOD.items() if k != "notes"}
    errors = plan_contract.check(plan)
    assert "notes" in errors[0][1]


def test_empty_list_is_rejected():
    plan = dict(GOOD, search_phrases=[])
    assert any("search_phrases" in msg for _, msg in plan_contract.check(plan))


def test_non_string_entries_are_rejected():
    plan = dict(GOOD, mechanism_patterns=[1, 2])
    assert any("mechanism_patterns" in msg for _, msg in plan_contract.check(plan))


# -- kind tagging -----------------------------------------------------------
# check() tags every problem with its KIND ("type" or "value") rather than
# leaving callers to sniff error-message wording for "must be a string" to
# recover which exception type paperclip_kb.validate_plan should raise. This
# pins the tagging directly so a rewording of a message can never silently
# flip which exception type a case maps to.

def test_non_dict_plan_is_tagged_type():
    kinds = [kind for kind, _ in plan_contract.check("not a dict")]
    assert kinds == ["type"]


def test_missing_key_is_tagged_value():
    plan = {k: v for k, v in GOOD.items() if k != "notes"}
    kinds = [kind for kind, _ in plan_contract.check(plan)]
    assert kinds == ["value"]


def test_empty_list_is_tagged_value():
    plan = dict(GOOD, search_phrases=[])
    kinds = [kind for kind, _ in plan_contract.check(plan)]
    assert kinds == ["value"]


def test_non_string_entries_are_tagged_value():
    plan = dict(GOOD, mechanism_patterns=[1, 2])
    kinds = [kind for kind, _ in plan_contract.check(plan)]
    assert kinds == ["value"]


def test_notes_wrong_type_is_tagged_type():
    plan = dict(GOOD, notes=123)
    kinds = [kind for kind, _ in plan_contract.check(plan)]
    assert kinds == ["type"]


def test_litkb_and_the_script_agree_on_every_case():
    """The anti-drift guarantee, now structural rather than by inspection."""
    kb = _load_paperclip_kb()

    cases = [GOOD,
             {k: v for k, v in GOOD.items() if k != "notes"},
             dict(GOOD, search_phrases=[]),
             dict(GOOD, notes=123)]
    for plan in cases:
        litkb_errors = contracts.validate_brief_plan(plan)
        try:
            kb.validate_plan(plan)
            kb_failed = False
        except (TypeError, ValueError):
            kb_failed = True
        assert bool(litkb_errors) == kb_failed, plan


def test_validate_plan_exception_types_are_unchanged():
    """Pins paperclip_kb.validate_plan's pre-refactor raising contract
    exactly: non-dict plans and a non-string `notes` raise TypeError; every
    other rejection raises ValueError. formulation_agent007/tests/test_emit.py
    depends on the real function behaving this way."""
    kb = _load_paperclip_kb()

    with pytest.raises(TypeError):
        kb.validate_plan("not a dict")

    with pytest.raises(TypeError):
        kb.validate_plan(dict(GOOD, notes=123))

    with pytest.raises(ValueError):
        kb.validate_plan({k: v for k, v in GOOD.items() if k != "notes"})

    with pytest.raises(ValueError):
        kb.validate_plan(dict(GOOD, search_phrases=[]))

    with pytest.raises(ValueError):
        kb.validate_plan(dict(GOOD, mechanism_patterns=[1, 2]))

    assert kb.validate_plan(GOOD) == GOOD
