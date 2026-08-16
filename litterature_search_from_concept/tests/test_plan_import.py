import json
import types
from unittest.mock import patch
from pathlib import Path
from litkb import cli, contracts, paperclip

ROWS = ["CraCRY ODMR", "MagLOV ODMR", "magnetothermal protein switch"]
GROUPS = {"cryptochrome_rf": ["CraCRY ODMR"],
          "lov_radical_pair": ["MagLOV ODMR"],
          "magnetothermal": ["magnetothermal protein switch"]}


def test_every_row_lands_in_exactly_one_class():
    plan = cli.rows_to_plan(ROWS, "objective", "rfp", GROUPS)
    placed = [p for c in plan["mechanism_classes"] for p in c["search_phrases"]]
    assert sorted(placed) == sorted(ROWS)


def test_generated_plan_is_schema_valid():
    plan = cli.rows_to_plan(ROWS, "objective", "rfp", GROUPS)
    assert contracts.validate_plan(plan) == []


def test_ungrouped_row_raises_rather_than_being_dropped():
    try:
        cli.rows_to_plan(ROWS + ["orphan keyword"], "o", "rfp", GROUPS)
    except contracts.ContractError as e:
        assert "orphan keyword" in str(e)
    else:
        raise AssertionError("expected ContractError for an ungrouped row")


def test_search_with_exact_true_includes_e_flag():
    """Verify that search(exact=True) passes -e flag to paperclip."""
    captured_args = []

    def mock_run(args):
        captured_args.append(args)
        return "Found 3 papers  [s_abc123]"

    with patch("litkb.paperclip._run", side_effect=mock_run):
        paperclip.search("test phrase", exact=True)

    assert captured_args
    assert "-e" in captured_args[0]


def test_search_with_exact_false_omits_e_flag():
    """Verify that search(exact=False) omits -e flag for hybrid ranking."""
    captured_args = []

    def mock_run(args):
        captured_args.append(args)
        return "Found 5 papers  [s_def456]"

    with patch("litkb.paperclip._run", side_effect=mock_run):
        paperclip.search("test phrase", exact=False)

    assert captured_args
    assert "-e" not in captured_args[0]


def test_count_with_exact_true_includes_e_flag():
    """Verify that count(exact=True) passes -e flag to paperclip."""
    captured_args = []

    def mock_run(args):
        captured_args.append(args)
        return "Found 2 papers"

    with patch("litkb.paperclip._run", side_effect=mock_run):
        paperclip.count("test phrase", exact=True)

    assert captured_args
    assert "-e" in captured_args[0]


def test_count_with_exact_false_omits_e_flag():
    """Verify that count(exact=False) omits -e flag for hybrid ranking."""
    captured_args = []

    def mock_run(args):
        captured_args.append(args)
        return "Found 4 papers"

    with patch("litkb.paperclip._run", side_effect=mock_run):
        paperclip.count("test phrase", exact=False)

    assert captured_args
    assert "-e" not in captured_args[0]


def test_cmd_search_derives_exact_true_when_no_search_mode_key(tmp_path):
    """Verify cmd_search derives exact=True when plan has NO search_mode key."""
    plan = {
        "objective": "test",
        "slug": "test-slug",
        "mechanism_classes": [
            {
                "id": "class1",
                "question": "test?",
                "candidate_evaluators": [],
                "search_phrases": ["test phrase"],
                "mechanism_patterns": ["pattern"],
            }
        ],
        "exclusions": [],
    }
    # NO search_mode key -- should default to exact=True
    assert "search_mode" not in plan
    assert contracts.validate_plan(plan) == []

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan))

    captured_exact = []

    def mock_search(phrase, sources, n, exact=False):
        captured_exact.append(exact)
        return {"phrase": phrase, "set_id": "s_abc123", "n_papers": 3}

    args = types.SimpleNamespace(
        plan=str(plan_file),
        sources="pmc",
        n=100,
        out=None,
    )

    with patch("litkb.cli.search", side_effect=mock_search):
        cli.cmd_search(args)

    assert captured_exact
    assert captured_exact[0] is True, "Plan without search_mode should use exact=True"


def test_cmd_search_derives_exact_false_when_search_mode_semantic(tmp_path):
    """Verify cmd_search derives exact=False when plan has search_mode=semantic."""
    plan = {
        "objective": "test",
        "slug": "test-slug",
        "search_mode": "semantic",
        "mechanism_classes": [
            {
                "id": "class1",
                "question": "test?",
                "candidate_evaluators": [],
                "search_phrases": ["test phrase"],
                "mechanism_patterns": ["pattern"],
            }
        ],
        "exclusions": [],
    }
    assert plan.get("search_mode") == "semantic"
    assert contracts.validate_plan(plan) == []

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan))

    captured_exact = []

    def mock_search(phrase, sources, n, exact=False):
        captured_exact.append(exact)
        return {"phrase": phrase, "set_id": "s_def456", "n_papers": 5}

    args = types.SimpleNamespace(
        plan=str(plan_file),
        sources="pmc",
        n=100,
        out=None,
    )

    with patch("litkb.cli.search", side_effect=mock_search):
        cli.cmd_search(args)

    assert captured_exact
    assert captured_exact[0] is False, "Plan with search_mode=semantic should use exact=False"


def test_cmd_plan_validate_derives_exact_true_when_no_search_mode_key(tmp_path):
    """Verify cmd_plan_validate probe derives exact=True when plan has NO search_mode key."""
    plan = {
        "objective": "test",
        "slug": "test-slug",
        "mechanism_classes": [
            {
                "id": "class1",
                "question": "test?",
                "candidate_evaluators": [],
                "search_phrases": ["test phrase"],
                "mechanism_patterns": ["pattern"],
            }
        ],
        "exclusions": [],
    }
    # NO search_mode key -- should default to exact=True
    assert "search_mode" not in plan
    assert contracts.validate_plan(plan) == []

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan))

    captured_exact = []

    def mock_count(phrase, sources, exact=False):
        captured_exact.append(exact)
        return 5

    args = types.SimpleNamespace(
        plan=str(plan_file),
        probe=True,
        sources="pmc",
        out=None,
    )

    with patch("litkb.cli.count", side_effect=mock_count):
        cli.cmd_plan_validate(args)

    assert captured_exact
    assert captured_exact[0] is True, "Plan without search_mode should probe with exact=True"


def test_cmd_plan_validate_derives_exact_false_when_search_mode_semantic(tmp_path):
    """Verify cmd_plan_validate probe derives exact=False when plan has search_mode=semantic."""
    plan = {
        "objective": "test",
        "slug": "test-slug",
        "search_mode": "semantic",
        "mechanism_classes": [
            {
                "id": "class1",
                "question": "test?",
                "candidate_evaluators": [],
                "search_phrases": ["test phrase"],
                "mechanism_patterns": ["pattern"],
            }
        ],
        "exclusions": [],
    }
    assert plan.get("search_mode") == "semantic"
    assert contracts.validate_plan(plan) == []

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan))

    captured_exact = []

    def mock_count(phrase, sources, exact=False):
        captured_exact.append(exact)
        return 8

    args = types.SimpleNamespace(
        plan=str(plan_file),
        probe=True,
        sources="pmc",
        out=None,
    )

    with patch("litkb.cli.count", side_effect=mock_count):
        cli.cmd_plan_validate(args)

    assert captured_exact
    assert captured_exact[0] is False, "Plan with search_mode=semantic should probe with exact=False"
