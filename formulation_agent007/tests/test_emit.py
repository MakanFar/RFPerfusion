"""Emission tests.

The important one is `test_plan_is_accepted_by_paperclip_kb`: it validates our
emitted plan with the real `validate_plan` from the mining script rather than
with our restatement of its rules, so the two cannot drift apart silently.
"""

from __future__ import annotations

import json
import re

from formulation_agent007.emit import render_harvest, render_proto_brief, save_brief


class TestPaperclipContract:
    def test_plan_is_accepted_by_paperclip_kb(self, brief, paperclip_kb):
        payload = brief.literature.plan_payload()
        assert paperclip_kb.validate_plan(payload) == payload

    def test_plan_payload_has_only_the_three_expected_keys(self, brief):
        assert set(brief.literature.plan_payload()) == {
            "search_phrases",
            "mechanism_patterns",
            "notes",
        }

    def test_slug_matches_the_script_safe_slug_rule(self, brief, paperclip_kb):
        assert paperclip_kb.SAFE_SLUG_RE.fullmatch(brief.slug)


class TestArtifacts:
    def test_writes_every_expected_file(self, brief, tmp_path):
        names = {p.name for p in save_brief(brief, str(tmp_path))}
        assert f"concept_{brief.slug}.txt" in names
        assert f"plan_{brief.slug}.json" in names
        assert f"harvest_{brief.slug}.md" in names
        assert f"proto_brief_{brief.slug}.md" in names
        assert "run_literature.sh" in names
        assert any(re.fullmatch(r"brief-\d{8}-\d{6}\.json", n) for n in names)
        assert any(re.fullmatch(r"brief-\d{8}-\d{6}\.md", n) for n in names)

    def test_plan_file_round_trips(self, brief, tmp_path, paperclip_kb):
        save_brief(brief, str(tmp_path))
        written = json.loads((tmp_path / f"plan_{brief.slug}.json").read_text())
        assert paperclip_kb.validate_plan(written) == written

    def test_run_script_passes_the_reviewed_plan(self, brief, tmp_path):
        save_brief(brief, str(tmp_path))
        script = (tmp_path / "run_literature.sh").read_text()
        assert "--dry-run" in script
        assert "--plan-file" in script
        assert f"--slug {brief.slug}" in script


class TestProtoRunbook:
    def test_lists_every_gate_in_order(self, brief):
        text = render_proto_brief(brief)
        positions = [text.index(f"### Gate {g.order} —") for g in brief.proto.ordered()]
        assert positions == sorted(positions)

    def test_states_each_numeric_condition(self, brief):
        text = render_proto_brief(brief)
        for gate in brief.proto.gates:
            assert gate.condition() in text

    def test_carries_the_billable_deployment_warning(self, brief):
        text = render_proto_brief(brief)
        assert "billable" in text
        assert "one at a time" in text

    def test_inherits_the_unverified_evidence_status(self, brief):
        assert "discovery_only_unverified" in render_proto_brief(brief)

    def test_surfaces_validation_warnings_to_the_downstream_agent(self, brief):
        brief.validation_warnings = ["[proto] something did not check out"]
        assert "something did not check out" in render_proto_brief(brief)

    def test_names_the_unscoreable_step(self, brief):
        assert brief.frame.simulability_note in render_proto_brief(brief)


class TestHarvestContract:
    def test_covers_every_shard(self, brief):
        text = render_harvest(brief)
        for shard in brief.shards:
            assert shard.id in text

    def test_states_that_a_grep_hit_is_not_evidence(self, brief):
        assert "lead" in render_harvest(brief)
