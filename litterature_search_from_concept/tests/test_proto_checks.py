from litkb import proto

ESM2 = {"key": "esm2-score", "input_kind": "sequence", "molecules": ["protein"],
        "alphabet": proto.PROTEIN_ALPHABET, "max_length": 1022}
NOCAP = {"key": "mystery", "input_kind": "sequence", "molecules": ["protein"],
         "alphabet": proto.PROTEIN_ALPHABET, "max_length": None}
MPNN = {"key": "proteinmpnn-score", "input_kind": "structure",
        "molecules": ["protein"], "alphabet": None, "max_length": None}

PROTEIN = {"kind": "sequence", "molecule": "protein", "value": "MKVAAL", "length": 6}
DNA = {"kind": "sequence", "molecule": "dna", "value": "ATGGCC", "length": 6}
LONG = {"kind": "sequence", "molecule": "protein", "value": "M" * 2000, "length": 2000}
BAD_CHARS = {"kind": "sequence", "molecule": "protein", "value": "MKVJJZ", "length": 6}


def test_valid_protein_passes_every_check():
    checks = proto.check(PROTEIN, ESM2)
    assert all(v.startswith("pass") for v in checks.values())


def test_dna_fails_molecule_check():
    assert proto.check(DNA, ESM2)["molecule"].startswith("fail")


def test_over_length_fails():
    assert proto.check(LONG, ESM2)["max_length"].startswith("fail")


def test_non_alphabet_characters_fail():
    assert proto.check(BAD_CHARS, ESM2)["alphabet"].startswith("fail")


def test_missing_cap_is_unknown_not_pass():
    assert proto.check(PROTEIN, NOCAP)["max_length"] == "unknown"


def test_structure_tool_rejects_bare_sequence():
    assert proto.check(PROTEIN, MPNN)["input_kind"].startswith("fail")


def test_bind_marks_runnable_when_a_tool_fully_passes():
    result = proto.bind_artifact(PROTEIN, {"tools": [ESM2, MPNN]})
    assert result["status"] == "runnable"
    assert result["tools"][0]["key"] == "esm2-score"
    assert result["rejected_by"][0]["key"] == "proteinmpnn-score"


def test_bind_is_unverified_when_only_unknowns_stand_between_it_and_pass():
    result = proto.bind_artifact(PROTEIN, {"tools": [NOCAP]})
    assert result["status"] == "unverified"


def test_bind_rejects_when_every_tool_fails():
    result = proto.bind_artifact(DNA, {"tools": [ESM2]})
    assert result["status"] == "rejected"
    assert result["tools"] == []


def test_bind_unsupported_kind_returns_distinct_status():
    mutation = {"kind": "mutation", "molecule": "protein", "value": "A123B", "length": 5}
    result = proto.bind_artifact(mutation, {"tools": [ESM2]})
    assert result["status"] == "unsupported_kind"
    assert result["tools"] == []
    assert result["rejected_by"] == []
    assert "mutation" in result["reason"]


def test_input_kind_failure_names_artifact_kind():
    structure_artifact = {"kind": "structure_id", "molecule": "protein", "value": "1ABC", "length": 4}
    checks = proto.check(structure_artifact, MPNN)
    assert "structure_id" in checks["input_kind"]
