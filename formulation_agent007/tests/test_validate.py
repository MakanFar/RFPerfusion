"""The validators earn their place only if they reject fluent, well-formed junk.

Every test below feeds in something that parses cleanly, reads plausibly, and
is wrong in a way that would waste real compute or send a downstream agent
after a tool that does not exist.
"""

from __future__ import annotations

import pytest

from formulation_agent007.catalog import METRIC_CALIBRATION
from formulation_agent007.models import FitnessGate, GateState, Linker
from formulation_agent007.validate import (
    _decimal_step,
    validate_assembly,
    validate_frame,
    validate_literature,
    validate_proto,
    validate_shards,
)


class TestProtoCascade:
    def test_accepts_a_well_formed_cascade(self, proto):
        assert validate_proto(proto) == []

    def test_rejects_an_invented_tool_key(self, proto):
        proto.gates[0].tool_keys = ["fieldsolver3d"]
        problems = validate_proto(proto)
        assert any("fieldsolver3d" in p for p in problems)

    def test_rejects_an_invented_metric(self, proto):
        proto.gates[0].metric = "switchiness"
        problems = validate_proto(proto)
        assert any("switchiness" in p for p in problems)

    def test_rejects_cost_inverted_cascade(self, proto):
        # bioemu (expensive) pulled to the front, esmfold pushed to the back.
        proto.gates[0].order, proto.gates[3].order = 4, 1
        problems = validate_proto(proto)
        assert any("cheap-first" in p for p in problems)

    def test_rejects_cascade_with_no_decisive_gate(self, proto):
        for gate in proto.gates:
            gate.decisive = False
        problems = validate_proto(proto)
        assert any("decisive" in p for p in problems)

    def test_rejects_interface_metric_on_a_single_chain(self, proto):
        proto.gates[1].state = GateState.SINGLE
        problems = validate_proto(proto)
        assert any("interface metric" in p for p in problems)

    def test_rejects_mislabelled_cost_tier(self, proto):
        proto.gates[3].cost_tier = "cheap"  # boltz2-prediction is not cheap
        problems = validate_proto(proto)
        assert any("cost_tier" in p for p in problems)

    def test_rejects_between_without_upper_bound(self, proto):
        proto.gates[3].threshold_upper = None
        problems = validate_proto(proto)
        assert any("threshold_upper" in p for p in problems)

    def test_rejects_gate_that_kills_nothing(self, proto):
        proto.gates[0].kill_rule = "   "
        problems = validate_proto(proto)
        assert any("kill_rule" in p for p in problems)

    def test_rejects_non_contiguous_gate_orders(self, proto):
        proto.gates[2].order = 9
        problems = validate_proto(proto)
        assert any("gate orders" in p for p in problems)

    _CAL = {"esmfold-prediction": {
        "status": "validated",
        "measured_error": {"kind": "mae", "value": 0.06}}}

    def test_uncalibrated_metric_raises_no_margin_problem(self, proto):
        """validate_proto's output drives an LLM repair attempt
        (agent.py:120), not a warning log. With nothing calibrated, flagging
        uncalibrated gates would fire on every gate of every run and drive a
        repair that cannot succeed. The label belongs in the runbook."""
        assert not any("measured error" in p for p in validate_proto(proto))

    def test_between_window_narrower_than_twice_the_error_is_rejected(
            self, proto, monkeypatch):
        monkeypatch.setitem(METRIC_CALIBRATION, "avg_plddt", self._CAL)
        gate = proto.gates[0]
        gate.metric, gate.tool_keys = "avg_plddt", ["esmfold-prediction"]
        gate.operator = "between"
        gate.threshold, gate.threshold_upper = 0.80, 0.85

        assert any("measured error" in p for p in validate_proto(proto))

    def test_threshold_quoted_finer_than_the_measured_error_is_rejected(
            self, proto, monkeypatch):
        monkeypatch.setitem(METRIC_CALIBRATION, "avg_plddt", self._CAL)
        gate = proto.gates[0]
        gate.metric, gate.tool_keys = "avg_plddt", ["esmfold-prediction"]
        gate.operator, gate.threshold = ">=", 0.852
        gate.threshold_upper = None

        assert any("measured error" in p for p in validate_proto(proto))

    def test_threshold_coarser_than_the_measured_error_passes(
            self, proto, monkeypatch):
        monkeypatch.setitem(METRIC_CALIBRATION, "avg_plddt", self._CAL)
        gate = proto.gates[0]
        gate.metric, gate.tool_keys = "avg_plddt", ["esmfold-prediction"]
        gate.operator, gate.threshold = ">=", 0.8
        gate.threshold_upper = None

        assert not any("measured error" in p for p in validate_proto(proto))

    def test_calibration_for_a_tool_the_gate_does_not_name_is_ignored(
            self, proto, monkeypatch):
        """The gate names the tools that will actually run. A metric
        validated on some other tool says nothing about this gate."""
        monkeypatch.setitem(METRIC_CALIBRATION, "avg_plddt", self._CAL)
        gate = proto.gates[0]
        gate.metric, gate.tool_keys = "avg_plddt", ["boltz2-prediction"]
        gate.operator, gate.threshold = ">=", 0.852
        gate.threshold_upper = None

        assert not any("measured error" in p for p in validate_proto(proto))

    def test_whole_number_threshold_is_not_rejected_by_a_coarser_error(
            self, proto, monkeypatch):
        """A whole number claims no fractional precision. Regression for the
        bug where `_decimal_step` returned 0.1 for any whole-number float
        (pydantic always coerces an authored `2` to `2.0`, so this path is
        the only one a real gate ever takes) -- that falsely rejected a
        gate like `count >= 2` against a measured error as coarse as 0.5."""
        monkeypatch.setitem(METRIC_CALIBRATION, "avg_plddt", {
            "esmfold-prediction": {
                "status": "validated",
                "measured_error": {"kind": "mae", "value": 0.5}}})
        gate = proto.gates[0]
        gate.metric, gate.tool_keys = "avg_plddt", ["esmfold-prediction"]
        gate.operator, gate.threshold = ">=", 2.0
        gate.threshold_upper = None

        assert not any("measured error" in p for p in validate_proto(proto))

    def test_inverted_between_gate_is_not_also_flagged_by_the_margin_check(
            self, proto, monkeypatch):
        """threshold_upper <= threshold is already rejected by the shape
        check; the margin check must not pile on a nonsensical negative-
        window message on top of it (that message would also feed the LLM
        repair loop)."""
        monkeypatch.setitem(METRIC_CALIBRATION, "avg_plddt", self._CAL)
        gate = proto.gates[0]
        gate.metric, gate.tool_keys = "avg_plddt", ["esmfold-prediction"]
        gate.operator = "between"
        gate.threshold, gate.threshold_upper = 0.85, 0.80

        problems = validate_proto(proto)
        assert any("threshold_upper <= threshold" in p for p in problems)
        assert not any("measured error" in p for p in problems)


class TestDecimalStep:
    """Pinned cases for `_decimal_step`. A whole number claims no fractional
    precision -- `repr()` of a whole-number float always appends `.0`, and
    `models.py` types `threshold: float`, so a real gate's whole-number
    threshold always takes this path."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (0.8, 0.1),
            (0.852, 0.001),
            (2.0, 1.0),
            (10.0, 1.0),
            (2.50, 0.1),
            (0.0, 1.0),
        ],
    )
    def test_pinned_cases(self, value, expected):
        assert _decimal_step(value) == pytest.approx(expected)


class TestLiteraturePlan:
    def test_accepts_a_well_formed_plan(self, literature):
        assert validate_literature(literature) == []

    def test_rejects_single_word_phrases(self, literature):
        literature.search_phrases[0] = "protein"
        problems = validate_literature(literature)
        assert any("single word" in p for p in problems)

    def test_rejects_question_form_phrases(self, literature):
        literature.search_phrases[0] = "how does temperature affect folding"
        problems = validate_literature(literature)
        assert any("question" in p for p in problems)

    def test_rejects_too_few_phrases(self, literature):
        literature.search_phrases = literature.search_phrases[:3]
        problems = validate_literature(literature)
        assert any("search_phrases has 3" in p for p in problems)

    def test_rejects_duplicate_phrases(self, literature):
        literature.search_phrases[1] = literature.search_phrases[0].upper()
        problems = validate_literature(literature)
        assert any("duplicates" in p for p in problems)

    def test_rejects_a_thin_concept_file(self, literature):
        literature.concept_text = "make a switch"
        problems = validate_literature(literature)
        assert any("concept_text" in p for p in problems)


class TestAssembly:
    def test_accepts_a_well_formed_recipe(self, assembly, shards):
        assert validate_assembly(assembly, shards) == []

    def test_rejects_linker_between_non_adjacent_shards(self, assembly, shards):
        assembly.linkers[0] = Linker(
            after_shard="S1", before_shard="S3", sequence="GGGGS"
        )
        problems = validate_assembly(assembly, shards)
        assert any("not adjacent" in p for p in problems)

    def test_rejects_non_amino_acid_linker(self, assembly, shards):
        assembly.linkers[0].sequence = "GGGG-SXB"
        problems = validate_assembly(assembly, shards)
        assert any("amino acids" in p for p in problems)

    def test_rejects_dropped_required_shard(self, assembly, shards):
        assembly.construct_order = ["S1", "S2"]
        assembly.linkers = assembly.linkers[:1]
        problems = validate_assembly(assembly, shards)
        assert any("omits required shard" in p for p in problems)

    def test_rejects_unknown_shard_in_construct(self, assembly, shards):
        assembly.construct_order = ["S1", "S2", "S3", "S9"]
        problems = validate_assembly(assembly, shards)
        assert any("S9" in p for p in problems)


class TestFrameAndShards:
    def test_accepts_a_well_formed_frame(self, frame):
        assert validate_frame(frame) == []

    def test_rejects_a_slug_paperclip_kb_would_refuse(self, frame):
        frame.slug = "Test Design"
        problems = validate_frame(frame)
        assert any("slug" in p for p in problems)

    def test_requires_an_excluded_pathway(self, frame):
        frame.excluded_pathways = []
        problems = validate_frame(frame)
        assert any("excluded_pathways" in p for p in problems)

    def test_requires_a_simulability_note(self, frame):
        frame.simulability_note = ""
        problems = validate_frame(frame)
        assert any("simulability_note" in p for p in problems)

    def test_accepts_well_formed_shards(self, shards):
        assert validate_shards(shards) == []

    def test_rejects_shard_without_search_handles(self, shards):
        shards[0].search_handles = []
        problems = validate_shards(shards)
        assert any("search_handles" in p for p in problems)

    def test_rejects_duplicate_shard_ids(self, shards):
        shards[1].id = "S1"
        problems = validate_shards(shards)
        assert any("duplicate" in p for p in problems)


class TestNoUnsupportedConstraints:
    """Structured-output backends strip string `maxLength` from the schema and
    validate it client-side, so a response that misses the limit is discarded
    *after* an expensive generation. Length guidance belongs in the prompt.
    """

    @pytest.mark.parametrize(
        "model",
        [
            FitnessGate,
            Linker,
        ],
    )
    def test_no_max_length_on_response_models(self, model):
        schema = model.model_json_schema()
        assert "maxLength" not in str(schema)
