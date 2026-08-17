<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo/resolve-wide-dark.svg">
    <img src="assets/logo/resolve-wide.svg" alt="RFPerfusion" width="200">
  </picture>
</p>

<h1 align="center">RFPerfusion</h1>

<p align="center">
  <b>Turn a protein design question into cited evidence and scored candidates —<br>
  and get told, explicitly, what could not be checked.</b>
</p>

Ask it *"design a protein that changes conformation in response to
radiofrequency fields"* and it decomposes the question into buildable parts,
reads the literature for mechanisms and real sequences, verifies every sequence
against the paper it came from, and hands the survivors to computational
biology tools with numeric pass/fail gates already attached.

The distinctive part is what it refuses. Every extracted sequence is re-checked
against its source document, every rejection keeps the reason it failed, and
nothing is presented as verified evidence when it is only a discovery lead.

---

## Install

```bash
git clone <this repo> && cd RFPerfusion
claude plugin marketplace add .
claude plugin install rfperfusion@rfperfusion
```

Inside this repo the nine agent skills load automatically and need no install.

### Dependencies

Three pieces of software and two accounts.

| | What it is | Setup |
|---|---|---|
| [**uv**](https://docs.astral.sh/uv/) | Runs every project here | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [**Paperclip**](https://paperclip.gxl.ai) | Literature CLI (`gxl-paperclip`) | Install from paperclip.gxl.ai, then `paperclip login` |
| [**proto-tools**](https://github.com/evo-design/proto-tools) | Computational biology tool catalogue | `uv sync --project proto` |
| [**Paperclip account**](https://paperclip.gxl.ai) | Search and full-text reading | Free · 100 LLM reads/day |
| [**Modal account**](https://modal.com) | GPU compute for prediction and scoring | Billable · per-tool approval |

```bash
uv sync --project proto                  # installs proto-tools
paperclip login                          # interactive browser sign-in
uv run --project proto modal setup       # interactive; writes ~/.modal.toml
```

Verify:

```bash
paperclip config                         # expect an authenticated account
uv run --project proto proto-tools list  # 140 tools in the catalogue
```

proto-tools is what reaches Modal — the catalogue and its schemas are readable
without a Modal account, and only execution needs one.

You can try a lot before signing up for either: the test suite, tool discovery,
and a few database tools that run locally — see [Without an
account](#without-an-account).

## Use it

Each stage is a skill you invoke in Claude Code, or a command you run. Output
from one stage is input to the next.

```
your question
   │
   ├─ formulate-grounded-directions ─→ ranked directions, claim-verified
   │
   └─ design-brief-007 ─→ shards · mining plan · assembly recipe · fitness gates
          │
          ├─ mining plan ──→ litkb  or  mine-literature-from-concept
          │                     └─→ evidence + verified sequences
          │
          └─ fitness gates ─→ write-program / proto-tools ─→ scores
```

### 1. Turn a question into a brief

```bash
FA7_LLM_BACKEND=claude uv run --project formulation_agent007 formulate007-run \
  --question "Design a protein that changes conformation in response to radiofrequency fields" \
  --output-dir formulation_agent007/briefs/rf-switch
```

Produces a mining plan, a per-shard extraction contract, and a screening
cascade whose every gate names a real tool, a real metric, and a number —
`esmfold` mean pLDDT ≥ 75, `boltz2` ipTM ≥ 0.72, and a negative gate the
inactive state must fail.

### 2. Mine the literature

`litkb` takes the brief's plan directly and returns typed records:

```bash
cd litterature_search_from_concept
uv run --project . python -m litkb plan-adopt <brief>/plan_<slug>.json \
    --objective "<question>" --slug rf --output-dir outputs/rf
uv run --project . python -m litkb search outputs/rf/plan_rf.json -n 4 --output-dir outputs/rf
uv run --project . python -m litkb screen outputs/rf/search_rf.json -n 1 --output-dir outputs/rf
```

Then `dig` → `bind` → `evidence` → `report` → `manifest`. `-n` caps papers per
query and is your cost dial — start small.

You get `evidence_<slug>.json` (mechanisms with citations),
`artifacts_<slug>.json` (sequences that passed verification, each bound to the
tools that accept it), a human-readable knowledge base, and a manifest
recording exactly what was searched.

`mine-literature-from-concept` is the lighter alternative: keyword grep over the
same corpus, no LLM reading, no per-day limit.

### 3. Score the candidates

`proto-tools` runs one model on one input. `write-program` runs an iterative
search under weighted constraints. `implement-constraint` builds a scoring
function that does not exist yet.

## What you get back

Everything is typed JSON with provenance, so a downstream agent consumes it
without parsing prose.

**Evidence** carries a claim, a citation, and `testable_by.requires_new_evaluator` —
three-valued: `"unassessed"` until you assign vocabulary terms via `litkb label`,
then `false` once a catalogue tool measures the assigned property, or `true` if
none does.

**Sequences** carry the document they came from, whether they were confirmed
present in it, and the tools whose input constraints they satisfy.

**Rejections ship too.** A sequence no tool accepts, a query that returned
nothing, a mechanism with no evaluator — each is kept with its reason. A run
that finds little says so rather than padding.

Every run declares `evidence_status: discovery_only_unverified`. A sequence
accepted by a tool passed an input check — molecule, alphabet, length — not an
experiment, and not a run.

## Without an account

```bash
cd litterature_search_from_concept && uv run --project . pytest
```

119 tests, fully offline. Tool discovery (`search_tools`, `get_tool_schema`) is
free, and several database tools run locally with no GPU and no billing —
`uniprot-fetch` and `alphafold-db-fetch` will resolve a protein and return a
real structure with per-residue confidence before you authenticate anything.

## Skills

| Skill | Role |
|---|---|
| `formulate-grounded-directions` | Ranked research directions, claim-level verification |
| `design-brief-007` | Question → shards, mining plan, assembly recipe, fitness gates |
| `litkb` | Concept → typed evidence + verified, tool-bound sequences |
| `mine-literature-from-concept` | Concept → keyword-grep knowledge base |
| `paperclip` | Full-text search over papers, trials, regulatory documents |
| `write-program` | Design program — iterative search under weighted constraints |
| `implement-constraint` | Build and calibrate a missing scoring function |
| `proto-tools` | Single tool invocations against the catalogue |
| `visualize-sequence-design` | Compare an input and a designed sequence |

`.agents` symlinks to `.claude`, so both conventions work, and each skill ships
an `agents/openai.yaml` for Codex.

**Scope.** `proto-tools` is one model, one input, one result. Iterative design
belongs in `write-program`. A missing scoring function goes to
`implement-constraint` first.

## Layout

```
.claude/skills/                   nine agent skills
docs/                             PRD-framework (the loop) · PRD-instance-tlpa (worked example)
formulation_agent/                open question → ranked, claim-verified directions
formulation_agent007/             question → brief; briefs/ holds runs
litterature_search_from_concept/  litkb/ (typed) + paperclip_kb.py (grep); outputs/ holds runs
proto/                            proto-tools runtime for Modal-backed compute
registry/proto_catalog.json       generated tool-constraint table
```

Design rationale lives in [`docs/PRD-framework.md`](docs/PRD-framework.md); the
worked TlpA example and the data contracts are in
[`docs/PRD-instance-tlpa.md`](docs/PRD-instance-tlpa.md).

## Where it stands

Working end to end: question → brief → literature → verified evidence and
sequences, artifact to artifact. Committed example runs live under
`litterature_search_from_concept/outputs/`.

Known limits, honestly:

- **The tool-binding surface is narrow.** Sequence constraints are parsed from
  the proto-tools catalogue, and most entries do not publish parseable limits,
  so many sequences come back `unverified` rather than bound. Unknown never
  counts as pass.
- **Deep reading is capped.** Paperclip's specialised readers require elevated
  access; the default reader handles body text well but rarely reaches
  supplementary tables, where many sequences live.
- **Nothing has been generated yet.** The scoring cascade is defined and its
  gates are real, but variant generation needs Modal credentials and has not
  been run.

Next: Modal-backed generation and the GPU gates, a held-out melting-temperature
benchmark for calibration, and an orchestrator over the stage functions.

## License

MIT — see [LICENSE](LICENSE).
