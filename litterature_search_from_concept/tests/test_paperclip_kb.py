from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from litterature_search_from_concept.paperclip_kb import host_env, validate_plan


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


if __name__ == "__main__":
    unittest.main()
