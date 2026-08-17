from unittest.mock import patch

from litkb import contracts, paperclip, reader

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

# A paper whose payload is not valid JSON at all (e.g. structured-extraction's
# documented fallback_required response for an oversized packet -- see
# `paperclip map --help`). No braces anywhere in the body, so parsing must
# fail rather than silently becoming `{}`.
FAILED_RAW = """Map complete: 1/1 papers
Results ID: m_test_fail

  ✗ A paper that broke schema validation
    PMC3 · 500ms
    fallback_required: schema validation failed after one retry

Tip: These per-paper answers are ready to use -- synthesize them to respond.
[1.0s, saved to m_test_fail]
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


def test_unparseable_payload_is_recorded_as_failed_not_silently_empty():
    """A paper with no valid JSON in its body must not collapse into an
    empty `{}` -- that would be indistinguishable from a validly-empty
    result and would vanish from flagged_for_dig without a trace."""
    records = reader.parse_map_output(FAILED_RAW)
    assert len(records) == 1
    rec = records[0]
    assert rec["doc_id"] == "PMC3"
    assert rec["extraction_failed"] is True
    assert "fallback_required" in rec["raw"]


def test_failed_extraction_is_countable_and_never_flagged_for_dig():
    records = reader.parse_map_output(FAILED_RAW)
    assert reader.failed_extractions(records) == ["PMC3"]
    assert reader.flagged_for_dig(records) == []


def test_map_papers_defaults_to_quick_reader_because_other_workers_are_gated():
    """structured-extraction/exhaustive-extraction/eligibility-screen are
    gated to GXL testers on this account (confirmed live -- see
    task-5-report.md Step 5); quick-reader is the only one that runs. If
    someone restores the gated default, this should fail loudly instead of
    only failing on a live call."""
    captured_args = []

    def mock_run(args):
        captured_args.append(args)
        return "Map complete: 0/0 papers\n"

    with patch("litkb.paperclip._run", side_effect=mock_run):
        paperclip.map_papers("s_abc123", "a query", {"type": "object"})

    assert captured_args
    assert "--worker" in captured_args[0]
    i = captured_args[0].index("--worker")
    assert captured_args[0][i + 1] == "quick-reader"


def _artifact(value="TAGTTCCTTCTTTCAGCAGTTT", verbatim=True,
              set_id="s_abc123", doc_id="PMC2040520"):
    """Built through the REAL builder, never hand-rolled.

    The hand-rolled version of this fixture put `verbatim` at the TOP level,
    but `contracts.draft_artifact` nests it under `provenance`. So
    `confirm_in_source`'s `artifact.get("verbatim")` guard was satisfied in
    every test and `None` on every artifact the pipeline actually produces --
    the fabrication check returned False without ever calling grep, and
    `confirmed_in_source` was False for 56/56 artifacts of a live run while
    the suite stayed green. Constructing the fixture through the real
    function is what stops that drift recurring.
    """
    return contracts.draft_artifact(
        1,
        {"value": value, "molecule": "dna", "name": None, "region": None,
         "where": "methods", "verbatim": verbatim},
        doc_id, set_id,
    )


def test_confirm_in_source_reads_verbatim_from_provenance():
    """Regression for the nesting bug above: a real artifact carries
    `provenance.verbatim`, and confirm_in_source must consult THAT. If it
    reads a top-level key, this artifact looks non-verbatim and grep is
    never called."""
    art = _artifact(verbatim=True)
    assert "verbatim" not in art, "builder shape changed -- retarget this test"
    assert art["provenance"]["verbatim"] is True

    calls = []

    def grep_fn(set_id, patterns):
        calls.append((set_id, patterns))
        return [{"doc_id": art["provenance"]["doc_id"], "text": art["value"]}]

    assert reader.confirm_in_source(art, grep_fn, literal=True) is True
    assert calls, "grep was never called -- the guard short-circuited"


def test_confirm_in_source_matches_map_truncated_doc_id_against_full_grep_id():
    """`paperclip map`'s per-paper timing line abbreviates bioRxiv doc ids --
    it printed `bio_f583cade` where `paperclip grep` returns
    `bio_f583cade7157` for the same paper (confirmed live; PMC ids are
    unaffected). `parse_map_output` records what map printed, so an
    artifact's stored id can be a strict prefix of the id a grep hit
    carries, and an `==` comparison rejected every bioRxiv sequence however
    plainly present it was."""
    art = _artifact(doc_id="bio_f583cade")

    def grep_fn(set_id, patterns):
        return [{"doc_id": "bio_f583cade7157", "text": "snippet"}]

    assert reader.confirm_in_source(art, grep_fn, literal=True) is True


def test_confirm_in_source_does_not_let_a_stub_doc_id_match_everything():
    """Prefix acceptance must stay bounded: a truncated-to-nothing id would
    otherwise be a prefix of every document in the set and confirm all of
    them."""
    art = _artifact(doc_id="bio_")

    def grep_fn(set_id, patterns):
        return [{"doc_id": "bio_f583cade7157", "text": "snippet"}]

    assert reader.confirm_in_source(art, grep_fn, literal=True) is False


def test_confirm_in_source_literal_trusts_doc_id_match_even_if_text_snippet_differs():
    """Regression for the live art_001/PMC2040520 case: `paperclip grep`'s
    `text` field is a truncated display snippet and can legitimately come
    from a different paragraph than the actual hit. With literal=True (the
    caller asserting it used `-F`), a doc_id match alone must confirm --
    requiring the value to also appear in `text` produced false rejections
    of sequences that ARE in the paper."""
    art = _artifact()

    def grep_fn(set_id, patterns):
        return [{"doc_id": "PMC2040520",
                 "text": "To probe for potential influences of the C-terminal extensi..."}]

    assert reader.confirm_in_source(art, grep_fn, literal=True) is True


def test_confirm_in_source_literal_still_fails_on_different_doc():
    art = _artifact(doc_id="PMC2040520")

    def grep_fn(set_id, patterns):
        return [{"doc_id": "PMC9999999", "text": "some unrelated snippet"}]

    assert reader.confirm_in_source(art, grep_fn, literal=True) is False


def test_confirm_in_source_fails_before_grep_when_not_verbatim():
    art = _artifact(verbatim=False)
    calls = []

    def grep_fn(set_id, patterns):
        calls.append((set_id, patterns))
        return [{"doc_id": art["provenance"]["doc_id"], "text": art["value"]}]

    assert reader.confirm_in_source(art, grep_fn, literal=True) is False
    assert calls == []


def test_confirm_in_source_non_literal_keeps_old_substring_behaviour():
    art = _artifact()

    # Same doc_id, but the text snippet does not contain the value -- under
    # the conservative (default, non-literal) fallback this must still fail,
    # since the grep itself cannot be trusted to have matched literally.
    def grep_fn(set_id, patterns):
        return [{"doc_id": "PMC2040520",
                 "text": "To probe for potential influences of the C-terminal extensi..."}]

    assert reader.confirm_in_source(art, grep_fn) is False
    assert reader.confirm_in_source(art, grep_fn, literal=False) is False

    def grep_fn_with_value(set_id, patterns):
        return [{"doc_id": "PMC2040520", "text": f"context {art['value']} context"}]

    assert reader.confirm_in_source(art, grep_fn_with_value, literal=False) is True


def test_map_papers_raises_when_output_has_no_map_header():
    """The worker-gating error also exits 1 with an empty stdout (its
    message is on stderr) -- see task-5-report.md Fix round 2 for the
    captured evidence. Without this check that looks exactly like a
    legitimate empty sweep to any caller of map_papers."""
    def mock_run(args):
        return "[error] Parallel map workers are currently limited to GXL testers.\n"

    with patch("litkb.paperclip._run", side_effect=mock_run):
        try:
            paperclip.map_papers("s_abc123", "a query", {"type": "object"},
                                  worker="structured-extraction")
        except paperclip.PaperclipError as e:
            assert "structured-extraction" in str(e)
        else:
            raise AssertionError(
                "expected PaperclipError when map output has no header")
