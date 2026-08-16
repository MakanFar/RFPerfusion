From the repository root:

uv run --with anthropic python litterature_search_from_concept/paperclip_kb.py \
  litterature_search_from_concept/context.txt \
  --slug rfp \
  --output-dir litterature_search_from_concept/outputs/rfp \
  --dry-run

Inspect the generated plan, then reuse that exact plan for the full run:

uv run --with anthropic python litterature_search_from_concept/paperclip_kb.py \
  litterature_search_from_concept/context.txt \
  --slug rfp \
  --output-dir litterature_search_from_concept/outputs/rfp \
  --plan-file litterature_search_from_concept/outputs/rfp/plan_rfp.json

The knowledge base contains discovery leads, not independently verified claims.
