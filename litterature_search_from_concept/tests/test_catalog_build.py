import pytest

from litkb import proto

TOOLS = [
    {"key": "esmfold-prediction", "category": "structure_prediction", "uses_gpu": True},
    {"key": "uniprot-fetch", "category": "database_retrieval", "uses_gpu": False},
]

SCHEMAS = {
    "esmfold-prediction": {
        "inputs": {
            "$defs": {"Chain": {"properties": {
                "entity_type": {"description": "'protein', 'dna', 'rna', or 'ligand'"}}}},
            "properties": {"complexes": {"type": "array"}},
        }
    },
    "uniprot-fetch": {"inputs": {"$defs": {}, "properties": {}}},
}

OUTPUTS = {
    "esmfold-prediction": (
        "Metrics (per structures item):\n"
        "  avg_plddt                 float, range [0.0, 1.0], always, better=higher  *primary\n"
        "  bogus row with no range\n"
    ),
    "uniprot-fetch": "Output: UniProtFetchOutput\n",
}

DOCS = {"esmfold-prediction": "must not exceed 2,400", "uniprot-fetch": ""}


def _build():
    return proto.build_catalog(
        TOOLS,
        doc_fetcher=lambda k: DOCS[k],
        schema_fetcher=lambda k: SCHEMAS[k],
        output_fetcher=lambda k: OUTPUTS[k],
    )


def test_registry_declares_schema_version_3():
    assert _build()["schema_version"] == 3


def test_measures_are_attached_per_tool():
    tools = {t["key"]: t for t in _build()["tools"]}
    assert tools["esmfold-prediction"]["measures"][0]["metric"] == "avg_plddt"


def test_tool_measuring_nothing_gets_an_empty_list():
    tools = {t["key"]: t for t in _build()["tools"]}
    assert tools["uniprot-fetch"]["measures"] == []


def test_unparsed_rows_are_surfaced_with_their_tool():
    failures = _build()["parse_failures"]
    assert failures == [{"key": "esmfold-prediction", "line": "bogus row with no range"}]


def test_status_stays_needs_calibration():
    # Capability is not accuracy. Framework section 6 is unaffected by this work.
    assert all(t["status"] == "needs_calibration" for t in _build()["tools"])


def test_constraint_source_is_a_list():
    tools = {t["key"]: t for t in _build()["tools"]}
    assert tools["esmfold-prediction"]["constraint_source"] == ["schema", "docstring"]


def test_load_catalog_rejects_a_version_1_registry(tmp_path):
    import json
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"tools": [], "n_tools": 0}))
    with pytest.raises(ValueError, match="schema_version"):
        proto.load_catalog(old)


def _raise(key):
    raise RuntimeError(f"fetch failed for {key}")


def test_raising_fetcher_degrades_one_tool_to_unknown_without_aborting():
    # A prefetch that failed for one tool (proto-sync's own concurrent
    # fetchers guard against this before build_catalog ever sees it, but
    # build_catalog must not depend on that guard) must leave that tool
    # with unknown -- never fabricated -- constraints and no measures,
    # and must not stop the rest of the catalogue from being built.
    cat = proto.build_catalog(
        TOOLS,
        doc_fetcher=_raise,
        schema_fetcher=_raise,
        output_fetcher=_raise,
    )
    assert cat["n_tools"] == len(TOOLS)
    for tool in cat["tools"]:
        assert tool["measures"] == []
        assert tool["input_kind"] is None
        assert tool["molecules"] is None
        assert tool["alphabet"] is None
        assert tool["max_length"] is None
        assert tool["constraint_source"] == []
        assert tool["status"] == "needs_calibration"
    assert cat["parse_failures"] == []


def test_raising_fetcher_for_one_tool_does_not_affect_the_other():
    def doc_fetcher(key):
        if key == "esmfold-prediction":
            raise RuntimeError("boom")
        return DOCS[key]

    cat = proto.build_catalog(
        TOOLS,
        doc_fetcher=doc_fetcher,
        schema_fetcher=lambda k: SCHEMAS[k],
        output_fetcher=lambda k: OUTPUTS[k],
    )
    tools = {t["key"]: t for t in cat["tools"]}
    # esmfold's doc fetch failed, but its schema still answers molecules/input_kind.
    assert tools["esmfold-prediction"]["molecules"] == ["dna", "ligand", "protein", "rna"]
    # uniprot-fetch's fetchers never raised, so it is unaffected.
    assert tools["uniprot-fetch"]["measures"] == []
