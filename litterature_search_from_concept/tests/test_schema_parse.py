from litkb import proto

# Shape captured from `proto-tools schema esmfold-prediction`.
ESMFOLD_SCHEMA = {
    "inputs": {
        "$defs": {
            "Chain": {
                "properties": {
                    "sequence": {"type": "string",
                                 "description": "Sequence of the chain"},
                    "entity_type": {
                        "description": "Entity type: 'protein', 'dna', 'rna', "
                                       "or 'ligand'. Auto-inferred if None.",
                    },
                }
            }
        },
        "properties": {"complexes": {"type": "array"}},
    }
}

SEQ_ONLY_SCHEMA = {
    "inputs": {
        "$defs": {},
        "properties": {
            "sequences": {"type": "array", "items": {"type": "string",
                                                     "maxLength": 1022}}
        },
    }
}

OPAQUE_SCHEMA = {"inputs": {"$defs": {}, "properties": {}}}


def test_entity_type_description_yields_molecules():
    got = proto.parse_input_schema(ESMFOLD_SCHEMA)
    assert got["molecules"] == ["dna", "ligand", "protein", "rna"]


def test_complexes_field_is_a_complex_input():
    assert proto.parse_input_schema(ESMFOLD_SCHEMA)["input_kind"] == "complex"


def test_sequences_field_is_a_sequence_input():
    assert proto.parse_input_schema(SEQ_ONLY_SCHEMA)["input_kind"] == "sequence"


def test_declared_maxlength_is_used():
    assert proto.parse_input_schema(SEQ_ONLY_SCHEMA)["max_length"] == 1022


def test_opaque_schema_yields_all_unknown():
    got = proto.parse_input_schema(OPAQUE_SCHEMA)
    assert got == {"input_kind": None, "molecules": None,
                   "alphabet": None, "max_length": None}


def test_prose_supplies_a_cap_the_schema_never_declares():
    # ESMFold's 2,400 cap lives only in the docstring Note, never in the schema.
    doc = proto.parse_input_doc(
        "Attributes:\n    complexes: must not exceed 2,400.\n"
    )
    merged = proto.merge_constraints(proto.parse_input_schema(ESMFOLD_SCHEMA), doc)
    assert merged["max_length"] == 2400
    assert merged["constraint_source"] == ["schema", "docstring"]


def test_schema_wins_over_prose_when_both_supply_a_field():
    doc = proto.parse_input_doc("Note:\n    only supports protein sequences\n")
    merged = proto.merge_constraints(proto.parse_input_schema(SEQ_ONLY_SCHEMA), doc)
    assert merged["max_length"] == 1022


def test_source_records_docstring_only_when_prose_contributed():
    merged = proto.merge_constraints(
        proto.parse_input_schema(SEQ_ONLY_SCHEMA),
        {"input_kind": None, "molecules": None, "alphabet": None,
         "max_length": None, "constraint_source": "docstring"},
    )
    assert merged["constraint_source"] == ["schema"]


def test_maxlength_ignores_irrelevant_field_before_sequence_field():
    # A schema with name field (maxLength=64) before sequences field (maxLength=1022)
    # should use the sequences cap, not the name cap
    schema = {
        "inputs": {
            "$defs": {},
            "properties": {
                "name": {"type": "string", "maxLength": 64},
                "sequences": {"type": "array", "items": {"type": "string",
                                                         "maxLength": 1022}}
            },
        }
    }
    assert proto.parse_input_schema(schema)["max_length"] == 1022


def test_molecules_are_intersected_not_schema_first():
    # entity_type is a shared, generic $defs description reused by every
    # Complex-accepting tool -- it always lists all four kinds. The prose
    # Note is tool-specific and narrower here, so the merge must shrink to
    # the prose's answer rather than keep the schema's broader one.
    doc = proto.parse_input_doc("Note:\n    only supports protein sequences\n")
    merged = proto.merge_constraints(proto.parse_input_schema(ESMFOLD_SCHEMA), doc)
    assert merged["molecules"] == ["protein"]
    assert merged["alphabet"] == proto.PROTEIN_ALPHABET
    assert merged["constraint_source"] == ["schema", "docstring"]


def test_molecules_from_schema_only_when_prose_is_silent():
    doc = proto.parse_input_doc("Attributes:\n    complexes: no cap here.\n")
    merged = proto.merge_constraints(proto.parse_input_schema(ESMFOLD_SCHEMA), doc)
    assert merged["molecules"] == ["dna", "ligand", "protein", "rna"]


def test_molecules_from_prose_only_when_schema_is_silent():
    doc = proto.parse_input_doc("Note:\n    only supports protein sequences\n")
    merged = proto.merge_constraints(proto.parse_input_schema(OPAQUE_SCHEMA), doc)
    assert merged["molecules"] == ["protein"]


def test_molecules_intersection_yields_nucleotide_alphabet():
    doc = proto.parse_input_doc("Note:\n    entity types: dna, rna\n")
    merged = proto.merge_constraints(proto.parse_input_schema(ESMFOLD_SCHEMA), doc)
    assert merged["molecules"] == ["dna", "rna"]
    assert merged["alphabet"] == proto.NUCLEOTIDE_ALPHABET


def test_disjoint_molecules_resolve_to_the_shorter_list_not_the_union():
    # A real contradiction (no overlap at all) must never resolve to the
    # union -- that would be strictly more permissive than either source,
    # the exact fail-open shape this merge exists to refuse.
    schema = proto.parse_input_schema(
        {"inputs": {"$defs": {"C": {"properties": {
            "entity_type": {"description": "'dna'"}}}}, "properties": {}}}
    )
    doc = proto.parse_input_doc("Note:\n    only supports protein sequences\n")
    merged = proto.merge_constraints(schema, doc)
    assert merged["molecules"] in (["dna"], ["protein"])
    assert merged["molecules"] != sorted({"dna", "protein"})
    assert len(merged["molecules"]) == 1


def test_maxlength_on_irrelevant_field_only_yields_none():
    # A schema with only irrelevant fields that have maxLength should leave max_length as None
    schema = {
        "inputs": {
            "$defs": {},
            "properties": {
                "name": {"type": "string", "maxLength": 64},
                "id": {"type": "string", "maxLength": 32}
            },
        }
    }
    assert proto.parse_input_schema(schema)["max_length"] is None


def test_entity_type_continues_scanning_if_first_field_uninformative():
    # A schema with two entity_type fields, first one uninformative, second one informative
    schema = {
        "inputs": {
            "$defs": {
                "Component1": {
                    "properties": {
                        "entity_type": {"description": "Type information"},
                    }
                },
                "Component2": {
                    "properties": {
                        "entity_type": {"description": "Entity type: 'protein' or 'rna'"},
                    }
                }
            },
            "properties": {},
        }
    }
    assert proto.parse_input_schema(schema)["molecules"] == ["protein", "rna"]
