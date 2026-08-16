---
name: proto-tools
description: Discover, deploy, and run computational-biology and biological-AI tools through proto-tools on the user's Modal workspace. Use for protein or nucleotide generation, structure prediction or design, inverse folding, sequence scoring or alignment, docking, annotation, dynamics, database retrieval, and other requests that may be served by the proto-tools catalogue.
---

# Proto Tools on Modal

Use the `proto-tools` MCP server as the machine interface. Keep tool selection, schemas, execution, and results structured; do not generate ad hoc Python unless the MCP server cannot express a required operation.

## Scope boundary

This skill covers **single tool invocations** — one model, one input, one result. Fetching a record, predicting a structure, scoring a known sequence, benchmarking a fixed candidate set.

It does not cover **iterative design**. When the request requires proposing candidates, scoring them, selecting survivors, and repeating, do not loop `run_tool` from the conversation. That search belongs in an optimizer, where it is reproducible, runs without consuming model context, and does not spend one model round-trip per candidate.

- Iterative search over many rounds → use the `write-program` skill.
- A scoring function that does not exist in the catalogue → use the `implement-constraint` skill.
- Everything else → continue here.

The prohibition on ad hoc Python above applies to substituting hand-written code for an available tool call. It does not apply to authoring a proto-language program, which is the supported way to express a design run.

## Run workflow

1. Call `workspace_info` before the first operation in a session. If credentials or the Modal environment are unavailable, read [references/setup.md](references/setup.md) and report the exact failing prerequisite.
2. Resolve the capability with `search_tools(deployed_only=true)`. If no suitable deployed tool exists, repeat with `deployed_only=false` to search the deployable catalogue. Use `list_tools` only when browsing a category or checking deployment state. Never guess a tool key from a model name.
3. Call `get_tool_schema` before `run_tool`, even when the fields look familiar. Use `get_tool_example` when the schema or a structure input is nontrivial.
4. Confirm that the selected tool actually measures or produces what the user requested. State important scientific limitations rather than treating every output as ground truth.
5. If the tool is not deployed, explain the deployment and persistent-storage cost and obtain explicit approval before calling `deploy_tool`. Deploy only the needed tool into `main`; never deploy the full catalogue.
6. Create an absolute output directory under `proto/outputs/<run-id>/`, where `<run-id>` starts with a UTC timestamp and ends with the tool key. Pass it as `output_dir` to `run_tool`.
7. Run on the session's Modal backend. Use `run_on="local"` only when the user asks for local execution or a small CPU-only operation clearly benefits from it.
8. On failure, preserve the returned error, correct schema or deployment problems, and retry at most once for a transient deployment/download failure. Do not repeatedly spend compute without new evidence.
9. Call `get_tool_info` for completed scientific runs so the method, citation, and implementation are attributable.
10. Save sanitized `request.json` and `result.json` files beside generated artifacts when they add reproducibility. Never write credentials or gated-model tokens into them.

## Report results

- Lead with the scientific result and whether the call succeeded.
- Report the tool key, actual `ran_on` backend, material config choices, and citation.
- Summarize compact JSON or text inline.
- Link every returned artifact using its absolute local path.
- Display returned images when useful.
- For PDB/mmCIF files, link the structure and display a returned preview image when one exists. Do not claim that a preview is an analytical validation.
- For embeddings or other large arrays, report shape, dtype, and useful summary statistics; do not paste the array into the conversation.
- Keep generated files under `proto/outputs/`, which is intentionally gitignored.

## Guardrails

- Treat Modal deployment and execution as billable actions.
- Never implement an optimization loop by repeatedly calling `run_tool`. Hand the search to `write-program` instead.
- Keep the environment fixed to `main` unless the user explicitly chooses another environment.
- Never expose `~/.modal.toml`, tokens, gated-model credentials, or secret values.
- Do not bypass gated-model licenses. Explain the required acceptance or secret setup.
- Do not treat an unvalidated computational score as experimental evidence or a calibrated ranking signal.
- Prefer file paths or HTTPS URLs for supported bulky structure inputs instead of inserting coordinates into a tool call.

## Setup reference

Read [references/setup.md](references/setup.md) only for installation, authentication, MCP connection, environment, deployment, or troubleshooting work.
