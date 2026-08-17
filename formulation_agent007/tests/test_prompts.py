"""Anti-drift guard: the prompt must teach the vocabulary the validator
accepts, not the pre-sweep vocabulary it now rejects.

`prompts.py` is what tells the design LLM which tools and metrics exist.
`validate.py` is the guard that rejects gates naming things that don't exist.
If the two disagree, every generated brief fails validation, burns its one
regeneration, and ships with `validation_warnings` -- which is worse than not
having the guard at all. These tests exist to make that drift loud instead of
silent.
"""

from __future__ import annotations

import re

import pytest

from formulation_agent007 import catalog, prompts

# A gate thresholding a metric with `<=`/`>=` that flips the metric's own
# `better` direction reads fluently and is still wrong -- see
# test_gate_direction.py. It is exactly the kind of thing a stale worked
# example teaches by accident, so the metric-derived rules here are the
# other half of that guard: they check what the model is TOLD, not just what
# it is allowed to submit.

BOGUS_METRICS = (
    "mean_plddt",
    "dg_fold",
    "population_fraction",
    "tm_score",
    "ddg",
    "vina_score",
    "cluster_count",
)

# snake_case / camel_snake identifiers that are legitimate prose in the
# proto-brief prompt but are NOT metric names -- FitnessGate/ProtoBrief field
# names and one model-family name (esm_if1). Anything snake_case-shaped that
# shows up in PROTO_SYSTEM and is not a real metric must be added here
# deliberately; that friction is the point.
NOT_METRICS = frozenset({
    "cost_tier",
    "deployment_notes",
    "esm_if1",
    "kill_rule",
    "known_limitations",
    "ranking_expression",
    "threshold_upper",
    "tool_keys",
})

_TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b")

# Finding 2 (fix round 1): `_TOKEN_RE` requires an underscore, so a
# single-word fabricated metric (`vina`, `stability`) would slip past it --
# only the static BOGUS_METRICS list catches single words, and only the ones
# named there. Scanning every bare lowercase word against PROTO_METRICS is
# not practical: PROTO_SYSTEM's prose is full of ordinary single words
# ("cheap", "state", "kill") that are not metric names and would make the
# test permanently noisy with things that need adding to an allowlist purely
# because they are English.
#
# The practical middle ground: a metric name is only ever USED in this
# prompt directly against a comparison operator or `between` followed by a
# number -- that's the one place in a gate specification a word is acting as
# a metric rather than as prose (`avg_plddt >= 0.75`, `iptm between 0.0 and
# 0.45`). Requiring a trailing digit is what keeps this from matching
# ordinary prose uses of "between" ("the population balance between them",
# "the difference between a run that finishes and one that does not") --
# none of those have a number immediately after "between".
#
# Residual gap: a bare single-word fabricated metric mentioned only in prose
# (never placed against an operator with a number) still would not be
# caught by either scan -- only by BOGUS_METRICS or a human reviewer.
_METRIC_POSITION_RE = re.compile(
    r"\b([a-zA-Z][a-zA-Z0-9_]*)\s*(?:>=|<=|>|<)\s*-?\d"
    r"|\b([a-zA-Z][a-zA-Z0-9_]*)\s+between\s+-?\d"
)

_ALL_PROMPT_TEXT = "\n".join([
    prompts.TOOLCHAIN,
    prompts.FRAME_SYSTEM,
    prompts.SHARD_SYSTEM,
    prompts.LITERATURE_SYSTEM,
    prompts.HARVEST_SYSTEM,
    prompts.ASSEMBLY_SYSTEM,
    prompts.PROTO_SYSTEM,
])


@pytest.mark.parametrize("bogus", BOGUS_METRICS)
def test_no_bogus_metric_name_appears_anywhere_in_the_prompts(bogus):
    """Not even to say the metric doesn't exist -- a mechanical token scan
    cannot tell a recommendation from a disclaimer, so the honest way to
    describe a gap (see the bioemu note in PROTO_SYSTEM) is prose that never
    spells out the invented identifier at all."""
    assert re.search(rf"\b{re.escape(bogus)}\b", _ALL_PROMPT_TEXT) is None


def test_every_metric_like_name_in_proto_system_is_real():
    tokens = set(_TOKEN_RE.findall(prompts.PROTO_SYSTEM))
    unexplained = tokens - NOT_METRICS - catalog.PROTO_METRICS
    assert not unexplained, (
        f"PROTO_SYSTEM mentions snake_case token(s) that are neither a real "
        f"metric nor on the NOT_METRICS allowlist: {sorted(unexplained)}"
    )


def test_every_word_used_against_an_operator_is_a_real_metric():
    """Catches single-word fabricated metrics (no underscore, so invisible
    to `_TOKEN_RE`) at the one place a word is unambiguously acting as a
    metric name: directly against a comparison operator or `between`,
    followed by a number -- exactly how gates are written in the worked
    example. See the comment on `_METRIC_POSITION_RE` for what this does and
    does not catch."""
    words = {
        m.group(1) or m.group(2)
        for m in _METRIC_POSITION_RE.finditer(prompts.PROTO_SYSTEM)
    }
    assert words, "sanity check: the worked example should trip this at least once"
    unexplained = words - NOT_METRICS - catalog.PROTO_METRICS
    assert not unexplained, (
        f"PROTO_SYSTEM uses word(s) against a comparison operator that are "
        f"not real metrics: {sorted(unexplained)}"
    )


def test_not_metrics_allowlist_has_no_stale_entries():
    """If one of these ever becomes a real metric name, drop it from the
    allowlist instead of leaving a redundant entry."""
    overlap = NOT_METRICS & catalog.PROTO_METRICS
    assert not overlap, overlap


def test_metric_digest_output_is_embedded_in_proto_system():
    for line in catalog.metric_digest().splitlines():
        assert line in prompts.PROTO_SYSTEM


def test_worked_example_tool_keys_are_real():
    # esmfold-prediction, boltz2-prediction, pyrosetta-interface-analyzer
    for key in ("esmfold-prediction", "boltz2-prediction", "pyrosetta-interface-analyzer"):
        assert key in prompts.PROTO_SYSTEM
        assert key in catalog.PROTO_TOOL_KEYS


def test_prompt_admits_no_tool_publishes_population_metrics():
    """Part 2's honesty requirement: state the gap, do not invent a metric."""
    assert "bioemu-sample" in prompts.PROTO_SYSTEM
    assert "no metrics block" in prompts.PROTO_SYSTEM
