from unittest.mock import patch

from litkb import paperclip, reader

# Real `paperclip map` stdout is human-formatted text, not a JSON envelope
# (confirmed live against PMC6200754 -- see reader.py comment above
# parse_map_output and task-5-report.md Step 5 for the raw bytes). This
# fixture reproduces that exact block format for two papers: PMC1's block
# is the literal confirmed shape with a stand-in JSON payload; PMC2's block
# is modeled on it by analogy to exercise the "no sequence claimed" path.
RAW = """Map complete: 2/2 papers
Results ID: m_test0000

  ✓ An open quantum system approach to the radical pair mechanism
    PMC1 · 2594ms
    {"mechanisms": [{"chain": "RF -> heating", "claim": "c", "measurable_properties": ["fold_confidence"]}], "has_sequence": true, "sequence_location": "supplementary", "named_proteins": [{"name": "AsLOV2", "accession": "Q9C9W9"}]}

  ✓ Some other paper with no sequence
    PMC2 · 1000ms
    {"mechanisms": [], "has_sequence": false, "sequence_location": "none", "named_proteins": []}

Tip: These per-paper answers are ready to use -- synthesize them to respond.
[4.0s, saved to m_test0000]
"""


def test_screen_schema_forbids_extra_keys():
    assert reader.SCREEN_SCHEMA["additionalProperties"] is False


def test_screen_schema_requires_the_sequence_flag():
    assert "has_sequence" in reader.SCREEN_SCHEMA["required"]


def test_parse_map_output_returns_one_record_per_paper():
    assert len(reader.parse_map_output(RAW)) == 2


def test_parse_map_output_keeps_doc_id_alongside_output():
    first = reader.parse_map_output(RAW)[0]
    assert first["doc_id"] == "PMC1"
    assert first["has_sequence"] is True


def test_flagged_papers_are_those_claiming_a_sequence():
    flagged = reader.flagged_for_dig(reader.parse_map_output(RAW))
    assert flagged == ["PMC1"]


def test_map_papers_defaults_to_quick_reader_because_other_workers_are_gated():
    """structured-extraction/exhaustive-extraction/eligibility-screen are
    gated to GXL testers on this account (confirmed live -- see
    task-5-report.md Step 5); quick-reader is the only one that runs. If
    someone restores the gated default, this should fail loudly instead of
    only failing on a live call."""
    captured_args = []

    def mock_run(args):
        captured_args.append(args)
        return ""

    with patch("litkb.paperclip._run", side_effect=mock_run):
        paperclip.map_papers("s_abc123", "a query", {"type": "object"})

    assert captured_args
    assert "--worker" in captured_args[0]
    i = captured_args[0].index("--worker")
    assert captured_args[0][i + 1] == "quick-reader"
