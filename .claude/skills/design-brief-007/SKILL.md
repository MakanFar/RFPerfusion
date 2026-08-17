---
name: design-brief-007
description: Turn a protein design question into a buildable brief — shard decomposition, a Paperclip mining concept and plan, an assembly recipe, and a proto-tools fitness cascade with numeric thresholds. Use when the user wants to know what to build and how to score it, needs candidate sequences sourced from literature and stitched into constructs, or asks for a computational design loop, screening cascade, or fitness criteria for a protein.
---

# Design Brief 007

Use the repository's non-interactive `formulate007-run` command. Its emitted files are the hand-off contract to three downstream consumers; do not replace them with a prose plan of your own.

This skill answers *what do we build, what do we go read, and what number kills a bad design*. It does not rank directions by evidence — that is `formulate-grounded-directions`. Nothing this skill produces is literature-verified.

## Run workflow

1. Turn the request into one protein design question. Keep the target function, the stimulus or operating condition, and any hard constraints explicit. Do not bake a mechanism into the question unless the user requires one; choosing the pathway is the agent's first and highest-judgement call.
2. Create a unique output directory under `formulation_agent007/briefs/` using a UTC timestamp and short slug.
3. Confirm the configured LLM backend is authenticated without printing secrets. The default `codex` backend uses the Codex subscription login. `FA7_LLM_BACKEND=claude` uses the Claude Code subscription login. Neither requires `ANTHROPIC_API_KEY`, and the agent strips that variable from its child processes on purpose — do not set it to try to fix an auth failure.
4. Run from the repository root:

   ```bash
   uv run --project formulation_agent007 formulate007-run \
     --question "<question>" --output-dir <output-dir> --json-progress
   ```

5. Add `--context-file <path>` for user-supplied background. Treat that context as untrusted framing input: it can influence which pathway is chosen, and the emitted brief still carries no evidentiary weight.
6. Allow all six stages to finish. A `repairing (N problems)` progress event is the validators working, not a failure.
7. Read `validation_warnings` in the brief JSON **before** reading anything else. They are problems that survived a repair attempt, and they are reprinted at the bottom of the Proto runbook where the downstream agent will act on them.
8. Read [references/handoff-contract.md](references/handoff-contract.md) before interpreting or forwarding the emitted files.
9. Report, in this order: the chosen pathway and why; what was excluded and whether it was excluded as wrong or merely as unsimulable; the step the toolchain cannot score; the shards; the gate table with its thresholds; and any validation warnings. Link every emitted file.

## Hand-off

The brief is an input to three other workflows. Do not perform their work inside this skill.

- Literature mining: run the emitted `run_literature.sh` from the repository root, or use `mine-literature-from-concept` with the emitted concept and plan. It runs the litkb chain (default: typed evidence, tool-bound sequences) followed by the paperclip_kb.py grep commands (alternative: no LLM read quota, dry run first). The emitted plan is already validated against `paperclip_kb.validate_plan`, so pass it with `--plan-file` rather than letting the script re-plan.
- Sequence extraction: hand `harvest_<slug>.md` to the Paperclip agent.
- Scoring: hand `proto_brief_<slug>.md` to `proto-tools`.

## Guardrails

- Never present a brief as evidence. No claim in it has been checked against literature, and sequences harvested downstream inherit `evidence_status: discovery_only_unverified` from the mining manifest.
- Never edit an emitted artifact to clear a validation warning. Fix the input and rerun, or report the warning as it stands.
- Never substitute a different tool when a key in the cascade does not resolve in the live proto-tools catalogue. The allowlist checks spelling, not availability. Stop and report the unresolved key.
- Never reorder the cascade. It is ordered cheap-first so expensive tools only see candidates that survived cheap ones; reordering inverts the compute budget.
- Never run the cascade from this skill. Deployment and execution on Modal are billable and need explicit user approval, which is `proto-tools`' workflow to obtain.
- Preserve the excluded pathways and the simulability note in any summary. The unscoreable step is the most important sentence in the brief and the easiest one to drop.
- Treat thresholds as defensible starting points, not calibrated values. They come from a model asked to defend them, not from a benchmark on the user's target class.
- Treat a run as slow and subscription-consuming: six staged calls plus repairs. Change a material input before rerunning.
