# Constraint Contract

## Shape

A constraint is a callable plus a config, wired into a program through the `Constraint` wrapper:

```python
Constraint(
    inputs=[segment],
    function=my_constraint_fn,
    function_config={"target": 41.0, "tolerance": 0.5},
)
```

In declarative JSON the same thing is a registry key plus config:

```json
{ "key": "my-constraint", "targets": ["<segment-id>"], "config": { "target": 41.0 } }
```

## Scoring direction

**0.0 = satisfied. 1.0 = maximally violated.** The optimizer minimizes the weighted sum of all active constraints, so a constraint that returns high scores for good sequences will drive the search away from the objective while producing output that looks entirely normal.

Assert the direction with a known-answer test before calibrating anything:

```python
assert my_constraint_fn(known_good, cfg)["score"] < 0.1
assert my_constraint_fn(known_bad, cfg)["score"] > 0.9
```

## Normalization patterns

Raw predictions arrive in natural units and must be mapped into [0, 1].

**Target with tolerance** — a value that should land inside a window:

```python
deviation = abs(predicted - target)
score = min(1.0, max(0.0, (deviation - tolerance) / scale))
```

Zero cost inside the tolerance band, ramping to full cost at `tolerance + scale`.

**One-sided threshold** — a value that must clear a floor:

```python
score = 0.0 if predicted >= floor else min(1.0, (floor - predicted) / scale)
```

Choose `scale` so the ramp spans a range the optimizer can actually traverse. A step function gives the search no gradient to follow and degenerates into rejection sampling.

## Metadata

Return the normalized score *and* the raw quantity. Downstream ranking, uncertainty reporting, and out-of-distribution flagging all need the natural-unit value, and a score alone throws it away.

```python
{
    "score": 0.18,
    "data": {
        "predicted_value": 41.4,
        "unit": "celsius",
        "confidence": 0.61,
        "ood": False,
        "method": "<what actually computed this>",
    },
}
```

Namespace metadata under the constraint's own key so multiple constraints do not collide. The shipped constraints read back as `sequence._constraints_metadata["<key>"]["data"][...]`.

## Recording reliability

Attach measured error to the constraint so every score it produces can carry it:

```json
"known_reliability": { "benchmark": "<name>", "mae": 2.1, "unit": "celsius", "n": 12 }
```

This is the field that separates a calibrated predictor from a plausible number. Anything reported without it should be labeled as uncalibrated.

## The resolution gate

A predictor cannot enforce a tolerance finer than its own error. If held-out error exceeds the design tolerance:

- Do not use the constraint as a hard gate.
- Widen the stated tolerance to at least the measured error.
- State the widened claim in every report that uses the constraint.

A calibrated negative result is a legitimate outcome and is more defensible than a precise claim the benchmark does not support.

## Out-of-distribution flagging

A predictor calibrated on one region of sequence space says nothing reliable outside it. Compare each candidate to the calibration set — embedding distance or identity to the nearest calibration record works — and set `ood: true` when it falls outside. Flagged predictions should be displayed and excluded from ranking rather than silently trusted.

## Registration

Constraints register through the decorator pattern used across `proto_language/constraint/`. Follow the nearest existing constraint in the matching category directory for the exact import and decorator form, then confirm the key resolves from a program before wiring it into a run.

## Testing checklist

- Direction asserted on known-good and known-bad inputs.
- Non-constant across a real candidate batch.
- Deterministic under a fixed seed.
- Config validation rejects contradictory settings rather than silently picking one.
- Held-out error measured, recorded, and reported with its record count and value range.
