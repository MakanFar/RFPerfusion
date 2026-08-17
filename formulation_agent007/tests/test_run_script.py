import shlex
import shutil
import subprocess
import sys
from unittest.mock import patch

from pathlib import Path

import pytest

from formulation_agent007.emit import save_brief

# The real litkb project, imported by path so this test validates the emitted
# commands against litkb's *actual* argparse -- not against our own
# restatement of its flags, which is exactly the kind of restatement that
# drifted (a positional vs. a flag) and slipped past every other test here.
REPO_ROOT = Path(__file__).resolve().parents[2]
LITKB_PROJECT_DIR = REPO_ROOT / "litterature_search_from_concept"
LITKB_CLI_PATH = LITKB_PROJECT_DIR / "litkb" / "cli.py"

# Every litkb stage this script's litkb block invokes. Only these command
# functions are stubbed out below, so a real invocation of any other
# subcommand (there are none in the emitted script) would still execute for
# real and fail loudly rather than being silently no-op'd.
LITKB_STAGE_FNS = (
    "cmd_plan_adopt", "cmd_search", "cmd_screen", "cmd_dig", "cmd_bind",
    "cmd_evidence", "cmd_report", "cmd_manifest",
)


def _load_litkb_cli():
    """Import litkb.cli from the sibling project by path, the same pattern
    `paperclip_kb` uses in conftest.py. litkb is a package with relative
    imports (`from . import contracts, ...`) and `contracts` in turn imports
    the import-nothing `plan_contract` module from the project root by
    absolute import, so the project root -- not just the `litkb/` dir --
    must be on sys.path. Every import litkb.cli pulls in is stdlib-only, so
    this stays self-contained and offline; skips cleanly if the sibling
    project has moved."""
    if not LITKB_CLI_PATH.exists():
        pytest.skip(f"litkb cli not found at {LITKB_CLI_PATH}")
    if str(LITKB_PROJECT_DIR) not in sys.path:
        sys.path.insert(0, str(LITKB_PROJECT_DIR))
    import litkb.cli as cli  # noqa: PLC0415 (deliberately lazy/off the hot path)
    return cli


def _extract_litkb_commands(script: str) -> list[list[str]]:
    """Pull each `... python -m litkb <stage> ...` line out of the emitted
    script as an argv list, i.e. everything after the `litkb` module name --
    exactly what `litkb.cli.main(argv)` expects."""
    commands = []
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "python -m litkb " not in stripped:
            continue
        tokens = shlex.split(stripped)
        idx = tokens.index("litkb")
        commands.append(tokens[idx + 1:])
    return commands


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


def test_emitted_litkb_commands_match_the_real_cli(brief, tmp_path):
    """Guard against a wrong-flag/positional mismatch between what emit.py
    writes and what litkb.cli actually accepts.

    `bash -n` only proves the script parses as shell; it says nothing about
    whether `litkb manifest <file>` is a positional litkb's own argparse will
    accept. This test runs every emitted `litkb <stage> ...` argv through the
    real `litkb.cli` argparser (built fresh inside `cli.main`, same as a real
    invocation would build it) with each stage's command function replaced by
    a no-op, so a malformed invocation is caught by argparse's own
    `unrecognized arguments` / `the following arguments are required` errors
    without ever touching the network, paperclip, or the filesystem beyond
    what save_brief already wrote.
    """
    cli = _load_litkb_cli()
    script = _script(brief, tmp_path)
    commands = _extract_litkb_commands(script)

    # Sanity: every stage the litkb block claims to run was actually found as
    # a parseable command line, so this test cannot pass by silently
    # extracting nothing.
    stages_found = {argv[0] for argv in commands}
    assert stages_found == {
        "plan-adopt", "search", "screen", "dig", "bind", "evidence", "report",
        "manifest",
    }

    noops = {name: (lambda args: None) for name in LITKB_STAGE_FNS}
    with patch.multiple(cli, **noops):
        for argv in commands:
            try:
                cli.main(argv)
            except SystemExit as exc:
                pytest.fail(
                    f"litkb's own argparse rejected the emitted command "
                    f"{argv!r}: exit code {exc.code}"
                )
