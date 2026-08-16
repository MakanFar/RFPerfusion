---
name: visualize-sequence-design
description: Compare an input biological sequence with a final designed sequence and visualize their differences. Use after protein or nucleotide design, mutation, inverse-folding, generation, or optimization runs when both sequences are available.
---

# Visualize Sequence Design

1. Obtain the exact input sequence and final selected design sequence from the simulation artifacts. Never reconstruct or guess either sequence.
2. Normalize whitespace and capitalization while preserving chain boundaries and residue order.
3. Compare equal-length sequences position by position.
4. If lengths differ, use a standard biological sequence-alignment library or an existing alignment. Never compare shifted sequences positionally. If the alignment remains ambiguous, explain the ambiguity instead of producing a misleading visualization.
5. Use the `visualize` skill to create a compact, responsive, theme-aware inline visualization containing:
   - input and design sequences in aligned, wrapped rows;
   - residue-position markers;
   - changed residues highlighted in a strong contrasting color on both rows;
   - unchanged residues in a neutral color;
   - substitutions, insertions, and deletions distinguished by symbols as well as color;
   - input and design lengths, identity, and change counts.
6. Keep chain comparisons separate unless an explicit mapping says otherwise.
7. Keep the visualization focused. Do not add structural claims, mutation-effect scores, or inferred annotations.
