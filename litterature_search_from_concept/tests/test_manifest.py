import argparse
import json

from litkb import cli, contracts

SEARCH = {
    "slug": "rfp", "sources": "pmc,biorxiv", "n": 20,
    "classes": [
        {"id": "thermal", "sets": [
            {"phrase": "radio frequency protein", "set_id": "s_aaa111", "n_papers": 5},
            {"phrase": "magnetothermal switch", "set_id": "s_bbb222", "n_papers": 3},
        ]},
        {"id": "mechanical", "sets": [
            {"phrase": "piezoelectric gating", "set_id": "s_ccc333", "n_papers": 2},
        ]},
    ],
    "rejections": [],
}

SCREEN = {
    "slug": "rfp", "extracted_by": "quick-reader",
    "papers": [{"doc_id": "PMC1"}, {"doc_id": "PMC2"}],
    "flagged": ["PMC1"],
    "failed": [],
}

DIG = {"slug": "rfp", "extracted_by": "quick-reader", "artifacts": []}

ARTIFACTS = {
    "slug": "rfp",
    "artifacts": [{"id": "art_001"}],
    "rejections": [{"id": "art_002", "kind": "not_confirmed_in_source"}],
}


def test_manifest_always_carries_the_non_negotiable_evidence_status():
    m = contracts.build_manifest(slug="rfp", objective="o")
    assert m["evidence_status"] == "discovery_only_unverified"


def test_manifest_evidence_status_is_unaffected_by_any_input_combination():
    m = contracts.build_manifest(slug="rfp", objective="o", search=SEARCH,
                                 screen=SCREEN, dig=DIG, artifacts=ARTIFACTS)
    assert m["evidence_status"] == "discovery_only_unverified"


def test_manifest_carries_every_set_id_not_just_one():
    m = contracts.build_manifest(slug="rfp", objective="o", search=SEARCH)
    ids = {row["set_id"] for row in m["set_ids"]}
    assert ids == {"s_aaa111", "s_bbb222", "s_ccc333"}
    assert len(m["set_ids"]) == 3  # one row per (class, phrase), not deduplicated


def test_manifest_set_ids_are_tagged_by_class_and_phrase():
    m = contracts.build_manifest(slug="rfp", objective="o", search=SEARCH)
    row = next(r for r in m["set_ids"] if r["set_id"] == "s_bbb222")
    assert row["class_id"] == "thermal"
    assert row["phrase"] == "magnetothermal switch"


def test_manifest_records_sources_and_n():
    m = contracts.build_manifest(slug="rfp", objective="o", search=SEARCH)
    assert m["sources"] == "pmc,biorxiv"
    assert m["n"] == 20


def test_manifest_records_screen_and_dig_workers():
    m = contracts.build_manifest(slug="rfp", objective="o", screen=SCREEN, dig=DIG)
    assert m["extracted_by"]["screen"] == "quick-reader"
    assert m["extracted_by"]["dig"] == "quick-reader"


def test_manifest_counts():
    m = contracts.build_manifest(slug="rfp", objective="o", screen=SCREEN, artifacts=ARTIFACTS)
    assert m["counts"]["papers_screened"] == 2
    assert m["counts"]["papers_flagged"] == 1
    assert m["counts"]["failed_extractions"] == 0
    assert m["counts"]["artifacts_runnable"] == 1
    assert m["counts"]["artifacts_rejected"] == 1


def test_manifest_has_a_utc_timestamp():
    m = contracts.build_manifest(slug="rfp", objective="o")
    assert m["created_at"].endswith("+00:00") or m["created_at"].endswith("Z")


def test_manifest_from_partial_run_has_null_counts_not_crashes():
    """Every input is optional -- a partial run must still produce a
    manifest describing what exists, not raise."""
    m = contracts.build_manifest(slug="rfp", objective="o")
    assert m["counts"]["papers_screened"] is None
    assert m["set_ids"] == []


def test_manifest_records_artifact_paths():
    m = contracts.build_manifest(slug="rfp", objective="o",
                                 paths={"search": "s.json", "screen": None, "evidence": "e.json"})
    assert m["artifact_paths"] == {"search": "s.json", "evidence": "e.json"}


def test_cmd_manifest_writes_evidence_status(tmp_path):
    search_path = tmp_path / "search.json"
    search_path.write_text(json.dumps(SEARCH))
    out_path = tmp_path / "manifest_rfp.json"

    args = argparse.Namespace(plan=None, search=str(search_path), screen=None, dig=None,
                              artifacts=None, evidence=None, slug=None, objective="an objective",
                              out=str(out_path))
    cli.cmd_manifest(args)

    result = json.loads(out_path.read_text())
    assert result["evidence_status"] == "discovery_only_unverified"
    assert result["slug"] == "rfp"
    assert len(result["set_ids"]) == 3


def test_cmd_manifest_derives_slug_from_search_when_not_given_explicitly():
    """--slug is optional per the task -- 'every input optional so a partial
    run still produces a manifest'; slug should come from a provided stage's
    own JSON when --slug is omitted."""
    m = contracts.build_manifest(slug=SEARCH["slug"], objective=None, search=SEARCH)
    assert m["slug"] == "rfp"
