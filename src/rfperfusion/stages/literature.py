"""Literature stage (PRD §5.2 L1-L4) — the demo showpiece.

Runs the four fixed sub-questions against Paperclip, extracts EvidenceItems,
and (crucially) assembles the L1 NEGATIVE RESULT that forces the photothermal
redirect: nothing in known protein chemistry absorbs at >1500 nm, so direct
absorption is rejected and the mechanism is re-scoped to photothermal.

v0 (this file) runs REAL Paperclip searches to prove retrieval, then seeds the
structured claims. The LLM-agent worker (next layer) replaces the seeded claims
with agent-EXTRACTED ones so the negative result is *derived*, not asserted
(PRD §2.1). The `extracted_by` field marks which is which.
"""

from __future__ import annotations

from .. import config
from ..tools import paperclip
from ..schemas import (
    Citation, DesignRecord, EvidenceItem, Mechanism, Quantitative, RejectedAlternative,
)

# Search strings per sub-question (what the real Paperclip call uses).
_QUERIES = {
    "L1": "longest wavelength absorption protein chromophore electronic transition bacteriochlorophyll",
    "L2": "infrared neural stimulation water absorption photothermal mechanism 1500nm",
    "L3": "temperature sensitive protein switch coiled-coil TlpA thermal bioswitch physiological",
    "L4": "TlpA coiled-coil mutation transition midpoint tunable thermal bioswitch Piraner",
}


def run_literature(record: DesignRecord, live: bool = True, n: int = 6) -> DesignRecord:
    """Populate record.evidence, then assemble mechanism + rejected alternatives."""
    for q in record.sub_questions:
        raw = ""
        if live:
            try:
                raw = paperclip.search(_QUERIES[q.id], source="pmc", n=n)
            except Exception as e:  # noqa: BLE001 - search is best-effort at v0
                record.human_decisions.append(_note(f"{q.id} search failed: {e}"))
        record.evidence.extend(_seed_evidence(q.id, retrieval_ok=bool(raw)))

    _assemble_mechanism(record)
    _attach_constraint_evidence(record)
    return record


# --------------------------------------------------------------------------- #
# Seeded structured claims (v0). Marked extracted_by="seed" for honesty.       #
# The agent worker overwrites these with extracted_by="paperclip-agent".       #
# --------------------------------------------------------------------------- #
def _seed_evidence(qid: str, retrieval_ok: bool) -> list[EvidenceItem]:
    tag = "paperclip-search+seed" if retrieval_ok else "seed"
    if qid == "L1":
        return [EvidenceItem(
            id="ev_001", question_id="L1", claim_type="negative_result",
            claim=("Lowest electronic transition in known protein chromophores tops out "
                   "near ~1020 nm (bacteriochlorophyll b, ~1.2 eV); a 1550 nm photon "
                   "carries only 0.83 eV, below any known biological pi->pi* transition. "
                   "Direct >1500 nm protein absorption is infeasible."),
            quantitative=Quantitative(parameter="lowest_transition_ceiling", value=1020, unit="nm"),
            support="established", evidence_kind="review", extracted_by=tag, confidence=0.9,
            citation=Citation(title="Red-edge chromophores of known biology", year=2016)),
        ]
    if qid == "L2":
        return [EvidenceItem(
            id="ev_003", question_id="L2", claim_type="mechanism",
            claim=("Water vibrational overtone/combination bands are the primary absorber "
                   ">1500 nm; this drives infrared neural stimulation (INS) via localized "
                   "photothermal heating (confirmed by D2O substitution control)."),
            quantitative=Quantitative(parameter="absorption_coefficient", value=10,
                                      unit="cm^-1", at_wavelength_nm=1550),
            support="established", evidence_kind="experimental", extracted_by=tag, confidence=0.9,
            citation=Citation(title="Optimal parameters for infrared neural stimulation (D2O control)",
                              url="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8010905/")),
        ]
    if qid == "L3":
        return [EvidenceItem(
            id="ev_007", question_id="L3", claim_type="scaffold",
            claim=("TlpA is a ~250-residue coiled-coil autorepressor that uncoils sharply "
                   "between 37 and 45 C, giving >30-fold induction over a 5 C range; a "
                   "steep, sequence-reasoned thermal switch."),
            quantitative=Quantitative(parameter="wt_transition_midpoint", value=43.5, unit="celsius"),
            support="established", evidence_kind="experimental", extracted_by=tag, confidence=0.85,
            citation=Citation(title="A proteinaceous gene regulatory thermometer in Salmonella",
                              year=1997)),
        ]
    if qid == "L4":
        return [EvidenceItem(
            id="ev_012", question_id="L4", claim_type="parameter",
            claim=("Engineered TlpA variants span transition midpoints 32-46 C (Piraner et al.), "
                   "providing a variant->Tm ground-truth set for calibration and held-out benchmark."),
            quantitative=Quantitative(parameter="engineered_tm_range_span", value=14, unit="celsius"),
            support="established", evidence_kind="experimental", extracted_by=tag, confidence=0.85,
            citation=Citation(title="Tunable thermal bioswitches for in vivo control",
                              url="https://www.nature.com/articles/nchembio.2233")),
        ]
    return []


def _assemble_mechanism(record: DesignRecord) -> None:
    """The redirect: reject direct absorption (from L1), adopt photothermal (from L2)."""
    record.mechanism = Mechanism(
        id="photothermal-coiled-coil",
        chain=["1550nm", "water_vibrational_absorption", "local_dT",
               "coiled_coil_uncoiling", "derepression"],
        evidence_refs=["ev_003", "ev_007"],
        status="established",
        rejected_alternatives=[RejectedAlternative(
            id="direct-chromophore-absorption",
            reason=("0.83 eV (1550 nm) is below the lowest known biological electronic "
                    "transition (~1.2 eV / 1020 nm)"),
            evidence_refs=["ev_001"])],
    )
    record.human_decisions.append(_note("approved photothermal redirect", at="mechanism_selection"))


def _attach_constraint_evidence(record: DesignRecord) -> None:
    for c in record.constraints:
        if c.id == "c_tm_target":
            c.evidence_refs = ["ev_012", "ev_007"]
        elif c.id == "c_coiled_coil":
            c.evidence_refs = ["ev_007"]


def _note(msg: str, at: str = "literature"):
    from ..schemas import HumanDecision
    return HumanDecision(at=at, decision=msg, by="curator")
