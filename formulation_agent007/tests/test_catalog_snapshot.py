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
    assert catalog.cost_tier("bioemu-sample") == "expensive"


def test_unknown_family_is_treated_as_costly():
    assert catalog.cost_tier("never-heard-of-it") == "expensive"


def test_interface_metrics_catches_qualified_iptm_variants():
    # These are real boltz2-prediction / germinal-design metrics that a
    # prefix-only heuristic (startswith "iptm") used to miss because the
    # qualifier comes first: protein_iptm, ligand_iptm, pair_chains_iptm,
    # chains_ptm, i_ptm, i_pae.
    for present in (
        "protein_iptm", "ligand_iptm", "pair_chains_iptm", "chains_ptm",
        "i_ptm", "i_pae",
    ):
        assert present in catalog.INTERFACE_METRICS, present


def test_metric_digest_only_names_real_metrics():
    digest = catalog.metric_digest()
    # crude tokenizer: comma/space separated, strip the "better=..." labels
    for line in digest.splitlines():
        _, _, rest = line.partition(":")
        for token in rest.split(","):
            name = token.strip()
            if name:
                assert name in catalog.PROTO_METRICS, name


def test_metric_digest_is_grouped_by_direction():
    digest = catalog.metric_digest()
    assert "better=higher" in digest
    assert "better=lower" in digest


def test_metric_digest_does_not_dump_the_whole_snapshot():
    digest = catalog.metric_digest()
    named = sum(len(line.partition(":")[2].split(",")) for line in digest.splitlines())
    assert named < len(catalog.PROTO_METRICS)


def test_metric_digest_prefers_primary_and_shared_metrics():
    digest = catalog.metric_digest()
    for present in ("avg_plddt", "iptm", "avg_pae", "perplexity", "confidence_score"):
        assert present in digest


def test_interface_metrics_does_not_catch_single_chain_confidence():
    # chain_ptm/chain_plddt are per-chain fold-confidence values, not
    # interface-specific -- the "chains_" (plural) / "i_" heuristic must not
    # widen to swallow the singular "chain_" family or the bare metrics.
    for absent in ("ptm", "plddt", "chain_ptm", "chain_plddt", "pae"):
        assert absent not in catalog.INTERFACE_METRICS, absent


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
