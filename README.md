# RFPerfusion

An agentic pipeline that turns an underspecified protein design question into
evidence-grounded, computationally evaluable candidates — and says plainly what
it could not check.

Two documents define it. [`docs/PRD-framework.md`](docs/PRD-framework.md) is the
framework: ideation → falsification → specification → generation → evaluation,
with a mandatory human gate at spec approval.
[`docs/PRD-(outdated).md`](<docs/PRD-(outdated).md>) is instance #1, the
SWIR-actuated **TlpA** thermal switch, kept because its data contracts (§6) are
still the ones the code implements.


```bash
FA7_LLM_BACKEND=claude uv run --project formulation_agent007 formulate007-run \
  --question "Design a protein that changes conformation in response to radiofrequency fields" \
  --output-dir formulation_agent007/briefs/rf-switch --json-progress
```

Emits a concept file, a validated `plan_<slug>.json`, a per-shard harvest
contract, and a runbook whose every gate names a real proto-tools key, a real
metric, and a number. Six staged LLM calls; treat a rerun as expensive.
Backends: `claude` (Claude Code login) or `codex` (default; needs the `codex`
CLI). Neither uses `ANTHROPIC_API_KEY`.
Details: [formulation_agent007/README.md](formulation_agent007/README.md).

### 2 — Literature

Two consumers of the same brief plan, with different outputs.

`mine-literature-from-concept` runs `paperclip_kb.py` and produces a categorized
grep knowledge base for a human to read.

`litkb` reads full text with an LLM and produces typed `EvidenceItem` records
plus sequence artifacts checked against the proto-tools constraint table. It
takes the brief's flat plan directly:

```bash
cd litterature_search_from_concept
uv run --project . python -m litkb plan-adopt <brief>/plan_<slug>.json \
    --objective "<question>" --slug <slug> --output-dir outputs/<run>
uv run --project . python -m litkb search  outputs/<run>/plan_<slug>.json -n 4 --output-dir outputs/<run>
uv run --project . python -m litkb screen  outputs/<run>/search_<slug>.json -n 1 --output-dir outputs/<run>
```

`-n` is the cost lever: `screen` and `dig` are LLM passes over full text, capped
at 100 map operations per day by Paperclip. Then `dig` → `bind` → `evidence` →
`report` → `manifest`. Every run declares
`evidence_status: discovery_only_unverified`.
Contract: [.claude/skills/litkb/references/output-contract.md](.claude/skills/litkb/references/output-contract.md).

### 3 — Scoring

`proto-tools` runs one model on one input. `write-program` runs the iterative
search. `implement-constraint` builds a scoring function that does not ship.

Discovery is free and local. Execution on Modal is **billable** and needs
`modal token new` first; `registry/proto_catalog.json` is the generated
constraint table `litkb bind` checks sequences against.

## Skills

Nine skills in `.claude/skills/`. `.agents` symlinks to `.claude`, so both
conventions work, and each skill ships an `agents/openai.yaml` for Codex.

| Skill | Role |
|---|---|
| `formulate-grounded-directions` | Ranked research directions with claim-level verification |
| `design-brief-007` | Question → shards, mining plan, assembly recipe, fitness cascade |
| `mine-literature-from-concept` | Concept → Paperclip corpus + categorized knowledge base |
| `litkb` | Concept → typed evidence + proto-runnable sequence artifacts |
| `paperclip` | Full-text search over papers, trials, and regulatory documents |
| `write-program` | Proto-language design program — search under weighted constraints |
| `implement-constraint` | Implement, calibrate, register a missing scoring function |
| `proto-tools` | Single tool invocations against the proto-tools catalogue |
| `visualize-sequence-design` | Compare an input and a designed sequence |

**Scope boundary.** `proto-tools` is one model, one input, one result. Iterative
design belongs in `write-program`. A missing scoring function goes to
`implement-constraint` first.

### As a plugin

```bash
claude plugin marketplace add .
claude plugin install rfperfusion@rfperfusion
claude plugin marketplace update rfperfusion   # after editing any skill
```

Installed skills are a snapshot. Inside this repo they load live from
`.claude/skills/` and need no install.

## Layout

```
.claude/skills/                   nine agent skills (.agents → .claude)
docs/                             PRD-framework (the loop), PRD-(outdated) (instance #1)
formulation_agent/                open question → ranked, claim-verified directions
formulation_agent007/             question → shards, mining plan, cascade; briefs/ holds runs
litterature_search_from_concept/  paperclip_kb.py (grep) + litkb/ (typed); outputs/ holds runs
proto/                            isolated proto-tools MCP runtime (uv, py3.12); outputs/ gitignored
registry/proto_catalog.json       generated proto-tools constraint table
```

## Formulation agent

```bash
export FA_LLM_BACKEND=claude              # or: codex
uv run --project formulation_agent formulate-web
```

Opens a local browser UI; `formulate` is the terminal equivalent.
Details: [formulation_agent/README.md](formulation_agent/README.md).

## Tools

| Tool | Role | Cost |
|---|---|---|
| **Paperclip** | Full-text literature; protein/structure records | free; 100 LLM map operations per day |
| **proto-tools** → Modal | Generation, folding, scoring | **billable**; per-tool deploy approval |

`.mcp.json` holds the project-scoped MCP configuration for `proto-tools`.

**Guardrails.** Nothing fabricates a score: an unresolved evaluation is reported
as unresolved. Literature output is discovery, never verified evidence. A
`litkb` artifact accepted by a proto tool passed a *schema* check — molecule,
alphabet, length — not a run.

## Status

- ✅ Design brief → literature → evidence runs end to end, artifact to artifact
- ✅ Frozen data contracts (PRD §6); nine skills; installable as a plugin
- ✅ TlpA resolved to UniProt `A0A0H3P187`, 371 aa (AlphaFold mean pLDDT 82.9)
- ⚠️ `litkb bind` can mark an artifact runnable against only one catalogue tool
  (`esmfold-prediction`); every other entry lacks parseable constraints and
  returns `unverified`
- ⚠️ Paperclip's specialised `map` workers are gated on this account, so both
  literature passes run `quick-reader`; supplement-borne sequences are out of reach
- 🔜 Modal authentication → generation and the GPU gates in the cascade
- 🔜 Piraner held-out Tm benchmark — the calibration gate
- 🔜 LLM orchestrator over the stage functions
