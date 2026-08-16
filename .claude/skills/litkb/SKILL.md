---
name: litkb
description: Use when turning a protein-design concept into cited, typed literature evidence — mining PubMed Central and bioRxiv full text into EvidenceItem records for the ideation layer of docs/PRD-framework.md. Triggers on "find evidence for", "literature search from concept", "build a knowledge base", "what does the literature say about <mechanism>", or any request to ground design routes in citations.
---

# litkb — concept to typed evidence

Nine deterministic tool calls over the `paperclip` corpus. You supply every
judgement; the tool supplies plumbing and citations.

**The split that matters:** `litkb` never invents a claim, a support level, or
a mechanism class. It searches, greps, parses, and fetches citation metadata.
You write the plan and you write the labels. Judgement fields on every
EvidenceItem start `null` by construction, and `litkb validate` refuses to
pass items that still are.

## Setup

Requires Python >= 3.10 and an authenticated `paperclip` (both `paperclip` and
this package use `str | None`, so a 3.9 interpreter fails at import). Check
with `paperclip config` — if it shows an auth error, tell the user to run
`paperclip login` themselves; it is an interactive browser flow you cannot
complete.

Run from `litterature_search_from_concept/` as `python -m litkb <cmd>`.

## The pipeline

```
plan-template ─▶ (you write the plan) ─▶ plan-validate --probe
                                              │
                                              ▼
                    search ─▶ extract ─▶ evidence ─▶ label ─▶ validate ─▶ report
                                                       ▲
                                              (you write the labels)
```

| Command | In | Out |
|---|---|---|
| `plan-template` | — | empty plan skeleton |
| `plan-validate PLAN [--probe]` | plan | schema errors + per-phrase yield |
| `search PLAN` | plan | set IDs + per-class coverage |
| `extract PLAN SEARCH` | plan, search | raw categorized hits |
| `evidence HITS` | hits | draft `EvidenceItem[]` |
| `label EVIDENCE LABELS` | evidence, your labels | labelled evidence |
| `validate EVIDENCE` | evidence | pass/fail for L1 entry |
| `registry-check PLAN` | plan | evaluator coverage per class |
| `report EVIDENCE --search S` | evidence | human-readable knowledge base |

Every command writes JSON to stdout, or to `-o FILE`.

## Writing the plan

The unit is the **mechanism class**, not the phrase. The framework measures
coverage over classes and wants at least six, so one class per distinct
physical route — not six rewordings of one route.

Per class: an `id`, the `question` it answers, `search_phrases`, and
`mechanism_patterns`.

**`search_phrases` are matched as strict literals.** Write phrases authors
actually put in a title or abstract. Compound phrases you assemble yourself
return nothing — "engineered magnetoreceptor" and "magnetic field effect on
enzyme" both returned 0 papers in testing, while "radical pair mechanism" and
"magnetic torque" work. Always run `plan-validate --probe` before `search`; it
flags zero-yield phrases and any single class about to swamp the corpus.

**`mechanism_patterns`** are case-insensitive fragments that mark mechanistic
content — the physical basis, rate-limiting steps, failure modes.
"excited-state proton transfer" is useful; "protein" is not.

Structural patterns (sequences, accessions, PDB IDs, mutations) are hardcoded
in `litkb/patterns.py` and are not yours to plan — they do not vary by concept.

## Writing labels

`evidence` gives you drafts with a verbatim `provenance.span` and a citation.
Read the span, then write a labels file:

```json
[{"id": "ev_001", "claim": "Water absorption is the primary energy-absorption mechanism for infrared neural stimulation",
  "claim_type": "mechanism", "support": "established",
  "evidence_kind": "experimental", "confidence": 0.9}]
```

`support` is `established | contested | speculative` and is load-bearing:
**nothing marked speculative may become a hard constraint downstream.** Label
from the span in front of you, not from memory. `provenance` is tool-owned and
`label` rejects any attempt to rewrite it.

## Reading the output

`search` reports `coverage.meets_framework_minimum`. If false, add mechanism
classes rather than more phrases to existing ones.

`registry-check` returns `requires_new_evaluator` for classes nothing can
evaluate. Per framework §77 that is a legitimate output to report to the
scientist, not a discard — the evaluator registry constrains what is worth
ideating. There is currently **no registry on disk**; `registry/evaluators.json`
was removed in commit `945164f` with the Tamarind integration, so the command
returns `status: missing` and coverage `unknown` until something replaces it.

Zero-yield phrases and empty classes are recorded as `rejections` and carried
into the report — rejection is a first-class output.

## Known limits

- `extract` truncates long per-document hit lists; `provenance.truncated_after`
  records how many were dropped.
- Hits are paragraph-level, so citation URLs have no `#L` line anchor.
- `PDB[ :]?[0-9][A-Za-z0-9]{3}` still matches the software name "PDB2PQR".
- `paperclip merge` is broken upstream (resolves only its first argument), which
  is why every set ID is carried separately rather than unioned.
