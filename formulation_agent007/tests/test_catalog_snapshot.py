import json
from pathlib import Path

import pytest

from formulation_agent007 import catalog

SNAPSHOT = Path(__file__).resolve().parents[2] / "registry" / "proto_metrics.json"


def test_tool_keys_come_from_the_snapshot():
    snap = json.loads(SNAPSHOT.read_text())
    assert catalog.PROTO_TOOL_KEYS == frozenset(snap["tool_keys"])


def test_real_catalogue_keys_are_accepted():
    assert catalog.unknown_tools(["esmfold-prediction", "boltz2-prediction"]) == []


def test_bare_model_names_are_now_rejected():
    """A model name alone is not a proto-tools key; 51 of the old 59 were."""
    assert catalog.unknown_tools(["esmfold"]) == ["esmfold"]


def test_metrics_no_tool_emits_are_gone():
    for absent in ("mean_plddt", "dg_fold", "population_fraction", "tm_score"):
        assert absent not in catalog.PROTO_METRICS


def test_real_metrics_are_present():
    for present in ("avg_plddt", "iptm", "perplexity"):
        assert present in catalog.PROTO_METRICS


def test_direction_is_available_per_metric():
    assert catalog.METRIC_DIRECTION["avg_pae"] == "lower"
    assert catalog.METRIC_DIRECTION["avg_plddt"] == "higher"


def test_cost_tier_resolves_by_model_family():
    # Cost is a curated judgement the registry cannot supply, so the tiers
    # stay hand-maintained -- but keyed by family so real keys resolve.
    assert catalog.cost_tier("esmfold-prediction") == "cheap"
    assert catalog.cost_tier("boltz2-prediction") == "moderate"
    assert catalog.cost_tier("bioemu-sampling") == "expensive"


def test_unknown_family_is_treated_as_costly():
    assert catalog.cost_tier("never-heard-of-it") == "expensive"


@pytest.mark.slow
def test_snapshot_matches_the_live_catalogue():
    """Marked so it never runs offline or in CI. Run by hand after a
    proto-tools upgrade: `pytest -m slow`."""
    import subprocess
    out = subprocess.run(
        ["uv", "run", "--project", "../proto", "proto-tools", "list", "--json"],
        capture_output=True, text=True, check=True).stdout
    live = {t["key"] for t in json.loads(out[out.index("["):out.rindex("]") + 1])}
    assert live == set(json.loads(SNAPSHOT.read_text())["tool_keys"]), \
        "registry/proto_metrics.json is stale; re-run `litkb proto-sync --snapshot`"
