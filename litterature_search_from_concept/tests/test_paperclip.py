from unittest.mock import patch

from litkb import paperclip


class _FakeCompletedProcess:
    """Minimal stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_run_raises_on_crash_disguised_as_no_match():
    """DEFECT 1: paperclip's launcher crashed at import (ModuleNotFoundError
    under `uv run`, wrong Python first on PATH), printed a traceback to
    stderr, produced EMPTY stdout, and exited 1 -- the same exit code as a
    genuine grep-style no-match. `_run` used to return that empty stdout as
    if it were a real "0 papers" result, so a 23-phrase search silently
    reported zero matches for every phrase. returncode != 0 + empty stdout +
    non-empty stderr must now raise instead of being swallowed."""
    traceback_text = (
        "Traceback (most recent call last):\n"
        "  File \"/Users/skynet/.local/bin/paperclip\", line 5, in <module>\n"
        "    import requests\n"
        "ModuleNotFoundError: No module named 'requests'\n"
    )
    fake = _FakeCompletedProcess(returncode=1, stdout="", stderr=traceback_text)

    with patch("litkb.paperclip.shutil.which", return_value="/usr/bin/paperclip"), \
            patch("litkb.paperclip.subprocess.run", return_value=fake):
        try:
            paperclip._run(["search", "-s", "pmc", "some phrase"])
        except paperclip.PaperclipError as e:
            assert "ModuleNotFoundError" in str(e)
        else:
            raise AssertionError(
                "expected PaperclipError when paperclip crashed with empty "
                "stdout and a stderr traceback")


def test_run_returns_normally_for_genuine_no_match():
    """The legitimate no-match path must keep working: `paperclip grep`
    exits 1 and prints "No matches for /.../ in s_xxx" to STDOUT (not
    stderr). This must still return normally, not raise."""
    fake = _FakeCompletedProcess(
        returncode=1,
        stdout="No matches for /foo/ in s_abc123\n",
        stderr="",
    )

    with patch("litkb.paperclip.shutil.which", return_value="/usr/bin/paperclip"), \
            patch("litkb.paperclip.subprocess.run", return_value=fake):
        out = paperclip._run(["grep", "--from", "s_abc123", "-e", "foo"])

    assert "No matches for" in out


def test_map_papers_argv_has_no_dash_j():
    """DEFECT 2: passing -j at any value triggers the "Parallel map workers
    are currently limited to GXL testers" gate on this account, regardless
    of --worker (verified live). map_papers must never emit -j."""
    captured_args = []

    def mock_run(args):
        captured_args.append(args)
        return "Map complete: 1/1 papers\n"

    with patch("litkb.paperclip._run", side_effect=mock_run):
        paperclip.map_papers("s_abc123", "a query", {"type": "object"})

    assert captured_args
    assert "-j" not in captured_args[0]
