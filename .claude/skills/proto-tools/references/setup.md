# Proto Tools setup

Use this reference only when installing, authenticating, deploying, or troubleshooting the project integration.

## Architecture

The project-scoped `.mcp.json` starts `proto-tools-mcp` through the isolated uv project in `proto-skill/`. The MCP process runs locally, uses the user's local Modal credentials, dispatches supported work to the `main` Modal environment, and materializes large returned values under the `output_dir` supplied by the agent.

The Modal dashboard URL `https://modal.com/apps/andrii-86352/main` identifies the workspace's `main` environment. It is not one universal proto-tools app. Proto-tools deploys supported tool apps individually.

## One-time installation and authentication

Run from the repository root:

```bash
uv sync --project proto-skill
uv run --project proto-skill modal setup
```

`modal setup` opens a browser authentication flow and writes credentials to `~/.modal.toml`. Never read, print, copy, or commit that file.

Confirm access without exposing credentials:

```bash
uv run --project proto-skill modal profile current
uv run --project proto-skill modal environment list
```

The environment should include `main`. Do not create a duplicate `proto-env` merely because it is the upstream default; this project deliberately targets the existing `main` environment through `MODAL_ENVIRONMENT=main` in `.mcp.json`.

Restart Claude Code after first installation, approve the project-scoped MCP server, and use `/mcp` to confirm that `proto-tools` is connected. Project MCP servers require a one-time trust decision.

## Manual verification

Probe the server without starting an interactive protocol session:

```bash
uv run --project proto-skill proto-tools-mcp --help
uv run --project proto-skill proto-tools agent-context
MODAL_ENVIRONMENT=main uv run --project proto-skill proto-tools doctor --json
uv run --project proto-skill proto-tools deploy --list
```

Inside Claude, call `workspace_info`, then `list_tools` or `search_tools`.

## Deploying a tool

Prefer the MCP `deploy_tool` operation because it elicits approval. For manual deployment, first inspect the deployable app names:

```bash
uv run --project proto-skill proto-tools deploy --list
uv run --project proto-skill proto-tools deploy --apps <app-name> --env main
```

Deploy one needed app at a time. Deployment builds an image and runs a smoke invocation. Both can incur cost, and downloaded weights persist in Modal storage until removed.

Some tools require accepting upstream licenses and configuring gated credentials such as a Hugging Face token. Follow the tool's upstream gated-model instructions; never place secrets in this repository or in MCP arguments.

## Cost and warm-container behavior

The MCP configuration sets `PROTO_MODAL_SCALEDOWN_WINDOW=30`, matching the upstream default. Raising it keeps a warm model available for repeated interactive calls but bills for longer idle GPU time. Change it only when the user knowingly chooses that tradeoff.

Do not deploy every tool. Remove unused deployments and cached weights through Modal when their ongoing storage is no longer wanted.

## Troubleshooting

- Missing credentials: run `uv run --project proto-skill modal setup` interactively.
- Workspace uncertainty: run the `proto-tools doctor --json` command above; it reports authentication, workspace, environment, and deployed-app count without running a biology tool.
- MCP not listed: restart Claude Code, inspect `/mcp`, and approve the project server.
- Server fails to start: run `uv sync --project proto-skill`, then run the MCP `--help` probe above.
- Wrong environment: inspect `workspace_info` and `.mcp.json`; do not silently deploy elsewhere.
- Tool not found: use `search_tools` and `get_tool_schema`; tool keys use `<model>-<action>` rather than bare model names.
- Tool not deployed: request approval and deploy only its mapped app.
- First call is slow: expect image startup, environment construction, model loading, or weight download.
- Deployment/download failure: retry once. If it fails again, preserve the error and stop.
- Large result absent from chat: inspect the returned local file paths under the supplied `output_dir`.

## Upstream references

- Proto-tools Modal setup: https://github.com/evo-design/proto-tools/blob/main/proto_tools/modal/README.md
- Proto-tools repository: https://github.com/evo-design/proto-tools
- Modal environments: https://modal.com/docs/guide/environments
- Claude Code MCP configuration: https://code.claude.com/docs/en/mcp
