# RFPerfusion — Formulation Agent

A scientist poses an open design question. The agent proposes concrete research
directions, decomposes each into checkable factual claims, verifies every claim
against full-text literature, and ranks the directions by how well they are
actually grounded — not by how good they sound.

```
question ──▶ propose directions ──▶ decompose into claims ──▶ verify ──▶ rank
                                                               │
                          ┌────────────────────────────────────┘
                          │  1. quote check   (deterministic, no model)
                          │  2. entailment    (independent model call)
                          └──▶ only claims passing BOTH raise a score
```

## Quick start

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # Console credits work here
uv run formulate
```

```
› How can we design a protein that responds to wavelengths greater than 1500 nm?

  6 directions, 19 claims — verifying against literature…
    (1/19) verified   Water's absorption coefficient at 1550 nm is ~10 cm^-1
    (2/19) unsupported  Retinal analogues can be red-shifted past 1200 nm
    ...

  #  id  direction                              score          grounded  verdict
  1  I3  Photothermal actuation via water        ███████··· 0.71   3/3   pursue
  2  I1  Direct SWIR chromophore engineering     ███······· 0.32 ▲ 0/2   park
```

## Why verification is the point

An LLM asked for research directions will produce fluent, plausible, correctly
formatted citations that do not say what it claims they say. This agent assumes
that and checks:

**Layer 1 — the quote is real.** Not a model call. The quoted text is searched
for in the cited paper. If it isn't there, the evidence is discarded no matter
how plausible it reads. Numbers are checked separately and strictly, because an
altered quantity is the most damaging failure and the easiest for fuzzy string
matching to wave through. The line number is taken from where the text was
*found*, so a correct quote with a wrong line number is repaired rather than
rejected.

**Layer 2 — the passage supports the claim.** A separate model call sees only
the claim and the retrieved passage — never the idea, its rationale, or why we
went looking. It cannot be talked into agreeing by a framing it never sees.

**The score is capped by grounding.** An idea whose load-bearing claims are
unverified cannot score above `0.45`; one with a verified refutation caps at
`0.35`. A fluent ungrounded idea therefore *cannot* outrank a modest verified
one. This is enforced in code (`scoring.py`), not by prompting.

Verified by `tests/test_verification.py`, which includes the adversarial cases:
fabricated quotes, altered quantities, altered meaning, and quotes lifted from
the wrong paper.

## Commands

| | |
|---|---|
| `<free text>` | talk to the agent about the ideas |
| `/ideas` | ranked list |
| `/show <n>` | claims, verified quotes, citations |
| `/evidence <n>` | everything including what *failed* verification |
| `/followup <n> <question>` | investigate in the background; chat continues |
| `/drop <n> [reason]` | remove from the ranking |
| `/more [n]` | propose further directions |
| `/jobs` | background investigation status |
| `/save` | session JSON + citable markdown report |

Follow-ups run as detached tasks. Ask about I3, keep discussing I1, and the
report arrives at a later prompt. Follow-up findings go through the same
verification, so a follow-up cannot smuggle an unverified assertion into the
session.

## Layout

| file | role |
|---|---|
| `models.py` | typed contracts — the only things crossing component boundaries |
| `paperclip.py` | async CLI wrapper; all text parsing and the quote check |
| `grounding.py` | search → extract → verify pipeline |
| `scoring.py` | confidence composition and the grounding cap |
| `agent.py` | proposal, chat, scoring orchestration |
| `followup.py` | background subagents |
| `report.py` | session JSON + markdown with a REFERENCES block |
| `cli.py` | interactive REPL |

## Gotchas that already cost us a run

Recorded because each one failed silently and looked like something else.

- **Never put `max_length` on a response model.** Anthropic structured outputs
  don't support string `maxLength` / array `maxItems`. The SDK strips them from
  the schema sent to the model and validates client-side *afterwards* — so the
  model never learns the limit, writes past it, and a completed, paid-for
  generation is thrown away. Put length guidance in the prompt instead.
  `tests/test_verification.py::TestNoUnsupportedConstraints` enforces this.
- **Proposal runs in two stages** (`propose_outline` → `expand_all`). One call
  producing six fully-decomposed directions took 6+ minutes, during which the
  UI had nothing to show. The outline call is deliberately the highest-effort
  call in the system; expansion is `medium`.
- **`-s pmc,biorxiv` does not union sources** — it returns PMC-only results and
  silently drops the rest. Sources are queried separately and merged.
- **`paperclip` must not inherit an active virtualenv.** Its launcher is
  `#!/usr/bin/env python3`; with `VIRTUAL_ENV` set it resolves to the project
  venv, dies on a missing import, and returns empty stdout — indistinguishable
  from "no results". `paperclip.py` sanitises the child environment.
- **Reading is the only expensive Paperclip operation.** Searches cost <1s; a
  `map` costs ~2-4s *per paper*. Total paper-reads is the number that decides
  runtime. Issuing one map per search per claim came to ~1,150 reads a run
  (~24 min); the fix was fewer searches, capped papers per map, and stopping a
  claim once it has enough verified support.
- **`paperclip merge` is broken** — it reports `not found` for result-set IDs
  that `results` and `map --from` both resolve, with raw IDs and `--save-as`
  aliases alike. So the documented "merge then map once" pattern is unavailable.
- **Bound the claim pool.** An unbounded `gather` over every claim makes them all
  advance in lockstep and finish together, so progress reads 0/N until the very
  end. A small semaphore makes them complete steadily.
- **Physical file lines are not `L<n>` labels.** Line 18 of one paper is
  labelled L133. Never slice `content.lines` by offset; locate text and read the
  label back.

## Known limitations

These are properties of the corpus and tooling, found while building. They
affect how much weight an unverified verdict deserves.

- **The full-text search index has coverage gaps.** Papers reachable by
  metadata lookup are not always reachable by search. Piraner et al.,
  *Modular Thermal Control of Protein Dimerization* (doi:10.1101/694448) is in
  the corpus — `lookup doi` finds it — but neither semantic nor boolean
  full-text search surfaces it, even querying a term unique to its own abstract.
  So **"not retrieved" is much weaker evidence than "refuted"**, and the UI
  words it that way.
- **`-s pmc,biorxiv` does not union sources.** The comma form returns PMC-only
  results and silently drops the rest. Sources are queried separately and
  merged. Do not "simplify" this back.
- **Semantic search misses exact entity names.** Querying a protein name
  topically returns papers about the general area while skipping the ones that
  say the name. Hence `exact_terms` and the BM25 full-text path alongside
  semantic search.
- **Piraner et al. 2017 (*Nat Chem Biol*)** — the source of the engineered TlpA
  variant→Tm table — is not in the corpus at all.
- Verification confirms a paper *says* something. It does not confirm the paper
  is *right*. `support_level` (established / contested / speculative) carries
  that distinction as far as the source itself states it.

## Development

```bash
uv run pytest tests/ -q          # 15 tests, incl. live corpus checks
uv run pytest tests/ -m "not live"
```

Tunable via env: `FA_MODEL`, `FA_JUDGE_MODEL`, `FA_EFFORT`, `FA_N_IDEAS`,
`FA_PAPERS_PER_CLAIM`, `FA_SOURCES`, `FA_PC_CONCURRENCY`.
