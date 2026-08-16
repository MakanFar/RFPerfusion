from litkb import reader

REAL = {"value": "MKVAALLPQR", "provenance": {"doc_id": "PMC1", "set_id": "s_1"},
        "verbatim": True}
FABRICATED = {"value": "QQQWWWEEEE", "provenance": {"doc_id": "PMC1", "set_id": "s_1"},
              "verbatim": True}


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
    claimed = dict(REAL, verbatim=False)
    assert reader.confirm_in_source(claimed, grep_fn) is False
