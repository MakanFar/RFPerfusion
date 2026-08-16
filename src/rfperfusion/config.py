"""Project constants (PRD §2, §5.2, §6.3). Numbers here are DESIGN INPUTS, not
literature-derived values — literature-derived numbers get filled into the
Design Record by the Literature stage with citations attached.
"""

from __future__ import annotations

from pathlib import Path

from .schemas import Constraint, ResearchQuestion, TargetRange

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTO_PROJECT = REPO_ROOT / "proto"          # isolated proto-tools uv runtime
OUTPUTS = REPO_ROOT / "outputs"

# --- The design goal / target (PRD §2.4) ---------------------------------- #
GOAL = "Design a protein switch actuated by >1500 nm illumination"
TM_TARGET_C = 41.0            # transition midpoint target
TM_TOLERANCE_C = 0.5
BASELINE_C = 37.0
WAVELENGTHS_NM = [1550, 1930]  # primary / tighter-confinement alternative (§2.2)

# --- Scaffold (PRD §2.3). uniprot/sequence RESOLVED AT RUNTIME by Paperclip. #
SCAFFOLD_NAME = "TlpA"
SCAFFOLD_ORGANISM = "Salmonella typhimurium"
SCAFFOLD_LENGTH_AA_HINT = 371
DBD_END_HINT = 120            # N-terminal DNA-binding domain ends ~here; CONFIRM at M0

# --- The four fixed literature sub-questions (PRD §5.2 L1-L4) -------------- #
SUB_QUESTIONS = [
    ResearchQuestion(
        id="L1",
        question="What is the longest-wavelength electronic transition in any known protein chromophore?",
        expected_finding="Ceiling ~1020 nm -> direct absorption at >1500 nm is infeasible (the load-bearing negative result).",
    ),
    ResearchQuestion(
        id="L2",
        question="What absorbs >1500 nm in biological tissue, and what happens downstream?",
        expected_finding="Water vibrational bands; infrared neural stimulation (INS); photothermal transduction.",
    ),
    ResearchQuestion(
        id="L3",
        question="What protein switches respond to small temperature changes near physiological?",
        expected_finding="TlpA, TcI, TRPV; coiled-coil thermal switches.",
    ),
    ResearchQuestion(
        id="L4",
        question="What mutations shift coiled-coil transition midpoints, and by how much?",
        expected_finding="Piraner variant->Tm table; heptad-position rules.",
    ),
]


def default_constraint_set() -> list[Constraint]:
    """PRD §6.3 constraint table. `evaluator` names the proto-tools tool that
    implements each; evidence_refs are filled in once the Literature stage runs.
    """
    lo, hi = TM_TARGET_C - TM_TOLERANCE_C, TM_TARGET_C + TM_TOLERANCE_C
    return [
        Constraint(id="c_tm_target", kind="target_range",
                   description=f"Transition midpoint in [{lo}, {hi}] C",
                   target=TargetRange(min=lo, max=hi, unit="celsius"),
                   evaluator="pyrosetta_ddg + calibrated_tm_regression", hard=True, weight=1.0),
        Constraint(id="c_off_state", kind="boolean",
                   description="Predicted stable dimer at 37 C (no basal leak)",
                   evaluator="esmfold + interface_stability", hard=True),
        Constraint(id="c_dbd_intact", kind="boolean",
                   description="DNA-binding domain (~1-120) unmutated",
                   evaluator="sequence_mask_check", hard=True),
        Constraint(id="c_coiled_coil", kind="threshold",
                   description="Heptad register preserved; DSSP helix content within 10% of WT",
                   evaluator="dssp + heptad_register", hard=True),
        Constraint(id="c_fold_conf", kind="threshold",
                   description="ESMFold pLDDT >= 70 over the coiled-coil",
                   evaluator="esmfold", hard=True),
        Constraint(id="c_cooperativity", kind="threshold",
                   description="Interface packing >= WT proxy (switch sharpness)",
                   evaluator="pyrosetta_interface", hard=False),
        Constraint(id="c_aggregation", kind="boolean",
                   description="No introduced aggregation-prone motifs",
                   evaluator="aggregation_motif_scan", hard=False),
        Constraint(id="c_novelty", kind="distance",
                   description="ESM-embedding distance from all known TlpA variants",
                   evaluator="esm2_embedding", hard=False),
    ]
