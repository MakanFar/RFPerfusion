---
name: write-program
description: Author a proto-language design program that searches sequence space under multiple weighted constraints. Use for protein or nucleotide design runs that require iterative optimization — mutation scanning, multi-objective sequence design, directed evolution, scaffold engineering, or any request to "design", "optimize", or "evolve" a sequence toward a target property.
---

# Write Program

Author a declarative proto-language program, validate it, then execute it. A design run is a search over many rounds; express it as a program the optimizer executes, never as an agent loop that calls tools one at a time.

## Run workflow

1. Restate the design objective as one sentence naming the scaffold, the region under design, and the target property. If the objective has no scoring function that can measure it, say so and stop; a program cannot optimize what nothing scores.
2. Read [references/program-contract.md](references/program-contract.md) before writing any keys.
3. Resolve every generator, constraint, and optimizer key against the proto-language registries (`proto_language/generator/generator_registry.py`, `proto_language/constraint/constraint_registry.py`). Never guess a key from a model name or a paper title. If a required constraint does not exist, stop and use the `implement-constraint` skill before continuing.
4. Create a run directory under `proto/programs/<run-id>/`, where `<run-id>` starts with a UTC timestamp and ends with a short slug.
5. Author `program.json` in the declarative form. Use Python only when a construct cannot be expressed in JSON, and say which construct forced it.
6. Declare immutable regions explicitly. Positions that must not change belong in the generator's `masking_strategy.fixed_positions` as a 1-indexed list, not in a prose instruction.
7. Order the optimization stages cheapest-first: sequence-composition and identity constraints before structure prediction, structure prediction before interface scoring. Every candidate a cheap stage rejects is a GPU-hour not spent.
8. Tie each constraint's configured numbers to their source. Record the originating `EvidenceItem` id, benchmark, or measurement in the constraint's description field. A threshold with no provenance is a guess and must be labeled as one.
9. Validate the program without GPU work before any real run. Confirm the registry resolves every key and the segment wiring parses.
10. Execute with the `proto-tools` skill's Modal backend. Report the funnel — proposed, passing hard constraints, surviving — not only the winners.

## Report results

- Lead with the funnel counts and the top candidates, and link `program.json` beside them.
- Name every hard constraint that rejected candidates, with how many each rejected. A constraint that never rejects anything is not doing work and should be reported as such.
- Report the optimizer, step count, and actual backend.
- State which configured thresholds were evidence-backed and which were assumed.
- Keep generated artifacts under `proto/outputs/`, which is intentionally gitignored. Keep `program.json` under `proto/programs/`, which is not.

## Guardrails

- Never implement a design loop by calling a tool repeatedly from the conversation. Iterative search belongs in the optimizer, where it is reproducible and does not consume model context.
- Never invent a registry key. An unresolvable key is a stop condition, not a naming problem to solve creatively.
- Never promote a constraint sourced from contested or speculative evidence to a hard gate. Soft weight only.
- Never describe a structure-confidence score as a measurement of stability, activity, or function. It measures the predictor's confidence in its own output.
- Preserve the program that produced a result. A candidate set without its program is not reproducible and cannot be defended.
- Treat every execution as billable. Change a material input before rerunning.

## Reference

Read [references/program-contract.md](references/program-contract.md) for the JSON structure, the primitive definitions, and optimizer selection.
