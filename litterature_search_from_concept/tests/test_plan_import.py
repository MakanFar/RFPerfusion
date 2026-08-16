from unittest.mock import patch
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
