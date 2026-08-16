# Program Contract

The declarative form proto-language parses, and the vocabulary it resolves keys against.

## Primitives

| Primitive | Role |
|---|---|
| `Sequence` | A typed string (dna, rna, protein) plus optional logits, structure, metadata |
| `Segment` | One design region. Holds proposal and result sequences |
| `Construct` | Ordered segments that concatenate into the full molecule |
| `Generator` | Proposes new sequences for a segment |
| `Constraint` | Scores a sequence against one property |
| `Optimizer` | Drives propose → score → select over many rounds |
| `Program` | Chains optimizer stages |

## The scoring convention

**A constraint returns 0.0 when satisfied and 1.0 when maximally violated.** The optimizer minimizes the weighted sum across all active constraints. Getting this direction backwards silently optimizes for the opposite of the objective, so assert it on a known-good and known-bad input before trusting any run.

## JSON structure

```json
{
  "name": "<slug>",
  "description": "<what this designs and why these thresholds>",
  "version": "1.0",
  "num_results": 20,
  "constructs": [
    {
      "id": "construct1",
      "type": "protein",
      "segments": [{ "id": "<segment-id>", "label": "<human label>", "length": 371 }]
    }
  ],
  "optimization_stages": [
    {
      "generators": [
        {
          "key": "<registry key>",
          "targets": ["<segment-id>"],
          "config": {
            "masking_strategy": {
              "method": "random",
              "num_mutations": 8,
              "fixed_positions": [1, 2, 3]
            }
          }
        }
      ],
      "constraints": [
        { "key": "<registry key>", "targets": ["<segment-id>"], "config": { } }
      ],
      "optimizer": { "method": "mcmc", "config": { "num_steps": 200 } }
    }
  ]
}
```

Multiple entries in `optimization_stages` run in sequence, sharing constructs by identity. Use this for cheap-filter-then-expensive-score funnels.

## Resolving keys

Keys are kebab-case and live in the registries, not in model names:

- Generators — `proto_language/generator/generator_registry.py`. Modules present include esm2, esm3, evo1, evo2, progen2, proteinmpnn, ligandmpnn, fampnn, mpnn_mutation, semigreedy_mutation, msa, position_weight, random_protein, random_nucleotide, rfdiffusion_mpnn_binder, freebindcraft.
- Constraints — `proto_language/constraint/constraint_registry.py`, grouped under `protein_quality/`, `protein_structure/`, `sequence_composition/`, `sequence_alignment/`, `sequence_annotation/`, `sequence_scoring/`, `rna_*`.
- Optimizers — `mcmc`, `gradient`, `rejection-sampling`, `beam-search`, `genetic-algorithm`, `cycling`. Confirm exact spelling against `proto_language/optimizer/`.

Working examples ship in `examples/jsons/` and `examples/scripts/` of the proto-language repository. `toy.json` is the minimal valid program. `protorepressor.py` is the closest reference for a staged DNA-binding protein design.

## Choosing an optimizer

| Optimizer | Behavior | Use when |
|---|---|---|
| `rejection-sampling` | Independent draws, score, keep best. Fully parallel | First pass, wide exploration, cheap fan-out |
| `mcmc` | Metropolis-Hastings from a seed sequence | Refining a known scaffold toward a target. The default for variant design |
| `genetic-algorithm` | Population, crossover, mutation, selection | Combining independently-good mutations |
| `beam-search` | Fixed-length extension over autoregressive models | Generating from Evo or ProGen |
| `gradient` | SGD/Adam through differentiable constraints | Only when every constraint provides gradients |
| `cycling` | Alternates conditioning and generation | Structure-predict ↔ inverse-fold feedback |

## Masking and immutable regions

`masking_strategy` selects which positions a masked language model is allowed to change.

- `fixed_positions` — 1-indexed positions never selected for mutation. This is the mechanism for protecting a functional domain.
- `num_mutations` — exact count of positions to mask. Mutually exclusive with `mask_fraction`.
- `mask_fraction` — proportion of *designable* positions, which excludes anything in `fixed_positions`.
- `method` — `random`, `entropy` (highest model uncertainty), or `max-logit` (lowest model confidence in its top call). The scored methods require `model_name`.

Seed explicitly when reproducibility matters; selection flows through an explicit RandomState.

## Cost discipline

Structure prediction dominates runtime. A stage that folds every proposal is the expensive one. Put length, complexity, repetitiveness, and identity constraints in an earlier stage so structure prediction only sees candidates that already passed the cheap gates.
