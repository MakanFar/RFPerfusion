# Formulation agent — internals

Read this before changing anything under `formulation_agent/src/formulation_agent/`.
It covers the data flow, where each guarantee is enforced, and the cost model that
decides runtime.

## Data flow

```
question
   │
   ├─ agent.propose_outline()      1 model call, effort=high
   │     → Idea{title, one_liner, mechanism_chain}      ← rendered immediately
   │
   ├─ agent.expand_all()           N model calls in parallel, effort=medium
   │     → Claim{text, load_bearing, search_queries, exact_terms}
   │
   ├─ grounding.ground_claims()    bounded pool of claims
   │     ├─ pc.search() × sources          cheap  (<1s)
   │     ├─ pc.search_exact()               cheap
   │     ├─ pc.map_schema()                 EXPENSIVE (~2-4s per paper)
   │     ├─ pc.locate_quote()      layer 1 — deterministic, no model
   │     └─ llm.structured()       layer 2 — entailment, isolated context
   │
   └─ agent.score()                → IdeaScore, capped by grounding
```

Proposal is split in two so directions appear in seconds. A single call producing
six fully-decomposed directions took 6+ minutes with nothing to display.

## Where each guarantee lives

| guarantee | enforced in | how it fails if moved |
|---|---|---|
| Quote really exists in the paper | `paperclip.verify_against_line` | becomes a model opinion; fabrications pass |
| Quantities are not altered | same, checked *separately* from fuzzy match | a changed number slips through string similarity |
| Passage actually supports the claim | `grounding.Grounder._verify` layer 2 | judge sees the argument and agrees with it |
| Ungrounded ideas can't win | `scoring.grounding_cap` | a prompt "please be strict" is not a guarantee |
| Response schemas stay API-compatible | `tests/…::TestNoUnsupportedConstraints` | completed generations get discarded on validation |

### Why the quote check is two-stage

Locating a *fragment* is not enough. An extractor can copy the opening of a real
sentence and alter the number at the end; a fragment match sails straight through.
So `locate_quote` uses a fragment only to **find the candidate line**, then
`verify_against_line` compares the **full quote** against that line:

1. every number in the quote must appear in the source line — checked first and
   independently, because an altered quantity is the most damaging failure and the
   easiest for a fuzzy comparison to wave through;
2. whitespace-insensitive containment (publishers render `42 °C` and `42°C`;
   extracted text carries doubled spaces around italics);
3. a ≥90% longest-common-run fallback for minor drift.

Verified against fabricated quotes, altered quantities, altered meaning, quotes
lifted from another paper, and cosmetic typography — see `tests/test_verification.py`.

## Cost model

Reading is the only expensive operation.

| operation | cost |
|---|---|
| `search` / `search_exact` | 0.4–1.1s including process start |
| `cat meta.json` | ~0.4s (memoised per doc) |
| `grep` within one document | 1–3s |
| **`map` (per-paper LLM reader)** | **~2–4s per paper** |

Runtime is therefore *total paper-reads*. The original design issued one `map` per
search per claim — 24 claims × 8 searches × 6 papers ≈ **1,150 reads ≈ 24 minutes**.

Current controls, all in `config.py`:

| setting | default | effect |
|---|---|---|
| `papers_per_map` | 4 | papers actually read per result set (`-n`) |
| `evidence_target` | 2 | stop a claim once this many verified supports exist |
| `claim_concurrency` | 4 | claims in flight; keeps completion incremental |
| `paperclip_concurrency` | 16 | subprocesses; these wait on network, not CPU |

Measured after tuning: 4 real claims in 17.2s, resolving at 7.6 / 13.3 / 13.7 /
17.2s — staggered, so progress is visible.

**Before adding retrieval breadth, compute the new paper-read count.**

Early stopping is safe because each result set is read *in full* before the check
fires, so a refutation in the current set is never skipped, and a claim that finds
nothing still exhausts every set — `no_evidence` remains as well-supported as before.

## Claim status semantics

`Claim.status` (derived, in `models.py`) — do not collapse these:

| status | meaning |
|---|---|
| `verified` | quote located **and** judged to support the claim |
| `partial` | real quote, supports only part of the claim |
| `unsupported` | real quote, does **not** support the claim |
| `quote_mismatch` | quoted text is not in the paper — fabricated or altered |
| `no_evidence` | searched, nothing relevant retrieved |
| `error` | never searched — a bug, not a finding |

`no_evidence` and `error` must stay distinct: "we looked and found nothing" is a
result; "we never looked" is a defect.

## UI constraints (`static/index.html`)

- **Nothing animated may change layout width.** An animated `content` ellipsis
  cycling `""`/`"."`/`".."`/`"..."` propagated through `.chip-pending` → `.metrics`
  → `.card-title` (`flex:1`) and re-wrapped every card title several times a
  second. Dots animate on **opacity** only.
- **Unscored ideas show no score, no rank, no verdict pill** — only a
  `claims pending` chip, grouped under "Still verifying". A number that later moves
  reads as a finding.
- `Session.ranked()` sorts unscored ideas to 0.0, so they must be **grouped
  separately**, never interleaved.
- The activity log has a fixed height; letting it grow pushes the panels below it
  down on every append.

## Paperclip output parsing

There is no machine-readable mode, so `paperclip.py` owns all text parsing.

- Search hits: `^\s{2,}(id)\s+·\s+(source)\s+·\s+(YYYY)-MM-DD$`
- Map results: `^\s{2,}(id)\s+·\s+\d+ms$`, JSON on following lines
- **Map output abbreviates long document ids** (`bio_6af5af36` for
  `bio_6af5af366c48`). An abbreviated id silently breaks the quote check and the
  citation fetch, so `map_schema` takes `known_ids` from the originating search and
  restores the full form. Ambiguous prefixes are left alone rather than guessed —
  attributing a quote to the wrong paper is worse than failing to resolve it.
