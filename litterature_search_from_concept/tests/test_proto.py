from litkb import proto

ESMFOLD_DOC = """Input: ESMFoldInput
Attributes:
    complexes (list[Complex]): The linked length actually
        folded must not exceed 2,400.
Note:
    ESMFold only supports protein sequences (amino acids). DNA, RNA, ligands,
    and glycans are not supported.

  complexes                 list[Complex]                   (required)
"""

ESM2_DOC = """Input: ESM2ScoringInput
Attributes:
    sequences (list[str]): Protein sequence(s) to score. Each must be <= 1022
        residues (ESM-2's positional-encoding cap).

  sequences                 list[str]                       (required)
"""

MPNN_DOC = """Input: InverseFoldingInput
Attributes:
    inputs (list[InverseFoldingStructureInput]): Per-structure inputs.

  sequence_structure_pairs  list[SequenceStructurePair]     (required)
"""


def test_parses_length_cap_with_thousands_separator():
    assert proto.parse_input_doc(ESMFOLD_DOC)["max_length"] == 2400


def test_parses_length_cap_with_comparison_operator():
    assert proto.parse_input_doc(ESM2_DOC)["max_length"] == 1022


def test_protein_only_tool_lists_one_molecule():
    assert proto.parse_input_doc(ESMFOLD_DOC)["molecules"] == ["protein"]


def test_sequence_input_kind_detected():
    assert proto.parse_input_doc(ESM2_DOC)["input_kind"] == "sequence"


def test_structure_input_kind_detected():
    assert proto.parse_input_doc(MPNN_DOC)["input_kind"] == "structure"


def test_unparseable_length_is_none_not_zero():
    assert proto.parse_input_doc(MPNN_DOC)["max_length"] is None


def test_build_catalog_carries_key_and_category():
    tools = [{"key": "esm2-score", "category": "sequence_scoring", "uses_gpu": True}]
    cat = proto.build_catalog(
        tools,
        doc_fetcher=lambda key: ESM2_DOC,
        schema_fetcher=lambda key: {},
        output_fetcher=lambda key: "",
    )
    entry = cat["tools"][0]
    assert entry["key"] == "esm2-score"
    assert entry["category"] == "sequence_scoring"
    assert entry["max_length"] == 1022
    assert entry["status"] == "needs_calibration"
    assert entry["measures"] == []
