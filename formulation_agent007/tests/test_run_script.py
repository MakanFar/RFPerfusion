import shlex
import shutil
import subprocess

from pathlib import Path

from formulation_agent007.emit import save_brief


def _script(brief, tmp_path) -> str:
    save_brief(brief, str(tmp_path))
    return (tmp_path / "run_literature.sh").read_text()


def _assert_valid_bash(script: str) -> None:
    """The script must parse as bash without being executed -- executing it
    would make real network calls."""
    bash = shutil.which("bash")
    assert bash is not None, "bash not found on PATH"
    result = subprocess.run(
        [bash, "-n", "-c", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_litkb_chain_is_the_default_block(brief, tmp_path):
    script = _script(brief, tmp_path)
    for stage in ("plan-adopt", "search", "screen", "dig", "bind",
                  "evidence", "report", "manifest"):
        assert f"litkb {stage}" in script or f"-m litkb {stage}" in script


def test_grep_path_is_retained_and_labelled(brief, tmp_path):
    script = _script(brief, tmp_path)
    assert "paperclip_kb.py" in script
    assert "no LLM read quota" in script


def test_litkb_block_precedes_the_grep_block(brief, tmp_path):
    script = _script(brief, tmp_path)
    assert script.index("plan-adopt") < script.index("paperclip_kb.py")


def test_script_names_the_directory_litkb_must_run_from(brief, tmp_path):
    # litkb's --registry and --project defaults are relative to that directory.
    script = _script(brief, tmp_path)
    assert "cd litterature_search_from_concept" in script


def test_script_is_still_bash_strict_mode(brief, tmp_path):
    assert "set -euo pipefail" in _script(brief, tmp_path)


def test_evidence_is_labelled_unassessed(brief, tmp_path):
    script = _script(brief, tmp_path)
    assert "unassessed" in script
    assert "litkb label" in script


# --------------------------------------------------------------------------
# Additional required tests: the emitted script must be verifiably correct,
# not merely contain the right substrings.
# --------------------------------------------------------------------------


def test_emitted_script_is_valid_bash_relative_output_dir(brief, tmp_path):
    out_dir = tmp_path / "run-relative"
    out_dir.mkdir()
    save_brief(brief, str(out_dir))
    script = (out_dir / "run_literature.sh").read_text()
    _assert_valid_bash(script)


def test_emitted_script_is_valid_bash_absolute_output_dir(brief, tmp_path):
    out_dir = (tmp_path / "run-absolute").resolve()
    out_dir.mkdir()
    save_brief(brief, str(out_dir))
    script = (out_dir / "run_literature.sh").read_text()
    _assert_valid_bash(script)
    assert str(out_dir) in script


def test_emitted_script_is_valid_bash_output_dir_with_space(brief, tmp_path):
    out_dir = tmp_path / "run with space"
    out_dir.mkdir()
    save_brief(brief, str(out_dir))
    script = (out_dir / "run_literature.sh").read_text()
    _assert_valid_bash(script)
    # The path must be quoted wherever it is interpolated, so that shell
    # word-splitting (bash -n's parser, and any real run) treats the whole
    # path -- space included -- as a single argument rather than splitting
    # it into two.
    found_split_path = False
    for line in script.splitlines():
        stripped = line.strip()
        if "run with space" not in line or stripped.startswith("#"):
            continue
        found_split_path = True
        tokens = shlex.split(line)
        assert any("run with space" in tok for tok in tokens), line
    assert found_split_path  # sanity: the path does appear somewhere


def test_litkb_block_precedes_grep_block_for_all_output_dir_kinds(brief, tmp_path):
    for out_dir in (
        tmp_path / "rel",
        (tmp_path / "abs").resolve(),
        tmp_path / "with space",
    ):
        out_dir.mkdir()
        save_brief(brief, str(out_dir))
        script = (out_dir / "run_literature.sh").read_text()
        assert script.index("plan-adopt") < script.index("paperclip_kb.py")


def test_script_cds_into_litkb_dir_for_all_output_dir_kinds(brief, tmp_path):
    for out_dir in (
        tmp_path / "rel2",
        (tmp_path / "abs2").resolve(),
        tmp_path / "with space 2",
    ):
        out_dir.mkdir()
        save_brief(brief, str(out_dir))
        script = (out_dir / "run_literature.sh").read_text()
        assert "cd litterature_search_from_concept" in script
