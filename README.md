# RFPerfusion

RFPerfusion combines project design documents, literature-search tooling, and a Modal-backed proto-tools integration.

## Repository layout

- `docs/` — project requirements and design notes.
- `litterature_search_from_concept/` — the existing literature-search workflow.
- `proto/` — the isolated uv runtime for proto-tools. Generated results go to the gitignored `proto/outputs/` directory.
- `.claude/skills/proto-tools/` — instructions that teach Claude and compatible agents how to discover, deploy, and run proto-tools.
- `.agents` — a symlink to `.claude`, so the same skill works with agents that use either convention.
- `.mcp.json` — the project-scoped MCP server configuration.

## Proto-tools setup

From the repository root:

```bash
uv sync --project proto
uv run --project proto modal setup
```

Restart Claude Code, approve the project MCP server, and use `/mcp` to confirm that `proto-tools` is connected. See the skill's [setup reference](.claude/skills/proto-tools/references/setup.md) for deployment and troubleshooting details.
