from litkb import contracts, reader


def _art(value, verbatim=True, doc_id="PMC1", set_id="s_1"):
    """Real builder, not a hand-rolled dict.

    These fixtures used to place `verbatim` at the top level while
    contracts.draft_artifact nests it under `provenance`, so every test here
    exercised a shape the pipeline never emits and the fabrication guard
    passed its tests while silently returning False on all real input.
    """
    return contracts.draft_artifact(
        1,
        {"value": value, "molecule": "protein", "name": None, "region": None,
         "where": "methods", "verbatim": verbatim},
        doc_id, set_id,
    )


REAL = _art("MKVAALLPQR")
FABRICATED = _art("QQQWWWEEEE")


def grep_fn(set_id, patterns):
    corpus = "the construct MKVAALLPQR was expressed"
    return [{"doc_id": "PMC1", "text": corpus}] if patterns[0] in corpus else []


def test_dig_schema_requires_the_verbatim_flag():
    item = reader.DIG_SCHEMA["properties"]["sequences"]["items"]
    assert "verbatim" in item["required"]


def test_sequence_present_in_source_is_confirmed():
    assert reader.confirm_in_source(REAL, grep_fn) is True


def test_sequence_absent_from_source_is_not_confirmed():
    assert reader.confirm_in_source(FABRICATED, grep_fn) is False


def test_non_verbatim_sequence_is_never_confirmed():
    claimed = _art("MKVAALLPQR", verbatim=False)
    assert reader.confirm_in_source(claimed, grep_fn) is False


def test_sequence_in_different_document_is_not_confirmed():
    """Same-document filter is critical: a sequence found in PMC2 must not
    confirm an artifact claiming PMC1, even if the sequence text matches."""
    def grep_fn_different_doc(set_id, patterns):
        corpus = "the construct MKVAALLPQR was expressed"
        # Return a hit, but for PMC2 not PMC1
        return [{"doc_id": "PMC2", "text": corpus}] if patterns[0] in corpus else []

    assert reader.confirm_in_source(REAL, grep_fn_different_doc) is False


def test_sequence_not_actually_in_hit_text_is_not_confirmed():
    """Belt-and-braces substring guard: even if grep returns a hit with the
    correct doc_id, if the actual sequence value is not in the text, reject it."""
    def grep_fn_no_substring(set_id, patterns):
        # Return a hit with correct doc_id but text that doesn't contain the value
        return [{"doc_id": "PMC1", "text": "some other protein sequence was used"}]

    assert reader.confirm_in_source(REAL, grep_fn_no_substring) is False
