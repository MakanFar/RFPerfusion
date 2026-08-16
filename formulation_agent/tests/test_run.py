from __future__ import annotations

from argparse import Namespace

import pytest
from formulation_agent.run import build_parser, read_context, read_question


def test_inline_question_is_trimmed():
    args = Namespace(
        question="  How should this protein respond?  ", question_file=None
    )
    assert read_question(args) == "How should this protein respond?"


def test_empty_question_is_rejected():
    args = Namespace(question="  ", question_file=None)
    with pytest.raises(ValueError, match="empty"):
        read_question(args)


def test_context_files_are_labelled(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("candidate mechanism", encoding="utf-8")
    second.write_text("supporting note", encoding="utf-8")
    context = read_context([first, second])
    assert f"SOURCE: {first}" in context
    assert f"SOURCE: {second}" in context
    assert "candidate mechanism" in context


def test_question_source_is_required():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--output-dir", "out"])
