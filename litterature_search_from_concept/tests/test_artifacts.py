import argparse
import json

from litkb import cli, contracts

RECORD = {"value": "MKVAAL", "molecule": "protein", "name": "AsLOV2",
          "region": [404, 546], "where": "Table S1", "verbatim": True}


def test_draft_artifact_has_a_stable_id():
    a = contracts.draft_artifact(7, RECORD, "PMC1", "s_1")
    assert a["id"] == "art_007"


def test_region_makes_it_a_subsequence():
    assert contracts.draft_artifact(1, RECORD, "PMC1", "s_1")["kind"] == "subsequence"


def test_absent_region_makes_it_a_sequence():
    record = dict(RECORD, region=None)
    assert contracts.draft_artifact(1, record, "PMC1", "s_1")["kind"] == "sequence"


def test_length_is_computed_from_the_value():
    assert contracts.draft_artifact(1, RECORD, "PMC1", "s_1")["length"] == 6


def test_confirmation_starts_false_until_checked():
    a = contracts.draft_artifact(1, RECORD, "PMC1", "s_1")
    assert a["provenance"]["confirmed_in_source"] is False


def _run_bind(tmp_path, artifacts, tools):
    artifacts_path = tmp_path / "artifacts.json"
    artifacts_path.write_text(json.dumps({"slug": "s", "artifacts": artifacts}))
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"tools": tools}))
    out_path = tmp_path / "bound.json"
    args = argparse.Namespace(artifacts=str(artifacts_path),
                              registry=str(registry_path), out=str(out_path))
    cli.cmd_bind(args)
    return json.loads(out_path.read_text())


def test_cmd_bind_confirms_sequences_with_fixed_string_matching(tmp_path, monkeypatch):
    """Guards the literal-matching closure in cmd_bind: confirm_in_source's
    grep_fn must call grep_set with fixed=True. A bare grep_set would send a
    sequence containing `*` or `.` to `paperclip grep -e` as a REGEX, and
    such a sequence could then match text that is not actually the
    sequence -- a FALSE CONFIRMATION, exactly the failure source-confirmation
    exists to prevent."""
    calls = []

    def fake_grep_set(set_id, patterns, ignore_case=False, fixed=False):
        calls.append({"set_id": set_id, "patterns": patterns, "fixed": fixed})
        return [{"doc_id": "PMC1", "text": patterns[0]}]

    monkeypatch.setattr(cli, "grep_set", fake_grep_set)

    art = contracts.draft_artifact(1, RECORD, "PMC1", "s_1")
    _run_bind(tmp_path, [art], [])

    assert calls, "grep_set was never called"
    assert calls[0]["fixed"] is True


def test_unsupported_kind_binding_has_a_non_empty_string_reason(tmp_path, monkeypatch):
    """A mutation artifact (kind="mutation") is unbindable by any current
    proto tool; cmd_bind must not let that rejection carry an empty list
    for a reason -- an agent reading rejections needs an actual explanation,
    not a falsy placeholder that looks like "no problem"."""
    def fake_grep_set(set_id, patterns, ignore_case=False, fixed=False):
        return [{"doc_id": "PMC1", "text": patterns[0]}]

    monkeypatch.setattr(cli, "grep_set", fake_grep_set)

    mut_record = {"value": "V342A", "molecule": "protein", "name": "TRPV1",
                  "verbatim": True}
    art = contracts.draft_artifact(1, mut_record, "PMC1", "s_1", kind="mutation")
    result = _run_bind(tmp_path, [art], [])

    rejections = result["rejections"]
    assert len(rejections) == 1
    rej = rejections[0]
    assert rej["kind"] == "proto_unsupported_kind"
    assert isinstance(rej["reason"], str)
    assert rej["reason"] != ""
    assert rej["doc_id"] == "PMC1"


def test_unconfirmed_mutation_gets_a_notation_specific_reason(tmp_path, monkeypatch):
    """A real, paper-reported mutation whose notation the reader normalised
    (Val342Ala written as V342A, spacing, etc.) fails the literal grep for a
    reason that has nothing to do with fabrication. cmd_bind must not reuse
    the sequence-fabrication wording ("sequence does not literally appear
    in its source document") on a mutation -- that phrasing is a
    fabrication signal applied to what may be a genuine finding."""
    def fake_grep_set(set_id, patterns, ignore_case=False, fixed=False):
        return []  # nothing matches -- could be notation mismatch, not fabrication

    monkeypatch.setattr(cli, "grep_set", fake_grep_set)

    mut_record = {"value": "V342A", "molecule": "protein", "name": "TRPV1",
                  "verbatim": True}
    art = contracts.draft_artifact(1, mut_record, "PMC1", "s_1", kind="mutation")
    result = _run_bind(tmp_path, [art], [])

    rejections = result["rejections"]
    assert len(rejections) == 1
    rej = rejections[0]
    assert rej["kind"] == "not_confirmed_in_source"
    assert "notation" in rej["reason"]
    assert "sequence does not literally appear" not in rej["reason"]


def test_quality_gated_rejections_carry_their_own_kind_and_a_string_reason(
        tmp_path, monkeypatch):
    """`VPGXG` bound to esmfold-prediction in a live run with every per-tool
    check reading `pass`. The two gates that now stop it are artifact-quality
    judgements, not proto constraints, so they must NOT be reported under a
    `proto_` kind -- and, like unsupported_kind above, they must carry a real
    string reason rather than the falsy empty list the generic branch would
    supply."""
    def fake_grep_set(set_id, patterns, ignore_case=False, fixed=False):
        return [{"doc_id": "PMC1", "text": patterns[0]}]

    monkeypatch.setattr(cli, "grep_set", fake_grep_set)

    motif = contracts.draft_artifact(
        1, {"value": "VPGXG", "molecule": "protein", "name": "ELP",
            "verbatim": True}, "PMC1", "s_1")
    short = contracts.draft_artifact(
        2, {"value": "VPGVG", "molecule": "protein", "name": "ELP",
            "verbatim": True}, "PMC1", "s_1")

    result = _run_bind(tmp_path, [motif, short], [])

    assert result["artifacts"] == []
    by_id = {r["id"]: r for r in result["rejections"]}
    assert by_id["art_001"]["kind"] == "unspecified_sequence"
    assert by_id["art_002"]["kind"] == "below_min_length"
    for rej in by_id.values():
        assert isinstance(rej["reason"], str) and rej["reason"]
        assert rej["doc_id"] == "PMC1"
