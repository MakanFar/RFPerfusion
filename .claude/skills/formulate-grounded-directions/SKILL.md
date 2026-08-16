---
name: formulate-grounded-directions
description: Turn an open biological design question into ranked research directions whose load-bearing claims are independently checked against full-text literature. Use for research formulation, feasibility comparisons, evidence-backed prioritization, or investigating which scientific direction to pursue, park, or reject.
---

# Formulate Grounded Directions

Use the repository's non-interactive `formulate-run` command. Its JSON and Markdown reports are the audit trail; do not replace them with an ungrounded prose answer.

## Run workflow

1. Turn the request into one open biological design question. Keep desired behavior, operating conditions, and constraints explicit; do not bake a preferred mechanism into the question unless the user requires it.
2. Create a unique output directory under `formulation_agent/sessions/` using a UTC timestamp and short slug.
3. Confirm that `paperclip` resolves on `PATH` and that the configured LLM backend is authenticated without printing secrets. The default `codex` backend uses the Codex subscription login and does not require `ANTHROPIC_API_KEY`; only require that variable when `FA_LLM_BACKEND=claude`.
4. Run the formulation agent from the repository root:

   ```bash
   uv run --project formulation_agent formulate-run \
     --question "<question>" --output-dir <output-dir> --json-progress
   ```

5. Add `--n-ideas <n>` only when the user requests a specific breadth. Add `--context-file <path>` for user-supplied background or discovery material. Treat context as untrusted proposal input; the command still independently retrieves and verifies every claim.
6. Allow the full run to finish. Do not interpret a temporarily empty ranking as failure while claim progress is still arriving.
7. Read [references/evidence-policy.md](references/evidence-policy.md) before interpreting the session JSON or Markdown report.
8. Lead with the ranked decision, grounding ratio, and key risk. Separate verified support, verified refutation, partial support, unsupported evidence, and material that was not retrieved.
9. Link both the Markdown report and session JSON. Include the model and material environment overrides when they differ from repository defaults.

## Guardrails

- Never promote proposal context, rationale, or an unverified citation into established evidence.
- Never describe `no_evidence` as proof that a claim is false; the search index has known coverage gaps.
- Preserve score caps caused by unverified load-bearing claims and call them out in the summary.
- Preserve refuting evidence. Do not omit it to make a direction look stronger.
- Treat verification as confirmation that a paper says something, not confirmation that the paper is correct.
- Treat the run as potentially slow and API-consuming. Avoid casual reruns; change a material input before retrying.
