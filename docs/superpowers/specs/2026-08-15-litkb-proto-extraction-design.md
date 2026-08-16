# litkb — LLM extraction bounded by proto-tools

**Replaces grep-based extraction with full-text LLM reading, and keeps only structural artifacts that a proto-tools tool can actually accept.**

| | |
|---|---|
| Date | 2026-08-15 |
| Status | Approved design, not yet implemented |
| Supersedes | the `extract` and `evidence` stages of litkb 0.1.0 |
| Related | `docs/PRD-framework.md` §4 §77, `docs/PRD-instance-tlpa.md` §6.2 |

---

## 1. Problem

litkb 0.1.0 finds papers well and reads them badly.

Extraction is `paperclip grep` over hardcoded regexes. That was always a proxy
for reading, and it fails in both directions. It missed nearly every real
sequence in the first RF run — one 29-mer targeting peptide out of 483 items,
with the rest DNA primers and prose mentions of the words "amino acid
sequence". It also produced false positives that no amount of regex tuning
fixes cleanly: three of five "accessions" were fragments of DOIs.

The deeper problem is that nothing downstream could use the output even when it
was correct. An extracted sequence had no relationship to any tool that could
act on it, so "we found a sequence" and "we found something we can compute
with" were indistinguishable.

## 2. Decisions

Four decisions were taken during design. They are recorded here because each
closed off a materially different system.

**Structural artifacts are hard-filtered; mechanisms are not.** A mechanism
sentence is not an input to any proto tool, so filtering everything by tool
binding would delete the literature grounding the framework's Route layer
depends on. Mechanisms are kept and annotated with `testable_by`; sequences and
subsequences must bind to a tool or they are rejected.

**Verification is schema-level, not execution-level.** Artifacts are checked
against tool constraints — molecule type, alphabet, length cap — parsed from
the proto-tools registry. Constructing the real Pydantic input models would be
more authoritative and is still free, but was judged more machinery than the
gain warrants. Running the tool on Modal to prove runnability is billable and
was never a candidate as an extraction-time filter. The cost of this choice is
drift: the constraint table restates rules that live in the Pydantic models.
`constraint_source` on every entry makes that drift visible, and `proto-sync`
makes it cheap to correct.

**Expert keywords are first-class input, searched semantically.**
`rf_protein_literature_keywords.csv` is a curated query set. Its rows are
keyword bags — `CraCRY ODMR`, `AsLOV2 C450A radical pair` — not phrases any
author writes verbatim, so exact matching would return roughly nothing. They
run through paperclip's hybrid ranking instead. The agent groups rows into
mechanism classes and invents new queries only for a class that comes back
empty.

**Reading is two-tier.** `structured-extraction` sweeps every paper cheaply for
mechanisms and flags which papers claim sequences; `exhaustive-extraction`
re-reads only the flagged ones, inspecting methods, tables and supplements
where sequences actually live. Running the expensive worker over every paper
would spend most of its budget on papers that were never going to carry a
usable sequence.

## 3. Architecture

```
keywords.csv ─▶ plan-import ─▶ plan-validate ─▶ search  (semantic)
                                                   │
                                                   ▼
                    screen   map --worker structured-extraction, ALL papers
                             → mechanisms + has_sequence + sequence_location
                                                   │
                                                   ▼
                    dig      map --worker exhaustive-extraction, FLAGGED only
                             → sequences, subsequences, mutations, accessions
                                                   │
                                                   ▼
                    bind     verify against registry/proto_catalog.json
                             ├─ passes → ProtoArtifact
                             └─ fails  → rejection carrying the failed check
                                                   │
                                                   ▼
                    evidence ─▶ label ─▶ validate ─▶ report
```

`plan`, `search`, `label`, `validate` and `report` carry over unchanged.
`extract` and `evidence`'s grep path are deleted.

**What this deletes.** The entire `STRUCTURAL` pattern table goes: the
amino-acid run regex, the UniProt and RefSeq patterns with their DOI
lookarounds, the mutation and accession patterns. The LLM reader does this job
properly, and deleting the regexes removes both the false negatives and the
lookaround machinery built to suppress the false positives.

**The division of labour is unchanged from litkb 0.1.0.** The agent supplies
judgement — mechanism classes, claims, support levels, measurable properties.
The tool supplies deterministic work — searching, constraint checking, citation
resolution. `bind` never decides what a sequence means; the reader never
decides whether a tool accepts it.

## 4. Contracts

### 4.1 proto_catalog.json

Generated by `proto-sync` from `proto-tools list --json` plus per-tool `input`
docs. One entry per tool:

```json
{
  "key": "esm2-score",
  "category": "sequence_scoring",
  "input_kind": "sequence",
  "molecules": ["protein"],
  "alphabet": "ACDEFGHIKLMNPQRSTVWYXBZUO",
  "max_length": 1022,
  "uses_gpu": true,
  "constraint_source": "docstring",
  "measures": [],
  "status": "needs_calibration"
}
```

`input_kind` ∈ `sequence | structure | structure_with_selection`. Tools taking
a structure file — `proteinmpnn-sample` and the inverse-folding family — cannot
consume a bare literature sequence.

`measures` and `status` are agent-curated, not derivable from proto-tools. They
exist so this file can serve as the Evaluator Registry (§6).

### 4.2 Constraint checks are three-valued

Every check returns `pass`, `fail`, or `unknown`. **`unknown` never counts as
`pass`.** A tool whose length cap could not be parsed yields an artifact status
of `unverified`, not `runnable`. Failing open here would silently reintroduce
the problem this redesign exists to fix.

Artifact status is `runnable` only when at least one tool returns `pass` on
every check.

### 4.3 ProtoArtifact

```json
{
  "id": "art_007",
  "kind": "sequence",
  "molecule": "protein",
  "value": "MKVAA…",
  "length": 247,
  "parent": {"name": "AsLOV2", "accession": "Q9C9W9", "region": [404, 546]},
  "evidence_refs": ["ev_012"],
  "provenance": {
    "doc_id": "PMC…",
    "where": "supplementary_table_S1",
    "verbatim": true,
    "confirmed_in_source": true,
    "extractor": "exhaustive-extraction"
  },
  "proto_binding": {
    "status": "runnable",
    "tools": [{"key": "esm2-score",
               "checks": {"molecule": "pass", "alphabet": "pass", "max_length": "pass 247<=1022"}}],
    "rejected_by": [{"key": "esmfold-prediction", "failed": "molecule", "detail": "artifact is dna"}]
  }
}
```

`kind` ∈ `sequence | subsequence | mutation | accession | structure_id`. A
`subsequence` is a region of a named parent — the LOV2 Jα helix, a heptad
core — and sets `parent.region`; a `sequence` stands alone and does not.

Only `status: runnable` artifacts enter `artifacts[]`. Everything else enters
`rejections[]` with its failed check, so "found a sequence, nothing can run it"
stays visible rather than vanishing.

### 4.4 Mechanism evidence gains testable_by

```json
"testable_by": {
  "properties": ["fold_confidence"],
  "tools": ["esmfold-prediction"],
  "requires_new_evaluator": false
}
```

`properties` come from `screen`, which is itself an LLM call and therefore the
right place for that judgement — they cannot come from `label`, which runs
after `bind`. `bind` resolves them against the catalogue. An empty resolution
sets `requires_new_evaluator: true`.

### 4.5 Reader schemas

`screen`, per paper:

```json
{"mechanisms": [{"chain": "…", "claim": "…",
                 "measurable_properties": ["fold_confidence"]}],
 "has_sequence": true,
 "sequence_location": "supplementary | methods | figure | none",
 "named_proteins": [{"name": "AsLOV2", "accession": "Q9C9W9"}]}
```

`measurable_properties` is what §4.4 resolves into `testable_by.tools`.

`dig`, per paper:

```json
{"sequences": [{"value": "…", "molecule": "protein", "name": "AsLOV2",
                "region": null, "where": "Table S1", "verbatim": true}],
 "mutations": [{"parent": "AsLOV2", "mutation": "C450A", "effect": "…"}]}
```

Both are passed to `paperclip map --output-schema` with
`additionalProperties: false` and explicit `required`, so a paper that cannot
produce valid output fails loudly rather than degrading.

## 5. Hallucinated sequences

This is the primary risk of the redesign and the schema check cannot address
it. An LLM asked for a sequence will produce a plausible one, and a fabricated
247-mer passes every alphabet and length check perfectly. Constraint
verification confirms a sequence is *well-formed*, never that it is *real*.

Two defences, in order of strength:

1. **Verbatim discipline.** `dig` must copy sequences character-for-character
   and set `verbatim: false` for anything reconstructed, translated, or
   inferred. Non-verbatim artifacts are rejected at `bind` regardless of
   constraint status.
2. **Source confirmation.** Each extracted sequence is re-grepped against its
   source document with `paperclip grep --from`. Anything that does not
   literally appear is downgraded to `confirmed_in_source: false` and rejected.
   This is free, deterministic, and catches what the honour system misses.

Defence 2 is the load-bearing one. Defence 1 alone is a request the model can
fail silently.

## 6. Relationship to the framework

`proto_catalog.json` **is the Evaluator Registry the framework lost.**
`registry/evaluators.json` was deleted in commit `945164f` with the Tamarind
integration, which is why `registry-check` currently returns `status: missing`.
proto-tools supplies 140 tools with categories, schemas and documented limits —
the `applicable_to` and `cost` fields §4 asks for. `measures` and `status` are
added by curation.

This closes the §77 inversion as a side effect: `bind` and `registry-check`
read one file, so "this sequence is usable" and "this mechanism is evaluable"
are answered against the same source of truth.

Unchanged from litkb 0.1.0: coverage is measured over mechanism classes, output
is typed `EvidenceItem[]` per §6.2, `support` is mandatory before L1, and
rejections ship as a visible artifact.

## 7. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Fabricated sequences pass every constraint check | **High** | §5 source confirmation via re-grep |
| Constraint table drifts from the Pydantic models | Med | `constraint_source` per field; re-run `proto-sync` |
| Two-tier reading costs more than expected | Med | `screen` is the budget control; `dig` runs on a flagged subset with `-n` |
| Semantic search returns topically-near, mechanistically-irrelevant papers | Med | `screen` is also an eligibility filter; papers yielding no mechanism are recorded as rejections |
| Structure-input tools unreachable from literature sequences | Low | Documented; `bind` records direct bindings only and does not chain a fold step |

## 8. Success criteria

- [ ] `proto-sync` produces a catalogue entry for every tool `proto-tools list` reports
- [ ] Every kept artifact names at least one tool and the checks it passed
- [ ] Every rejected artifact names the check it failed
- [ ] No artifact reaches `artifacts[]` with `confirmed_in_source: false`
- [ ] `unknown` constraint checks yield `unverified`, never `runnable`
- [ ] Mechanism classes with no resolvable tool report `requires_new_evaluator`
- [ ] The RF instance produces at least one runnable protein sequence traceable to a named paper
- [ ] `STRUCTURAL` and the grep `extract` path are deleted, not deprecated

## 9. Open questions

1. Who curates `measures` and `status` on the 140 catalogue entries? Untouched,
   every tool stays `needs_calibration`, and §6 of the framework then forbids
   using any of them to rank.
2. Should `bind` model the fold-then-inverse-fold chain, making structure-input
   tools reachable from a sequence? Out of scope here; it changes `bind` from a
   checker into a planner.
3. `sequence_location: supplementary` depends on paperclip having ingested the
   supplement. Coverage is unmeasured.
