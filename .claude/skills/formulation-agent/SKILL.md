---
name: formulation-agent
description: Turn an open scientific design question into ranked research directions, each decomposed into checkable claims and verified against full-text literature with line-pinned citations. Use when running, extending, debugging, or integrating the agent in formulation_agent/, and when a request needs literature-grounded directions with citations and calibrated confidence rather than plausible-sounding suggestions.
---

# Formulation Agent

Lives in `formulation_agent/`. Takes an underspecified design question and returns
ranked directions. Each direction is decomposed into checkable factual claims,
and **no claim raises a score until it survives two independent checks**.

Read [references/internals.md](references/internals.md) before changing anything
under `src/formulation_agent/`.

## Run

From the repository root, matching the `--project` convention used by `proto/`:

```bash
export ANTHROPIC_API_KEY=sk-ant-...                      # or paste into the browser UI
uv run --project formulation_agent formulate-web         # browser UI (recommended)
uv run --project formulation_agent formulate             # terminal REPL, same engine
uv run --project formulation_agent pytest formulation_agent/tests -q
```

Paperclip must be authenticated (`paperclip search -s pmc test -n 1`). It runs on
its own account, so retrieval and per-paper reading are not billed to the API key.

## Module map

| file | role |
|---|---|
| `models.py` | typed contracts — the only structures crossing component boundaries |
| `paperclip.py` | async CLI wrapper; all text parsing, and the deterministic quote check |
| `grounding.py` | search → extract → verify pipeline |
| `scoring.py` | confidence composition and the grounding cap |
| `agent.py` | two-stage proposal, chat, scoring orchestration |
| `followup.py` | background subagents for follow-up questions |
| `web.py` + `static/index.html` | local browser UI over SSE |
| `cli.py` | terminal REPL |
| `report.py` | session JSON + markdown with a REFERENCES block |

## Invariants — do not break these

Each of these is load-bearing. Breaking one does not fail loudly; it quietly
turns the tool back into something that emits confident, unfounded answers.

1. **The quote check is not a model call.** `Paperclip.locate_quote` searches the
   paper for the quoted text. If the text is not there, the evidence is discarded
   however plausible it reads. Do not replace this with a model asking "is this
   quote real?"
2. **The entailment judge sees only the claim and the passage** — never the idea,
   its rationale, or why we went looking. That blindness is the whole point; it
   cannot be argued into agreement by a framing it never sees.
3. **Line numbers are derived, never accepted.** They come from where the text was
   located. Physical file offsets do **not** correspond to `L<n>` labels (physical
   line 18 of one paper is labelled L133), so never slice `content.lines` by index.
4. **The grounding cap lives in code** (`scoring.py`), not in a prompt. Unverified
   load-bearing claims cap an idea at 0.45; a verified refutation at 0.35. This is
   what stops a fluent ungrounded direction outranking a modest verified one.
5. **Never add `max_length` / `max_items` to a response model.** Anthropic
   structured outputs do not support them: the SDK strips them from the schema and
   validates client-side afterwards, so the model never learns the limit and a
   completed, paid-for generation is thrown away. Put length guidance in prompts.
   `tests/test_verification.py::TestNoUnsupportedConstraints` enforces this.
6. **Refuting evidence is kept and surfaced.** A verified quote that cuts against a
   claim is a finding, not noise. Do not filter it out.
7. **"Not retrieved" is not "refuted."** The corpus index has coverage gaps, so
   absence of evidence is weak. Never render it, or reason about it, as evidence
   against a direction.

## Extending it

- **New evidence source** — add a retrieval method to `paperclip.py` and call it
  from `Grounder._collect`. Everything downstream is source-agnostic.
- **New scoring axis** — add to `JudgedAxes` and `WEIGHTS` in `scoring.py`. Keep
  computed axes (grounding, evidence strength) separate from model-judged ones;
  a model must not be able to argue its way to better grounding.
- **New front end** — drive `FormulationAgent` directly. `cli.py` and `web.py` are
  two thin drivers over one engine and contain no agent logic; copy that split.
- **Changing retrieval breadth** — count paper-reads first. Reading is the only
  expensive Paperclip operation (~2–4s *per paper*); searches are under a second.

## Traps that already cost a run

- `-s pmc,biorxiv` does **not** union sources — it silently returns PMC-only
  results. Query each source separately and merge in Python.
- `paperclip merge` is broken: it reports `not found` for result-set IDs that
  `results` and `map --from` both resolve, with raw IDs and `--save-as` aliases
  alike. The documented "merge then map once" pattern is unavailable.
- Paperclip's launcher is `#!/usr/bin/env python3`. With `VIRTUAL_ENV` set it
  resolves to the project venv, dies on a missing import, and returns **empty
  stdout** — indistinguishable from "no results". `paperclip.py` sanitises the
  child environment; keep it that way.
- Semantic search misses exact entity names. A protein name queried topically
  returns papers about the area while skipping the ones that say the name. Hence
  `exact_terms` and the BM25 full-text path alongside semantic search.
- An unbounded `asyncio.gather` over all claims makes them advance in lockstep and
  finish together, so progress reads 0/N until the very end. Keep the pool bounded.

## Reporting results

- Lead with the ranked directions and their grounding, not the prose rationale.
- Quote verified evidence with its line-pinned URL; never paraphrase a citation.
- State plainly which claims failed verification and how — a fabricated quote and
  a real quote that does not support the claim are different failures.
- Never present a score without its grounding fraction beside it.
