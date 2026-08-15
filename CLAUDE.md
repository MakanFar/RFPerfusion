# RFPerfusion

Read `docs/PRD.md` first (the 48h hackathon deliverable) and `docs/PRD-framework.md`
(the general architecture it's an instance of). `docs/Team Discussion Summary & Proposed
Project Direction.md` is background only — superseded where it conflicts with the PRDs.

## Tamarind Bio API

Sponsor tool for Layer 4 (Evaluation) and, via pipelines, Layer 3 (Generation). It runs
computational-biology tools (folding, docking, developability, binder design) on managed
GPUs behind one REST job API. No local GPU, no SDK — plain HTTP.

**Setup:** copy `.env.example` to `.env`, set `TAMARIND_API_KEY` (get one at
app.tamarind.bio). `.env` is gitignored — never commit a real key, never paste one into
a chat message or a committed file.

**Non-negotiable rule when calling this API: discover live, never guess.** There are
hundreds of tools and the catalog changes constantly. Always call `GET /tools` (or read
`registry/tamarind_catalog.json` as a cached starting point) before naming a tool or a
settings field — a tool name, port name, or setting key not read from the live schema is
a guess and will fail validation. Always `POST /validate-job` before `POST /submit-job`.

## How Tamarind plugs into the framework

Per `docs/PRD-framework.md`, the Evaluator Registry is an *input* to ideation — routes
without a bound evaluator can't become specs. Two files implement that here:

- **`registry/tamarind_catalog.json`** — raw sync of everything Tamarind exposes to this
  account (name, description, required settings). Refresh with
  `python scripts/sync_tamarind_catalog.py`. This is discovery only, not curation.
- **`registry/evaluators.json`** — the actual Evaluator Registry the framework consults.
  Each entry names a Tamarind tool, what it measures, and its `status`
  (`needs_calibration` until someone benchmarks it against a held-out set per PRD.md
  §7.2 — an uncalibrated evaluator may run but its scores cannot rank candidates).

**Adding a new evaluator:** confirm the tool exists via `GET /tools`, add an entry to
`registry/evaluators.json` with `status: "needs_calibration"`, then run the calibration
benchmark before flipping it to `"validated"`. Don't hand-roll evaluator JSON that
duplicates what a schema call would give you for free.

## Don't

- Don't hardcode a Tamarind `type`, port name, or settings key from memory — read it
  from `/tools` or `/tools/{name}/schema` first.
- Don't submit a job with a known-missing required field to "see what happens" —
  `/validate-job` catches this for free.
- Don't treat an uncalibrated evaluator's score as rankable — see `registry/evaluators.json`.
- Don't commit `.env` or any file containing an actual API key.
