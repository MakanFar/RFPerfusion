"""Semantic validation — the rules the JSON schema cannot express.

Everything here is a rule that a fluent, well-formed, completely wrong answer
would otherwise pass. Each validator returns a list of problem strings; an
empty list means the stage is accepted. `agent.py` feeds a non-empty list back
to the model once, then records the survivors as `validation_warnings` rather
than failing the run — a brief with a known flaw stated on it is more useful
than no brief.

The load-bearing checks, in rough order of how much damage they prevent:

  1. A gate may only name a tool key that exists in the proto-tools catalogue.
  2. The cascade must be ordered cheap-first.
  3. At least one gate must be `decisive` — must measure the requested
     function, not just whether the chain folds.
  4. Every required shard must appear in the construct order exactly once.
  5. Linkers must join shards that are actually adjacent.
  6. The literature plan must satisfy paperclip_kb.validate_plan's contract
     *and* its count bounds, so it can be passed with --plan-file unedited.
"""

from __future__ import annotations

import re
from decimal import Decimal

from .catalog import (
    INTERFACE_METRICS,
    METRIC_DIRECTION,
    PROTO_METRICS,
    calibration_for,
    cost_rank,
    gate_cost_tier,
    unknown_tools,
)
from .config import SETTINGS
from .models import (
    AssemblyRecipe,
    DesignFrame,
    GateState,
    HarvestContract,
    LiteraturePlan,
    ProtoBrief,
    Shard,
)

SHARD_ID_RE = re.compile(r"^S[0-9]+$")
# A phrase real authors write is several words long. One-word "phrases" match
# everything and turn the Paperclip set into noise.
MIN_PHRASE_WORDS = 2


def _decimal_step(value: float) -> float:
    """The resolution a number is quoted to: 0.85 -> 0.01, 0.852 -> 0.001,
    2.0 -> 1.0, 1e-05 -> 1e-05.

    Quoting more digits than the evaluator's error supports is a claim about
    precision the measurement does not carry. Goes through
    `Decimal(repr(value))` rather than text-sniffing the repr: `repr()`
    switches to exponent notation below 1e-4, and a prior version treated
    any exponent-notation repr as "no fractional precision claimed" (whole-
    number coarse) -- which fails open, scoring a threshold finer than 1e-4
    as maximally coarse and skipping the margin check for exactly the
    thresholds it matters most for.

    Known nuisance, not fixed here: a *computed* threshold like `0.1 + 0.2`
    reprs as `0.30000000000000004` (exponent -17) and would read as
    claiming 17 digits of precision, producing a spurious rejection. There
    is no way to tell an authored ultra-fine threshold apart from a
    float-arithmetic artifact from the value alone.
    """
    exp = Decimal(repr(value)).normalize().as_tuple().exponent
    return 10.0 ** exp if exp < 0 else 1.0


# --------------------------------------------------------------------------
# frame
# --------------------------------------------------------------------------


def validate_frame(frame: DesignFrame) -> list[str]:
    problems: list[str] = []
    if not frame.slug_ok():
        problems.append(
            f"slug {frame.slug!r} must match ^[a-z0-9][a-z0-9-]*$ "
            "(paperclip_kb.py rejects anything else)"
        )
    if not frame.chosen_pathway.strip():
        problems.append("chosen_pathway is empty")
    if not frame.pathway_rationale.strip():
        problems.append("pathway_rationale is empty")
    if not frame.excluded_pathways:
        problems.append(
            "excluded_pathways is empty: name at least one route you considered "
            "and dropped, and say whether it was dropped because it is wrong or "
            "because it cannot be simulated with the available tools"
        )
    if not frame.simulability_note.strip():
        problems.append(
            "simulability_note is empty: state plainly what part of this design "
            "the toolchain cannot evaluate"
        )
    return problems


# --------------------------------------------------------------------------
# shards
# --------------------------------------------------------------------------


def validate_shards(shards: list[Shard]) -> list[str]:
    problems: list[str] = []
    if not (SETTINGS.min_shards <= len(shards) <= SETTINGS.max_shards):
        problems.append(
            f"got {len(shards)} shards; need between {SETTINGS.min_shards} and "
            f"{SETTINGS.max_shards}"
        )
    seen: set[str] = set()
    for shard in shards:
        if not SHARD_ID_RE.fullmatch(shard.id):
            problems.append(f"shard id {shard.id!r} must look like S1, S2, ...")
        if shard.id in seen:
            problems.append(f"duplicate shard id {shard.id!r}")
        seen.add(shard.id)
        if not shard.search_handles:
            problems.append(
                f"{shard.id} has no search_handles; give the literal protein, "
                "mutant or technique names a relevant paper would contain"
            )
        if not shard.candidate_families:
            problems.append(f"{shard.id} has no candidate_families to harvest from")
    return problems


# --------------------------------------------------------------------------
# literature plan
# --------------------------------------------------------------------------


def validate_literature(plan: LiteraturePlan) -> list[str]:
    problems: list[str] = []
    s = SETTINGS

    n_phrases = len(plan.search_phrases)
    if not (s.min_search_phrases <= n_phrases <= s.max_search_phrases):
        problems.append(
            f"search_phrases has {n_phrases} entries; paperclip_kb.py expects "
            f"{s.min_search_phrases}-{s.max_search_phrases}"
        )
    n_patterns = len(plan.mechanism_patterns)
    if not (s.min_mechanism_patterns <= n_patterns <= s.max_mechanism_patterns):
        problems.append(
            f"mechanism_patterns has {n_patterns} entries; paperclip_kb.py "
            f"expects {s.min_mechanism_patterns}-{s.max_mechanism_patterns}"
        )

    for phrase in plan.search_phrases:
        stripped = phrase.strip()
        if len(stripped.split()) < MIN_PHRASE_WORDS:
            problems.append(
                f"search phrase {phrase!r} is a single word; phrases are matched "
                "verbatim against titles and abstracts and must be multi-word "
                "noun phrases real authors write"
            )
        if stripped.endswith("?") or stripped.lower().startswith(
            ("how ", "what ", "why ", "can ", "does ", "is ")
        ):
            problems.append(f"search phrase {phrase!r} is a question, not a phrase")

    lowered = [p.strip().lower() for p in plan.search_phrases]
    if len(set(lowered)) != len(lowered):
        problems.append("search_phrases contains duplicates")

    pattern_lowered = [p.strip().lower() for p in plan.mechanism_patterns]
    if len(set(pattern_lowered)) != len(pattern_lowered):
        problems.append("mechanism_patterns contains duplicates")
    for pattern in plan.mechanism_patterns:
        if len(pattern.strip()) < 4:
            problems.append(
                f"mechanism pattern {pattern!r} is too short to be selective"
            )

    if len(plan.concept_text.split()) < 60:
        problems.append(
            "concept_text is too thin to plan from; it is the concept file a "
            "domain expert would have written, so it needs the function, the "
            "mechanism, the shards, and the constraints"
        )
    if not plan.notes.strip():
        problems.append("notes is empty; say what you deliberately excluded and why")
    return problems


# --------------------------------------------------------------------------
# harvest contract
# --------------------------------------------------------------------------


def validate_harvest(harvest: HarvestContract, shards: list[Shard]) -> list[str]:
    problems: list[str] = []
    known = {s.id for s in shards}
    covered = {rule.shard_id for rule in harvest.per_shard}

    for rule in harvest.per_shard:
        if rule.shard_id not in known:
            problems.append(
                f"harvest rule references unknown shard {rule.shard_id!r}"
            )
        if not rule.accept_if:
            problems.append(f"harvest rule for {rule.shard_id} has no accept_if tests")

    missing = sorted(known - covered)
    if missing:
        problems.append(f"no harvest rule for shard(s): {', '.join(missing)}")
    if not harvest.record_fields:
        problems.append(
            "record_fields is empty; the Paperclip agent needs to know what "
            "provenance to record with each extracted sequence"
        )
    return problems


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


def validate_assembly(assembly: AssemblyRecipe, shards: list[Shard]) -> list[str]:
    problems: list[str] = []
    order = [s.strip().upper() for s in assembly.construct_order]
    known = {s.id.upper() for s in shards}
    required = {s.id.upper() for s in shards if s.required}

    unknown = [s for s in order if s not in known]
    if unknown:
        problems.append(f"construct_order names unknown shard(s): {', '.join(unknown)}")
    if len(set(order)) != len(order):
        problems.append("construct_order repeats a shard")
    missing = sorted(required - set(order))
    if missing:
        problems.append(
            f"construct_order omits required shard(s): {', '.join(missing)}"
        )

    adjacent = {(order[i], order[i + 1]) for i in range(len(order) - 1)}
    for linker in assembly.linkers:
        pair = (linker.after_shard.strip().upper(), linker.before_shard.strip().upper())
        if pair not in adjacent:
            problems.append(
                f"linker {pair[0]}->{pair[1]} joins shards that are not adjacent "
                f"in construct_order ({' -> '.join(order)})"
            )
        if not linker.sequence_ok():
            problems.append(
                f"linker {pair[0]}->{pair[1]} sequence {linker.sequence!r} is not a "
                "non-empty string of standard one-letter amino acids"
            )

    if len(order) > 1 and not assembly.linkers:
        problems.append("multi-shard construct declares no linkers")
    if not assembly.fasta_outputs:
        problems.append(
            "fasta_outputs is empty; name the FASTA files the assembly step must "
            "produce for the Proto agent to consume"
        )
    if not assembly.trimming_rules:
        problems.append(
            "trimming_rules is empty; harvested domains have to be cut somewhere "
            "and cutting inside a secondary-structure element is the default bug"
        )
    return problems


# --------------------------------------------------------------------------
# proto brief — the cascade
# --------------------------------------------------------------------------


def validate_proto(proto: ProtoBrief) -> list[str]:
    problems: list[str] = []
    gates = proto.ordered()
    s = SETTINGS

    if not (s.min_gates <= len(gates) <= s.max_gates):
        problems.append(
            f"got {len(gates)} gates; need between {s.min_gates} and {s.max_gates}"
        )

    orders = [g.order for g in gates]
    if orders != list(range(1, len(gates) + 1)):
        problems.append(
            f"gate orders must be 1..{len(gates)} with no gaps or repeats; got {orders}"
        )

    for gate in gates:
        bad = unknown_tools(gate.tool_keys)
        if bad:
            problems.append(
                f"gate {gate.order} ({gate.name}) names tool key(s) not in the "
                f"proto-tools catalogue: {', '.join(bad)}"
            )
        if not gate.tool_keys:
            problems.append(f"gate {gate.order} ({gate.name}) names no tool")
        if gate.metric not in PROTO_METRICS:
            problems.append(
                f"gate {gate.order} thresholds on {gate.metric!r}, which is not a "
                f"metric these tools emit; choose one of: "
                f"{', '.join(sorted(PROTO_METRICS))}"
            )
        # A gate thresholding a better=higher metric with `<=` keeps the worst
        # candidates and kills the best. The cascade still reads fluently, which
        # is exactly why this needs checking mechanically.
        direction = METRIC_DIRECTION.get(gate.metric)
        if direction and gate.operator != "between":
            floor = gate.operator in (">=", ">")
            if direction == "higher" and not floor:
                problems.append(
                    f"gate {gate.order} keeps {gate.metric!r} {gate.operator} "
                    f"{gate.threshold:g}, but higher is better for that metric; "
                    f"the direction is inverted"
                )
            elif direction == "lower" and floor:
                problems.append(
                    f"gate {gate.order} keeps {gate.metric!r} {gate.operator} "
                    f"{gate.threshold:g}, but lower is better for that metric; "
                    f"the direction is inverted"
                )
        if gate.operator == "between":
            if gate.threshold_upper is None:
                problems.append(
                    f"gate {gate.order} uses 'between' without threshold_upper"
                )
            elif gate.threshold_upper <= gate.threshold:
                problems.append(
                    f"gate {gate.order} has threshold_upper <= threshold "
                    f"({gate.threshold_upper} <= {gate.threshold})"
                )
        if not gate.kill_rule.strip():
            problems.append(
                f"gate {gate.order} has no kill_rule; a gate that never kills "
                "anything is not a gate"
            )
        if gate.metric in INTERFACE_METRICS and gate.state is GateState.SINGLE:
            problems.append(
                f"gate {gate.order} scores {gate.metric!r}, an interface metric, "
                "but declares state='single'; interface metrics need a complex"
            )
        expected = gate_cost_tier(gate.tool_keys)
        if expected != gate.cost_tier:
            problems.append(
                f"gate {gate.order} declares cost_tier={gate.cost_tier!r} but its "
                f"tools are {expected!r}"
            )

        # Framework section 6: no claimed design margin finer than the
        # evaluator's measured error. Fires only for metrics validated for the
        # tools THIS gate names, so it is inert until calibration lands.
        # `calibration.json` is a committed artifact this module does not
        # own: a validated record with a malformed `measured_error` (missing
        # or non-numeric `value`) is skipped rather than crashing the whole
        # brief validation on a KeyError/TypeError.
        errors_for_gate = [
            c["measured_error"]["value"]
            for c in calibration_for(gate.metric, gate.tool_keys).values()
            if c.get("status") == "validated"
            and isinstance(c.get("measured_error"), dict)
            and isinstance(c["measured_error"].get("value"), (int, float))
            and not isinstance(c["measured_error"].get("value"), bool)
        ]
        if errors_for_gate:
            err = max(errors_for_gate)
            if gate.operator == "between" and gate.threshold_upper is not None:
                window = gate.threshold_upper - gate.threshold
                # window <= 0 is an inverted/degenerate 'between', already
                # rejected by the shape check above -- piling a second,
                # nonsensical "negative window" message on top would also
                # feed the LLM repair loop with something it cannot fix.
                if 0 < window < 2 * err:
                    problems.append(
                        f"gate {gate.order} keeps a window of {window:g} on "
                        f"{gate.metric!r}, but its measured error is {err:g}; "
                        f"the window cannot be resolved"
                    )
            else:
                step = _decimal_step(gate.threshold)
                if step < err:
                    problems.append(
                        f"gate {gate.order} thresholds {gate.metric!r} at "
                        f"{gate.threshold:g}, quoted to {step:g}, but its "
                        f"measured error is {err:g}; the claimed margin is "
                        f"finer than the evaluator can resolve"
                    )

    ranks = [cost_rank(g.cost_tier) for g in gates]
    if ranks != sorted(ranks):
        problems.append(
            "the cascade is not ordered cheap-first: "
            + " -> ".join(f"{g.order}:{g.cost_tier}" for g in gates)
            + ". Expensive tools must only ever see candidates that already "
            "survived the cheap ones."
        )

    if not proto.decisive_gates():
        problems.append(
            "no gate is marked decisive: every gate tests whether the protein "
            "folds, none tests whether it does the thing that was asked for"
        )
    if not proto.ranking_expression.strip():
        problems.append("ranking_expression is empty; say how survivors are ordered")
    if not proto.known_limitations:
        problems.append(
            "known_limitations is empty; state what these scores do not tell you"
        )
    return problems
