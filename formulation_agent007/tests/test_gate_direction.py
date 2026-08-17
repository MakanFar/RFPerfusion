import pytest

from formulation_agent007 import validate
from formulation_agent007.models import FitnessGate, GateState, ProtoBrief


def _gate(metric, operator, **kw):
    return FitnessGate(
        order=1, name="g", purpose="p", tool_keys=["esmfold-prediction"],
        input_description="d", state=GateState.SINGLE, metric=metric,
        operator=operator, threshold=0.5, kill_rule="drop", cost_tier="cheap",
        **kw)


def _problems(gate):
    """A one-gate brief trips unrelated rules (no decisive gate, and so on),
    so filter to the direction check this task adds."""
    all_problems = validate.validate_proto(ProtoBrief(gates=[gate]))
    return [p for p in all_problems if "direction is inverted" in p]


def test_higher_is_better_metric_with_a_ceiling_is_rejected():
    # avg_plddt is better=higher, so `<= 0.5` gates out the GOOD candidates.
    assert _problems(_gate("avg_plddt", "<="))


def test_higher_is_better_metric_with_a_floor_is_accepted():
    assert _problems(_gate("avg_plddt", ">=")) == []


def test_lower_is_better_metric_with_a_floor_is_rejected():
    assert _problems(_gate("avg_pae", ">="))


def test_lower_is_better_metric_with_a_ceiling_is_accepted():
    assert _problems(_gate("avg_pae", "<=")) == []


def test_between_is_never_a_direction_error():
    gate = _gate("avg_plddt", "between", threshold_upper=0.9)
    assert _problems(gate) == []


def test_context_metrics_are_exempt():
    """`better=context-dependent` means direction is not decidable; do not guess."""
    from formulation_agent007 import catalog
    contextual = [m for m, d in catalog.METRIC_DIRECTION.items()
                  if d == "context-dependent"]
    if not contextual:
        pytest.skip("no better=context metrics in the current snapshot")
    assert _problems(_gate(contextual[0], ">=")) == []
