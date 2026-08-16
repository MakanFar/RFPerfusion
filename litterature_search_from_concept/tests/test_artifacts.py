from litkb import contracts

RECORD = {"value": "MKVAAL", "molecule": "protein", "name": "AsLOV2",
          "region": [404, 546], "where": "Table S1", "verbatim": True}


def test_draft_artifact_has_a_stable_id():
    a = contracts.draft_artifact(7, RECORD, "PMC1", "s_1")
    assert a["id"] == "art_007"


def test_region_makes_it_a_subsequence():
    assert contracts.draft_artifact(1, RECORD, "PMC1", "s_1")["kind"] == "subsequence"


def test_absent_region_makes_it_a_sequence():
    record = dict(RECORD, region=None)
    assert contracts.draft_artifact(1, record, "PMC1", "s_1")["kind"] == "sequence"


def test_length_is_computed_from_the_value():
    assert contracts.draft_artifact(1, RECORD, "PMC1", "s_1")["length"] == 6


def test_confirmation_starts_false_until_checked():
    a = contracts.draft_artifact(1, RECORD, "PMC1", "s_1")
    assert a["provenance"]["confirmed_in_source"] is False
