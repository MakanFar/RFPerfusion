import argparse
import json

from litkb import cli, contracts

BRIEF_PLAN = {
    "search_phrases": ["radio frequency protein"],
    "mechanism_patterns": ["dielectric heating"],
    "notes": "some notes",
}


def test_output_dir_places_the_file_inside_it(tmp_path):
    run_dir = tmp_path / "20260815-120000-rfp"
    args = argparse.Namespace(plan=_write_plan(tmp_path), objective="o", slug="rfp",
                              out=None, output_dir=str(run_dir))
    cli.cmd_plan_adopt(args)

    expected = run_dir / "plan_rfp.json"
    assert expected.exists()
    result = json.loads(expected.read_text())
    assert contracts.validate_plan(result) == []


def test_output_dir_creates_missing_parents(tmp_path):
    run_dir = tmp_path / "nested" / "does" / "not" / "exist-yet"
    args = argparse.Namespace(plan=_write_plan(tmp_path), objective="o", slug="rfp",
                              out=None, output_dir=str(run_dir))
    cli.cmd_plan_adopt(args)
    assert (run_dir / "plan_rfp.json").exists()


def test_o_alone_is_unchanged_when_output_dir_absent(tmp_path):
    """--output-dir is additive, not a replacement: -o on its own must keep
    working exactly as it did before this feature existed."""
    out_path = tmp_path / "custom_name.json"
    args = argparse.Namespace(plan=_write_plan(tmp_path), objective="o", slug="rfp",
                              out=str(out_path), output_dir=None)
    cli.cmd_plan_adopt(args)
    assert out_path.exists()


def test_o_and_output_dir_together_joins_relative_o_under_output_dir(tmp_path):
    run_dir = tmp_path / "run"
    args = argparse.Namespace(plan=_write_plan(tmp_path), objective="o", slug="rfp",
                              out="myplan.json", output_dir=str(run_dir))
    cli.cmd_plan_adopt(args)
    assert (run_dir / "myplan.json").exists()


def _write_plan(tmp_path):
    path = tmp_path / "brief_plan.json"
    path.write_text(json.dumps(BRIEF_PLAN))
    return str(path)
