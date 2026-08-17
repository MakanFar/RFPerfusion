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
