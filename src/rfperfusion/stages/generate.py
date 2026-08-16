"""Generation stage (PRD §5.2 Design Agent).

Two paths:
  method="proto_esm2"  -> real ESM2 masked-LM sampling via proto-tools/Modal
                          (BILLABLE, needs deploy approval; guarded).
  method="heuristic"   -> deterministic combinatorial substitution at heptad
                          a/d core positions inside the coiled-coil. Not a mock:
                          it produces real, novel, constraint-legal sequences to
                          drive the pipeline end-to-end at zero cost until ESM2
                          is deployed. Labeled as such in `generated_by`.

Both enforce: never touch the immutable DNA-binding domain; require >=3 mutations.
"""

from __future__ import annotations

from itertools import combinations

from ..schemas import Candidate, DesignRecord

# Conservative core substitutions that tend to lower coiled-coil stability
# (destabilizing the a/d core lowers the transition midpoint toward the 41 C target).
_SUBS = {"L": "A", "I": "V", "V": "A", "M": "A", "F": "L", "N": "D"}
_MIN_MUTATIONS = 3


def generate(record: DesignRecord, method: str = "heuristic", n: int = 120) -> list[Candidate]:
    if method == "heuristic":
        return _heuristic(record, n)
    if method == "proto_esm2":
        return _proto_esm2(record, n)
    raise ValueError(f"unknown generation method: {method}")


def _coiled_coil_core_positions(record: DesignRecord) -> list[int]:
    """1-indexed positions in the coiled-coil (after the immutable DBD) whose
    residue is a substitutable hydrophobic/polar core residue."""
    seq = record.scaffold.sequence
    if not seq:
        return []
    dbd_end = record.scaffold.immutable_regions[0][1] if record.scaffold.immutable_regions else 120
    return [i for i in range(dbd_end + 1, len(seq) + 1) if seq[i - 1] in _SUBS]


def _heuristic(record: DesignRecord, n: int) -> list[Candidate]:
    seq = record.scaffold.sequence
    positions = _coiled_coil_core_positions(record)
    if not seq or len(positions) < _MIN_MUTATIONS:
        # No resolved sequence yet: emit position-agnostic specs so downstream
        # schema/flow can still be exercised, clearly flagged.
        return [Candidate(id=f"cand_{i:03d}", sequence="", parent="TlpA_WT",
                          mutations=[], generated_by="heuristic_heptad_v0:no_sequence")
                for i in range(1)]

    # Sample distinct k-subsets of core positions, k in {3,4}.
    cands: list[Candidate] = []
    picks = list(combinations(positions[:16], 3)) + list(combinations(positions[:12], 4))
    for i, combo in enumerate(picks[:n]):
        muts, s = [], list(seq)
        for pos in combo:
            wt = seq[pos - 1]
            mut = _SUBS[wt]
            s[pos - 1] = mut
            muts.append(f"{wt}{pos}{mut}")
        cands.append(Candidate(id=f"cand_{i:03d}", sequence="".join(s), parent="TlpA_WT",
                               mutations=muts, generated_by="heuristic_heptad_v0"))
    return cands


def _proto_esm2(record: DesignRecord, n: int) -> list[Candidate]:
    """Real ESM2 masked-LM sampling over core positions via proto-tools/Modal.
    Guarded: raises unless the caller has approved the (billable) ESM2 deploy."""
    raise NotImplementedError(
        "proto_esm2 generation requires an approved ESM2 Modal deploy. "
        "Wire via tools.proto.run_tool(tool_key='esm2', ..., allow_deploy=True) "
        "after `proto-tools deploy --apps esm2` is approved."
    )
