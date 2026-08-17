"""_snapshot_from_catalog builds the formulation_agent007 vocabulary
snapshot. It is pure (no network, no filesystem) precisely so it can be
tested here without a live proto-tools project -- `cmd_proto_sync` itself
needs one and is not otherwise unit tested.
"""

from litkb.cli import _snapshot_from_catalog

CATALOG = {
    "tools": [
        {
            "key": "boltz2-prediction",
            "category": "structure_prediction",
            "measures": [
                {"metric": "iptm", "better": "higher", "primary": True},
                {"metric": "avg_pae", "better": "lower", "primary": False},
            ],
        },
        {
            "key": "alphafold3-prediction",
            "category": "structure_prediction",
            "measures": [
                {"metric": "iptm", "better": "higher", "primary": False},
            ],
        },
        {
            "key": "uniprot-fetch",
            "category": "database_retrieval",
            "measures": [],
        },
    ],
}


def test_metric_is_primary_if_any_emitting_tool_flags_it_primary():
    snapshot = _snapshot_from_catalog(CATALOG)
    assert snapshot["metrics"]["iptm"]["primary"] is True


def test_metric_is_not_primary_if_no_emitting_tool_flags_it():
    snapshot = _snapshot_from_catalog(CATALOG)
    assert snapshot["metrics"]["avg_pae"]["primary"] is False


def test_primary_tools_names_only_the_tools_that_flagged_it():
    snapshot = _snapshot_from_catalog(CATALOG)
    assert snapshot["metrics"]["iptm"]["primary_tools"] == ["boltz2-prediction"]


def test_better_and_tools_fields_are_preserved():
    snapshot = _snapshot_from_catalog(CATALOG)
    assert snapshot["metrics"]["iptm"]["better"] == "higher"
    assert snapshot["metrics"]["iptm"]["tools"] == [
        "alphafold3-prediction", "boltz2-prediction",
    ]


def test_tool_keys_and_categories_are_unaffected():
    snapshot = _snapshot_from_catalog(CATALOG)
    assert snapshot["tool_keys"] == [
        "alphafold3-prediction", "boltz2-prediction", "uniprot-fetch",
    ]
    assert snapshot["categories"]["structure_prediction"] == [
        "alphafold3-prediction", "boltz2-prediction",
    ]


def test_a_tool_with_no_measures_contributes_no_metrics():
    snapshot = _snapshot_from_catalog(CATALOG)
    assert set(snapshot["metrics"]) == {"iptm", "avg_pae"}


DISAGREEING_CATALOG = {
    "tools": [
        {
            "key": "some-design-tool",
            "category": "structure_design",
            "measures": [
                {"metric": "interface_hydrophobicity", "better": "context-dependent",
                 "primary": False},
            ],
        },
        {
            "key": "germinal-design",
            "category": "structure_design",
            "measures": [
                {"metric": "interface_hydrophobicity", "better": "higher",
                 "primary": False},
            ],
        },
    ],
}


def test_better_resolves_to_context_dependent_when_tools_disagree():
    """Real-world case: `interface_hydrophobicity` is `context-dependent`
    per three tools and `higher` per `germinal-design`. The resolution must
    be deliberate, not an accident of catalog iteration order -- so it must
    come out `context-dependent` regardless of which tool is listed first."""
    snapshot = _snapshot_from_catalog(DISAGREEING_CATALOG)
    assert snapshot["metrics"]["interface_hydrophobicity"]["better"] == "context-dependent"

    reordered = {"tools": list(reversed(DISAGREEING_CATALOG["tools"]))}
    snapshot_reordered = _snapshot_from_catalog(reordered)
    assert snapshot_reordered["metrics"]["interface_hydrophobicity"]["better"] == \
        "context-dependent"
