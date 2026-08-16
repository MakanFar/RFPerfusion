---
name: implement-constraint
description: Implement, calibrate, and register a custom proto-language constraint that scores a sequence against a target property no shipped constraint measures. Use when a design objective needs a scoring function that does not exist yet — a predicted melting or transition temperature, a bespoke activity or specificity proxy, a domain-specific quality gate.
---

# Implement Constraint

A constraint maps a sequence to a scalar cost. Writing one is mechanical; making it trustworthy is not. A constraint that has not been measured against held-out ground truth is an opinion, and must never gate a design run as though it were a measurement.

## Run workflow

1. Search the shipped constraints first. Read `proto_language/constraint/constraint_registry.py` and the category directories. Implementing a duplicate of an existing constraint is a defect, not a contribution.
2. State in one sentence what physical or biological quantity the constraint measures, and in a second sentence what it actually computes. When those differ, the constraint is a proxy and every downstream report must say so.
3. Read [references/constraint-contract.md](references/constraint-contract.md) for the function signature, the scoring direction, and the metadata shape.
4. Implement the scoring function. Return 0.0 when the target is satisfied and 1.0 when maximally violated, with a smooth ramp between. Emit namespaced metadata carrying the raw predicted quantity in its natural units, not only the normalized cost.
5. Write a known-answer test before calibrating. Assert the direction on one clearly-satisfying and one clearly-violating input. An inverted constraint optimizes for the opposite of the objective and produces plausible-looking results, so this test is not optional.
6. Assemble a labeled dataset with measured values for the quantity. Split it into calibration and held-out sets. Never fit and evaluate on the same records.
7. Fit any calibration on the calibration set only, then measure error on the held-out set. Report mean absolute error in the quantity's natural units, the record count, and the range covered.
8. Record the measured reliability on the constraint — benchmark name, error, and n — so every downstream score can carry it.
9. Apply the resolution gate. If held-out error is larger than the design tolerance the constraint is meant to enforce, the constraint may not be used as a hard gate. Widen the stated tolerance to match measured error, state the widened claim plainly, and continue with it as a soft weight.
10. Register the constraint and confirm it resolves by key from a program before wiring it into a real run.

## Report results

- Lead with what the constraint measures, what it computes, and whether those are the same thing.
- Report held-out error, record count, and the value range the benchmark covered. A constraint validated only near one value cannot be trusted away from it.
- State the resolution gate outcome explicitly: hard gate, or soft weight with a widened tolerance.
- Show at least one candidate the constraint rejects and why. A constraint that rejects nothing is untested.
- Link the calibration data, the split, and the test file.

## Guardrails

- Never gate a design run on an uncalibrated constraint. Without held-out error there is no basis for a threshold.
- Never report a proxy under the name of the quantity it proxies. A free-energy change is not a transition temperature; label the substitution everywhere it appears.
- Never extrapolate a reported error beyond the range the benchmark covered.
- Never fit on records that appear in the held-out set, including near-duplicates and variants of the same parent.
- Never let a constraint silently return a constant. Assert that it produces a spread across a candidate batch.
- Keep the function deterministic under a fixed seed. A stochastic constraint makes an optimization run unreproducible and its results undefendable.
- Preserve refuting benchmark results. A poor error figure is a finding to report, not a reason to re-split the data.

## Reference

Read [references/constraint-contract.md](references/constraint-contract.md) for the signature, normalization patterns, metadata shape, and registration.
