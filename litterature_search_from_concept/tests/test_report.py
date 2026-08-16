from litkb import report

EVIDENCE = {"slug": "rfp", "items": []}
ARTIFACTS = {"artifacts": [
    {"id": "art_001", "kind": "sequence", "molecule": "protein",
     "value": "MKVAAL", "length": 6,
     "parent": {"name": "AsLOV2", "accession": None, "region": None},
     "provenance": {"doc_id": "PMC1", "where": "Table S1",
                    "verbatim": True, "confirmed_in_source": True},
     "proto_binding": {"status": "runnable",
                       "tools": [{"key": "esm2-score", "checks": {}}]}}],
    "rejections": [{"kind": "not_confirmed_in_source", "id": "art_002",
                    "reason": "sequence does not literally appear in its source document"}]}


def test_report_names_the_bound_tool():
    text = report.render(EVIDENCE, None, ARTIFACTS)
    assert "esm2-score" in text


def test_report_shows_the_sequence_and_its_source():
    text = report.render(EVIDENCE, None, ARTIFACTS)
    assert "MKVAAL" in text and "Table S1" in text


def test_report_surfaces_rejected_artifacts():
    text = report.render(EVIDENCE, None, ARTIFACTS)
    assert "not_confirmed_in_source" in text


def test_report_states_acceptance_is_a_schema_check_not_a_run():
    text = report.render(EVIDENCE, None, ARTIFACTS)
    assert "not a run" in text or "not been executed" in text


def test_report_without_artifacts_still_renders():
    assert "knowledge base" in report.render(EVIDENCE)


def test_cmd_report_passes_artifacts_through(tmp_path, monkeypatch):
    """cmd_report must load --artifacts and hand it to report.render, not
    silently drop it."""
    import argparse
    import json
    from litkb import cli

    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(EVIDENCE))
    artifacts_path = tmp_path / "artifacts.json"
    artifacts_path.write_text(json.dumps(ARTIFACTS))
    out_path = tmp_path / "kb.txt"

    args = argparse.Namespace(evidence=str(evidence_path), search=None,
                              artifacts=str(artifacts_path), plan=None, screen=None,
                              dig=None, objective=None, out=str(out_path))
    cli.cmd_report(args)

    text = out_path.read_text()
    assert "esm2-score" in text


def test_cmd_report_registers_artifacts_flag():
    # `report`'s argparse subparser must expose --artifacts, per the task's
    # explicit instruction to check it is registered.
    import io
    from contextlib import redirect_stdout
    from litkb import cli

    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            cli.main(["report", "--help"])
    except SystemExit:
        pass
    assert "--artifacts" in buf.getvalue()
