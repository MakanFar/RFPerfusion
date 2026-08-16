# RFPerfusion

RFPerfusion combines project design documents, literature-search tooling, and a Modal-backed proto-tools integration.

## Repository layout

- `docs/` — project requirements and design notes.
- `litterature_search_from_concept/` — the existing literature-search workflow.
- `formulation_agent/` — turns an open design question into ranked research directions, with every claim verified against full-text literature. Browser UI or terminal; see its [README](formulation_agent/README.md).
- `formulation_agent007/` — turns a protein design question into a build plan: shard decomposition, a Paperclip mining concept and plan, an assembly recipe, and a proto-tools fitness cascade with numeric thresholds. See its [README](formulation_agent007/README.md).
- `proto/` — the isolated uv runtime for proto-tools. Generated results go to the gitignored `proto/outputs/` directory.
- `.claude/skills/proto-tools/` — instructions that teach Claude and compatible agents how to discover, deploy, and run proto-tools.
- `.claude/skills/mine-literature-from-concept/` — broad concept-to-corpus literature reconnaissance with reproducible artifacts.
- `.claude/skills/formulate-grounded-directions/` — ranked research formulation with claim-level literature verification.
- `.claude/skills/design-brief-007/` — protein design question to a buildable brief: shards, mining plan, assembly recipe, scoring cascade.
- `.agents` — a symlink to `.claude`, so the same skill works with agents that use either convention.
- `.mcp.json` — the project-scoped MCP server configuration.

## Formulation agent

From the repository root:

```bash
codex login                                # one-time subscription sign-in
export FA_LLM_BACKEND=codex                # default; or: claude
uv run --project formulation_agent formulate-web
```

Opens a local browser UI. `formulate` runs the same engine in the terminal.
For Claude, run `claude auth login` once and set `FA_LLM_BACKEND=claude`.
Details, guarantees and known corpus limitations: [formulation_agent/README.md](formulation_agent/README.md).

## Design brief agent (007)

```bash
uv run --project formulation_agent007 formulate007-run \
  --question "Design a protein that changes conformation in response to radiofrequency fields" \
  --output-dir formulation_agent007/briefs/rf-switch
```

Emits a `concept_<slug>.txt` and reviewed `plan_<slug>.json` that drop straight
into `paperclip_kb.py`, an extraction contract for the Paperclip agent, and a
runbook for the Proto agent whose every gate names a real proto-tools key, a
real metric, and a number. Details: [formulation_agent007/README.md](formulation_agent007/README.md).

## Proto-tools setup

From the repository root:

```bash
uv sync --project proto
uv run --project proto modal setup
```

Restart Claude Code, approve the project MCP server, and use `/mcp` to confirm that `proto-tools` is connected. See the skill's [setup reference](.claude/skills/proto-tools/references/setup.md) for deployment and troubleshooting details.
