from __future__ import annotations

import os
import subprocess
import unittest
from unittest.mock import patch

from litterature_search_from_concept.paperclip_kb import (
    build_kb,
    host_env,
    run,
    search_all,
    validate_plan,
)


class TestPlanValidation(unittest.TestCase):
    def test_accepts_expected_contract(self):
        plan = {
            "search_phrases": ["radio frequency protein"],
            "mechanism_patterns": ["dielectric heating"],
            "notes": "Excluded generic protein searches.",
        }
        self.assertIs(validate_plan(plan), plan)

    def test_rejects_empty_search_list(self):
        with self.assertRaisesRegex(ValueError, "search_phrases"):
            validate_plan(
                {"search_phrases": [], "mechanism_patterns": ["x"], "notes": ""}
            )


class TestPaperclipEnvironment(unittest.TestCase):
    def test_removes_active_virtualenv(self):
        with patch.dict(
            os.environ,
            {
                "VIRTUAL_ENV": "/tmp/example-venv",
                "PYTHONPATH": "/tmp/modules",
                "PATH": "/tmp/example-venv/bin:/usr/bin",
            },
            clear=True,
        ):
            env = host_env()
        self.assertNotIn("VIRTUAL_ENV", env)
        self.assertNotIn("PYTHONPATH", env)
        self.assertEqual(env["PATH"], "/usr/bin")


class TestSearchAll(unittest.TestCase):
    """`paperclip search` returns its OWN result set each call -- there is no
    accumulation, so search_all must keep every set id it sees, not just the
    last one seen across a multi-phrase plan."""

    def test_collects_every_set_id_not_just_the_last(self):
        calls = []

        def fake_run(cmd, dry):
            calls.append(cmd)
            i = len(calls)
            return f"Found 3 papers\nResults ID: s_{i:06x}\n"

        with patch(
            "litterature_search_from_concept.paperclip_kb.run", side_effect=fake_run
        ):
            set_ids = search_all(
                ["phrase one", "phrase two", "phrase three"], 100, ["pmc"], False
            )

        self.assertEqual(len(calls), 3)
        self.assertEqual(len(set_ids), 3)
        self.assertEqual(len(set(set_ids)), 3)  # distinct ids, not collapsed to one

    def test_does_not_pass_the_nonexistent_tag_flag(self):
        calls = []

        def fake_run(cmd, dry):
            calls.append(cmd)
            return "Results ID: s_abcdef\n"

        with patch(
            "litterature_search_from_concept.paperclip_kb.run", side_effect=fake_run
        ):
            search_all(["phrase one"], 100, ["pmc"], False)

        self.assertTrue(calls)
        for cmd in calls:
            self.assertNotIn("--tag", cmd)


class TestBuildKbGrepsEverySet(unittest.TestCase):
    def test_greps_every_set_and_concatenates_results(self):
        import tempfile
        from pathlib import Path

        calls = []

        def fake_run(cmd, dry):
            calls.append(cmd)
            set_id = cmd[cmd.index("--from") + 1]
            return f"  DOC_{set_id}/ (1 match)\n    [abstract] hit from {set_id}\n"

        with tempfile.TemporaryDirectory() as d:
            outpath = Path(d) / "kb.txt"
            with patch(
                "litterature_search_from_concept.paperclip_kb.run",
                side_effect=fake_run,
            ):
                build_kb(["s_one", "s_two"], ["mechanism pattern"], outpath, False)
            text = outpath.read_text()

        self.assertIn("hit from s_one", text)
        self.assertIn("hit from s_two", text)
        # one grep call per set, per category (mechanism + 4 structural = 5)
        self.assertEqual(len(calls), 2 * 5)


class TestRunReturnCodeHandling(unittest.TestCase):
    """Exit 1 is grep/search-style "no matches" and must not abort a run;
    a crash (nonzero exit, empty stdout, nonempty stderr) must abort loudly.
    Mirrors the fix in litkb/paperclip.py's `_run`, kept standalone here."""

    def test_no_match_return_code_does_not_abort(self):
        completed = subprocess.CompletedProcess(
            args=["paperclip"], returncode=1,
            stdout="No matches for /x/ in s_abc\n", stderr="",
        )
        with patch(
            "litterature_search_from_concept.paperclip_kb.subprocess.run",
            return_value=completed,
        ):
            out = run(["paperclip", "grep", "-e", "x"], False)
        self.assertEqual(out, completed.stdout)

    def test_crash_nonzero_empty_stdout_with_stderr_aborts(self):
        completed = subprocess.CompletedProcess(
            args=["paperclip"], returncode=1, stdout="",
            stderr="Traceback (most recent call last):\nModuleNotFoundError\n",
        )
        with patch(
            "litterature_search_from_concept.paperclip_kb.subprocess.run",
            return_value=completed,
        ):
            with self.assertRaises(SystemExit):
                run(["paperclip", "grep", "-e", "x"], False)

    def test_real_failure_return_code_two_or_more_aborts(self):
        completed = subprocess.CompletedProcess(
            args=["paperclip"], returncode=2,
            stdout="", stderr="bad arguments\n",
        )
        with patch(
            "litterature_search_from_concept.paperclip_kb.subprocess.run",
            return_value=completed,
        ):
            with self.assertRaises(SystemExit):
                run(["paperclip", "grep", "-e", "x"], False)


if __name__ == "__main__":
    unittest.main()
