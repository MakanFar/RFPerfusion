from litkb import cli, contracts

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
