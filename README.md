# RFPerfusion

A literature-grounded agentic pipeline that designs a **SWIR-actuated protein
thermal switch** — novel engineered **TlpA** variants whose coiled-coil transition
midpoint is tuned to ~41 °C, so they can be flipped by the tiny, localized heating
that >1500 nm (SWIR) light produces in water. See [`docs/PRD.md`](docs/PRD.md).

The judged artifact is the **sequence set** (`outputs/candidates.json`); the
pipeline is *how we got there*.

## Quick start

```bash
uv run design.py --offline     # run the pipeline (skips live Paperclip searches)
uv run design.py               # full run with real Paperclip literature searches
```

Outputs land in `outputs/`:
- `design_record.json` — the orchestrator's single source of truth (PRD §6.1)
- `candidates.json` — the ranked top-5 novel variants (the judged artifact)

## Architecture

Deterministic orchestrator (the DAG in code) → each stage is a pure typed
function `f(in) -> out`. The LLM-driven orchestrator + agent workers wrap these
same functions later; control flow and data contracts do not change.

```
design.py → orchestrator.run()
  1 formulate   goal            → DesignRecord v0        (config-driven)
  2 literature  sub-questions   → EvidenceItem[]         [Paperclip]  ← L1 negative result + redirect
  3 scaffold    resolve TlpA    → sequence + DBD bounds  [Paperclip /proteins/]
  4 generate    DesignRecord    → Candidate[]            [heuristic | Proto ESM2→Modal]
  5 evaluate    Candidate[]     → ScoredCandidate[]      [free checks + Proto ESMFold/PyRosetta→Modal]
  6 rank        by ci_low       → top-5
  7 report      console + JSON artifacts
```

### Layout
```
src/rfperfusion/
  schemas.py      frozen DTOs (PRD §6): DesignRecord, EvidenceItem, Constraint, ScoredCandidate
  config.py       design target, sub-questions, constraint set
  orchestrator.py the deterministic DAG
  tools/
    paperclip.py  CLI bridge (literature + protein DB)
    proto.py      isolated proto-tools/Modal bridge (discovery free; execution guarded + billable)
  stages/         one file per stage
formulation_agent/                open design question → ranked, claim-verified research directions
formulation_agent007/             design question → shards, mining plan, assembly recipe, scoring cascade
litterature_search_from_concept/  concept → broad Paperclip corpus + categorized knowledge base
proto/            isolated proto-tools MCP runtime (uv, py3.12) — Modal-backed heavy compute
outputs/          generated artifacts (gitignored)
```

## Agent skills

Seven skills in `.claude/skills/` cover the pipeline end to end. `.agents` is a
symlink to `.claude`, so the same definitions work with either convention, and
each skill ships an `agents/openai.yaml` for the Codex backend.

| Skill | Stage | Role |
|---|---|---|
| `formulate-grounded-directions` | 0 | Ranked research directions with claim-level literature verification |
| `design-brief-007` | 1 | Design question → shards, a mining plan, an assembly recipe, and a scoring cascade |
| `mine-literature-from-concept` | 2 | Concept → broad Paperclip corpus and categorized knowledge base |
| `write-program` | 3–5 | Author a proto-language design program — iterative search under weighted constraints |
| `implement-constraint` | 4 | Implement, calibrate, and register a scoring function that does not ship with Proto |
| `proto-tools` | infra | Single tool invocations against the proto-tools catalogue on Modal |
| `visualize-sequence-design` | demo | Compare input and designed sequences and visualize the differences |

**Scope boundary.** `proto-tools` covers *one model, one input, one result*.
Iterative design — propose, score, select, repeat — belongs in `write-program`,
where the search runs in an optimizer rather than as an agent loop. A missing
scoring function goes to `implement-constraint` first.

### Installing the skills as a plugin

The repo doubles as a local plugin marketplace, so the skills load outside this
directory (Claude Desktop chat, other projects) as well as inside it:

```bash
claude plugin marketplace add .
claude plugin install rfperfusion@rfperfusion
```

Installed skills are a **snapshot**, not a live link. After editing any skill:

```bash
claude plugin marketplace update rfperfusion
```

Inside this repo the skills load live from `.claude/skills/` at project scope
and need no install.

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

## Tools

| Tool | Role | Cost |
|---|---|---|
| **Paperclip** | Literature (L1–L4) + resolve TlpA sequence | free (laptop) |
| **Proto** (`proto-tools`→Modal) | ESM2 generation, ESMFold/PyRosetta/DSSP scoring | **billable**; per-tool deploy approval required |
| Claude Agent SDK *(next)* | LLM orchestrator + isolated agent workers | — |

`.mcp.json` holds the project-scoped MCP server configuration for `proto-tools`.

**Guardrails:** `tools.proto.run_tool` refuses to execute unless `allow_deploy=True`
— a first run of an undeployed tool triggers a billable Modal deploy. The pipeline
never fabricates ESMFold/PyRosetta numbers; unresolved scores are flagged
`pending_modal`.

## Status (POC v0)

- ✅ Runs end-to-end; 4 demo beats print; artifacts written
- ✅ Frozen schemas, deterministic orchestrator, tool bridges
- ✅ L1 negative result → photothermal redirect assembled into the Design Record
- ✅ Skills cover all pipeline stages; installable as a plugin
- 🔜 Real TlpA sequence resolution (in progress) → unblocks real variant generation
- 🔜 Real Proto ESM2 generation + ESMFold/PyRosetta scoring (Modal, needs deploy approval)
- 🔜 Piraner held-out Tm benchmark (the M3 go/no-go gate)
- 🔜 LLM-orchestrator + agent workers on top of the stage functions
