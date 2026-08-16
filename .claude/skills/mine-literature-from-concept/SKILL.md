---
name: mine-literature-from-concept
description: Build a broad Paperclip literature corpus and categorized knowledge base from a biological design concept. Use for literature reconnaissance, mechanism discovery, or finding candidate sequences, accessions, mutations, and quantitative measurements before detailed claim verification.
---

# Mine Literature From Concept

Use the repository's `litterature_search_from_concept/paperclip_kb.py` pipeline. Treat its output as a discovery index, not as verified evidence.

## Run workflow

1. Obtain a concrete biological concept as text. Preserve the user's wording in a UTF-8 concept file.
2. Choose a lowercase hyphenated slug and create a unique run directory under `litterature_search_from_concept/outputs/` using a UTC timestamp and the slug.
3. Confirm that `ANTHROPIC_API_KEY` is set without printing it and that `paperclip` resolves on `PATH`. Report a missing prerequisite precisely.
4. Generate the search plan without searching:

   ```bash
   uv run --with anthropic python litterature_search_from_concept/paperclip_kb.py \
     <concept-file> --slug <slug> --output-dir <run-dir> --dry-run
   ```

5. Read `plan_<slug>.json`. Reject generic one-word phrases, duplicates, question-form queries, and mechanism patterns unlikely to occur verbatim in papers. Revise the concept and regenerate when the plan does not span the important subproblems.
6. Reuse the reviewed plan for the full run; do not silently generate a different plan:

   ```bash
   uv run --with anthropic python litterature_search_from_concept/paperclip_kb.py \
     <concept-file> --slug <slug> --output-dir <run-dir> \
     --plan-file <run-dir>/plan_<slug>.json
   ```

7. Read [references/output-contract.md](references/output-contract.md), inspect the manifest and category counts, and report empty or unexpectedly large categories as search-quality warnings.
8. Summarize useful mechanisms and concrete identifiers while linking the run artifacts. Describe every extracted line as a lead that still requires source-level verification.

## Guardrails

- Never call a grep match verified, supported, or refuted evidence.
- Never infer that a sequence, accession, mutation, or quantity belongs to the nearby concept without opening and checking the source paper.
- Query sources separately. Do not collapse multiple sources into Paperclip's comma-separated `-s` form.
- Preserve the concept, reviewed plan, manifest, and knowledge base together for reproducibility.
- Do not place credentials in commands, plans, manifests, or reports.
