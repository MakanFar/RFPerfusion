"""Evaluation stage (PRD §5.2 Eval Agent + §7 uncertainty).

Computes every constraint it can for FREE and honestly, and marks Modal-backed
constraints as PENDING (never fabricates ESMFold/PyRosetta numbers). Each score
carries a confidence; OOD candidates are flagged. Hard-constraint violations are
recorded so ranking can exclude them.

Free (computed now, real):
  c_dbd_intact  - DNA-binding domain unmutated (exact check)
  c_novelty     - normalized edit distance from WT (embedding proxy at v0)
Modal-backed (real numbers require approved deploy):
  c_fold_conf   - ESMFold pLDDT
  c_tm_target   - PyRosetta ddG + calibrated Tm regression
  c_coiled_coil - DSSP helix content / heptad register
"""

from __future__ import annotations

from ..schemas import Aggregate, Candidate, DesignRecord, ScoredCandidate, ScoreEntry

_MODAL_BACKED = {"c_fold_conf", "c_tm_target", "c_coiled_coil", "c_off_state",
                 "c_cooperativity", "c_aggregation"}


def evaluate(candidates: list[Candidate], record: DesignRecord,
             use_modal: bool = False) -> list[ScoredCandidate]:
    dbd_end = record.scaffold.immutable_regions[0][1] if record.scaffold.immutable_regions else 120
    wt = record.scaffold.sequence or ""
    out: list[ScoredCandidate] = []
    for c in candidates:
        sc = ScoredCandidate(**c.model_dump())
        _score_free(sc, wt, dbd_end)
        if use_modal:
            _score_modal(sc, record)  # real proto-tools calls, guarded inside
        else:
            for cid in _MODAL_BACKED & {c.id for c in record.constraints}:
                sc.flags.append(f"{cid}:pending_modal")
        _aggregate(sc, record)
        out.append(sc)
    return out


def _score_free(sc: ScoredCandidate, wt: str, dbd_end: int) -> None:
    # c_dbd_intact: no mutation position within [1, dbd_end]
    bad = [m for m in sc.mutations if _pos(m) is not None and _pos(m) <= dbd_end]
    dbd_ok = not bad
    sc.scores["c_dbd_intact"] = ScoreEntry(value=1.0 if dbd_ok else 0.0, unit="bool",
                                           confidence=1.0, method="sequence_mask_check")
    if not dbd_ok:
        sc.hard_violations.append("c_dbd_intact")

    # c_novelty: normalized Hamming distance from WT over the aligned region
    if wt and sc.sequence and len(sc.sequence) == len(wt):
        diff = sum(1 for a, b in zip(wt, sc.sequence) if a != b)
        nov = diff / len(wt)
        sc.scores["c_novelty"] = ScoreEntry(value=round(nov, 4), unit="fraction",
                                            confidence=0.6, method="hamming_proxy(v0)")


def _score_modal(sc: ScoredCandidate, record: DesignRecord) -> None:
    """Real ESMFold/PyRosetta/DSSP via proto-tools/Modal. Guarded per-tool."""
    raise NotImplementedError(
        "Modal-backed scoring requires approved deploys (esmfold, pyrosetta, dssp). "
        "Wire via tools.proto.run_tool(..., allow_deploy=True) once approved."
    )


def _aggregate(sc: ScoredCandidate, record: DesignRecord) -> None:
    """Interval-based aggregate (PRD §7.1): rank by ci_low. With Modal scores
    pending, aggregate reflects only resolved constraints and is widened to
    signal low information."""
    vals = [(s.value, s.confidence) for s in sc.scores.values()]
    if not vals:
        sc.aggregate = Aggregate(score=0.0, ci_low=0.0, ci_high=0.0)
        return
    mean = sum(v for v, _ in vals) / len(vals)
    conf = sum(c for _, c in vals) / len(vals)
    half = (1 - conf) * 0.5
    sc.aggregate = Aggregate(score=round(mean, 3),
                             ci_low=round(max(0.0, mean - half), 3),
                             ci_high=round(min(1.0, mean + half), 3))


def _pos(mutation: str):
    digits = "".join(ch for ch in mutation if ch.isdigit())
    return int(digits) if digits else None
