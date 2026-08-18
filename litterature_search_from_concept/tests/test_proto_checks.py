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

# bind_artifact applies artifact-quality gates (see MIN_DESIGN_LENGTH) before
# it consults any tool, so its tests need candidates that clear them. PROTEIN
# and DNA stay short on purpose: check() is per-tool and length never gated it.
BINDABLE_PROTEIN = {"kind": "sequence", "molecule": "protein",
                    "value": "MKVAALLPQRSTGYWFNDEC", "length": 20}
BINDABLE_DNA = {"kind": "sequence", "molecule": "dna",
                "value": "ATGGCCATTGTAATGGGCCG", "length": 20}


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
    result = proto.bind_artifact(BINDABLE_PROTEIN, {"tools": [ESM2, MPNN]})
    assert result["status"] == "runnable"
    assert result["tools"][0]["key"] == "esm2-score"
    assert result["rejected_by"][0]["key"] == "proteinmpnn-score"


def test_bind_is_unverified_when_only_unknowns_stand_between_it_and_pass():
    result = proto.bind_artifact(BINDABLE_PROTEIN, {"tools": [NOCAP]})
    assert result["status"] == "unverified"


def test_bind_rejects_when_every_tool_fails():
    result = proto.bind_artifact(BINDABLE_DNA, {"tools": [ESM2]})
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


# --- artifact-quality gates -------------------------------------------------
# These are tool-INDEPENDENT: a 5-residue motif carrying an unresolved-residue
# placeholder is not a design candidate whichever tool you point at it. They
# therefore live in `bind_artifact`, ahead of the per-tool loop, alongside the
# existing `unsupported_kind` gate -- NOT in `check()`, whose every verdict is
# relative to one tool's declared constraints.

DESIGNABLE = {"kind": "sequence", "molecule": "protein",
              "value": "MKVAALLPQRSTGYWFNDECIK", "length": 22}


def test_sequence_with_an_ambiguity_code_is_not_runnable():
    """Found live: `VPGXG` (the elastin-like-polypeptide repeat) bound to
    esmfold-prediction with all four checks `pass`, because X is a legal
    IUPAC character and therefore a legal member of PROTEIN_ALPHABET. But X
    means "this position is unresolved" -- the sequence is not fully
    specified, so it is not a candidate."""
    art = {"kind": "sequence", "molecule": "protein",
           "value": "MKVAALLPQRSTGYWFNDECIX", "length": 22}
    result = proto.bind_artifact(art, {"tools": [ESM2]})

    assert result["status"] == "unspecified_sequence"
    assert result["tools"] == []
    assert "X" in result["reason"]


def test_nucleotide_ambiguity_code_is_caught_too():
    """N is the nucleotide equivalent of X and is in NUCLEOTIDE_ALPHABET."""
    art = {"kind": "sequence", "molecule": "dna",
           "value": "ATGGCCATTGTAATGGGCCN", "length": 20}
    result = proto.bind_artifact(art, {"tools": [ESM2]})

    assert result["status"] == "unspecified_sequence"
    assert "N" in result["reason"]


def test_sequence_shorter_than_the_minimum_is_not_runnable():
    """`VPGXG` was 5 residues. ESMFold will technically accept a 5-mer, so no
    per-tool check rejects it -- but a repeat motif is not a design
    candidate."""
    art = {"kind": "sequence", "molecule": "protein", "value": "VPGVG", "length": 5}
    result = proto.bind_artifact(art, {"tools": [ESM2]})

    assert result["status"] == "below_min_length"
    assert result["tools"] == []
    assert str(proto.MIN_DESIGN_LENGTH) in result["reason"]


def test_a_sequence_at_exactly_the_minimum_still_binds():
    """The boundary is inclusive -- 20 residues is designable."""
    art = {"kind": "sequence", "molecule": "protein",
           "value": "MKVAALLPQRSTGYWFNDEC", "length": 20}
    result = proto.bind_artifact(art, {"tools": [ESM2]})

    assert result["status"] == "runnable"


def test_ambiguity_is_reported_before_length():
    """A short sequence that is ALSO unspecified reports the more fundamental
    problem: we do not know what it is, never mind how long."""
    art = {"kind": "sequence", "molecule": "protein", "value": "VPGXG", "length": 5}
    assert proto.bind_artifact(art, {"tools": [ESM2]})["status"] == "unspecified_sequence"


def test_designable_sequence_is_unaffected_by_either_gate():
    result = proto.bind_artifact(DESIGNABLE, {"tools": [ESM2]})
    assert result["status"] == "runnable"
