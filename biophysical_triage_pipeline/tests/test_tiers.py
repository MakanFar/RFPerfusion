"""Tests for biophys_triage.tiers -- the fail-open fix (T1 "could not
evaluate" -> t1_pass=False) and the correctness fixes around it.

Offline only: every structure is a hand-built biotite AtomArray written to a
temp file, never fetched.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import pytest

from biophys_triage import tiers
from tests.structure_fixtures import (
    salt_bridge_pair, write_pdb, write_cif,
)


# ---------------------------------------------------------------- Finding 1
def test_apply_filters_rejects_nan_feature():
    """A row whose feature is NaN (could not be computed) must fail, not
    pass through an unenforced constraint."""
    df = pd.DataFrame([
        {"seq_id": "ok", "mean_plddt": 80.0},
        {"seq_id": "nan_feature", "mean_plddt": np.nan},
    ])
    out = tiers.apply_filters(df, {"mean_plddt": {"min": 70.0}}, "t1")
    row = out.set_index("seq_id").loc["nan_feature"]
    assert row["t1_pass"] is np.False_ or row["t1_pass"] is False
    assert row["t1_reject_reason"] != ""
    assert out.set_index("seq_id").loc["ok", "t1_pass"]


def test_apply_filters_rejects_missing_column():
    """A filter rule referencing a column the tier never produced must fail
    every row, with a reason naming what's missing -- not be silently
    skipped as an absent constraint."""
    df = pd.DataFrame([{"seq_id": "x"}])
    out = tiers.apply_filters(df, {"mean_plddt": {"min": 70.0}}, "t1")
    assert not out.loc[0, "t1_pass"]
    assert "mean_plddt" in out.loc[0, "t1_reject_reason"]


def test_apply_filters_consults_t1_error():
    """A structure that failed to parse (t1_error set) must fail with that
    error as the reject reason, even though its other feature columns look
    fine -- this is the dominant fail-open fix."""
    df = pd.DataFrame([{
        "seq_id": "bad_structure", "t1_error": "ValueError: boom",
        "mean_plddt": 99.0, "salt_bridges_per_100aa": 99.0,
    }])
    out = tiers.apply_filters(
        df, {"mean_plddt": {"min": 70.0}, "salt_bridges_per_100aa": {"min": 1.0}}, "t1")
    assert not out.loc[0, "t1_pass"]
    assert out.loc[0, "t1_reject_reason"] == "ValueError: boom"


def test_apply_filters_still_passes_clean_rows():
    """The stricter filter must not reject rows with real, in-range values."""
    df = pd.DataFrame([{"seq_id": "clean", "mean_plddt": 90.0}])
    out = tiers.apply_filters(df, {"mean_plddt": {"min": 70.0}}, "t1")
    assert out.loc[0, "t1_pass"]
    assert out.loc[0, "t1_reject_reason"] == ""


# ---------------------------------------------------------------- Finding 2
def test_t1_reads_pdb_and_cif_equivalently(tmp_path):
    """A .cif input must be read (via biotite's pdbx reader), not silently
    dropped through the t1_error catch-all the way a bare PDB reader call
    would drop it."""
    structure = salt_bridge_pair("A", b_factor=95.0)
    pdb_path = write_pdb(structure, tmp_path / "s.pdb")
    cif_path = write_cif(structure, tmp_path / "s.cif")

    df = pd.DataFrame([
        {"seq_id": "pdb_seq", "structure_path": pdb_path},
        {"seq_id": "cif_seq", "structure_path": cif_path},
    ])
    out = tiers.t1_structure_audit(df, {"plddt_min": 70.0, "salt_bridge_cutoff_a": 4.0})
    out = out.set_index("seq_id")

    assert "t1_error" not in out.columns or out["t1_error"].isna().all()
    assert out.loc["pdb_seq", "n_residues"] == out.loc["cif_seq", "n_residues"]
    assert out.loc["cif_seq", "n_salt_bridges"] == out.loc["pdb_seq", "n_salt_bridges"] == 1


def test_t1_refuses_unknown_structure_extension(tmp_path):
    """An unsupported structure format must be refused (t1_error set, so
    apply_filters rejects it), never silently pass through as an empty
    record with no reason."""
    junk = tmp_path / "s.xyz"
    junk.write_text("not a real structure")
    df = pd.DataFrame([{"seq_id": "junk", "structure_path": str(junk)}])
    out = tiers.t1_structure_audit(df, {"plddt_min": 70.0, "salt_bridge_cutoff_a": 4.0})
    assert "t1_error" in out.columns
    assert out.loc[0, "t1_error"]

    filtered = tiers.apply_filters(out, {"mean_plddt": {"min": 70.0}}, "t1")
    assert not filtered.loc[0, "t1_pass"]
    assert filtered.loc[0, "t1_reject_reason"]


# ---------------------------------------------------------------- Finding 3
def test_t1_salt_bridges_keyed_by_chain_and_res_id(tmp_path):
    """Two chains that each number their own ion pair 1/2 must be counted as
    two distinct salt bridges, not collapsed into one by res_id-only dedup.
    The low-confidence chain's pair must also not leak into the other
    chain's confidence set."""
    chain_a = salt_bridge_pair("A", b_factor=95.0, x0=0.0)     # confident
    chain_b = salt_bridge_pair("B", b_factor=40.0, x0=20.0)    # not confident
    combined = chain_a + chain_b
    path = write_pdb(combined, tmp_path / "two_chain.pdb")

    df = pd.DataFrame([{"seq_id": "complex", "structure_path": path}])
    out = tiers.t1_structure_audit(df, {"plddt_min": 70.0, "salt_bridge_cutoff_a": 4.0})
    row = out.iloc[0]

    # Both inter-chain pairs are real geometric ion pairs.
    assert row["n_salt_bridges_ungated"] == 2
    # Only chain A's pair is confident; chain B's must not be gated in via a
    # res_id collision with chain A's confident residues.
    assert row["n_salt_bridges"] == 1
    assert row["n_salt_bridges_lowconf_discarded"] == 1


# ---------------------------------------------------------------- Finding 5
def test_t0_descriptors_emits_row_for_empty_sequence():
    """An empty/degenerate sequence must still get a row (one row per input
    sequence, always), carrying a failure reason -- not be dropped."""
    records = [("real", "MKVLAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"),
               ("empty", ""), ("stars_only", "***")]
    out = tiers.t0_descriptors(records, {"target_ph": 7.0})
    assert set(out["seq_id"]) == {"real", "empty", "stars_only"}
    empty_row = out.set_index("seq_id").loc["empty"]
    assert empty_row["length"] == 0
    assert isinstance(empty_row.get("t0_error"), str) and empty_row["t0_error"]


# ---------------------------------------------------------------- Finding 9
def test_cvp_bias_matches_documented_formula():
    """cvp_bias must equal (D+E+K+R)-(N+Q+S+T) per 100 residues exactly as
    documented in its adjacent comment -- Tyr must not be subtracted."""
    seq = "DEKR" * 3 + "Y" * 10 + "AAAA"  # heavy on charged + a pile of Tyr
    records = [("s", seq)]
    out = tiers.t0_descriptors(records, {"target_ph": 7.0})
    row = out.iloc[0]
    L = row["length"]
    counts = {a: seq.count(a) for a in set(seq)}
    charged = sum(counts.get(a, 0) for a in "DEKR") / L
    polar_no_tyr = sum(counts.get(a, 0) for a in "NQST") / L
    expected = 100.0 * (charged - polar_no_tyr)
    assert row["cvp_bias"] == pytest.approx(expected)
    # Tyr must still count in the separately-reported polar_uncharged_frac,
    # confirming POLAR_UNCHARGED itself was left untouched.
    assert row["polar_uncharged_frac"] == pytest.approx(
        sum(counts.get(a, 0) for a in "NQSTY") / L)


# ---------------------------------------------------------------- Finding 10
def test_top_fraction_ranks_within_survivors_only():
    """keep_top_fraction must rank within rows that already pass this tier's
    other filters, not the whole batch -- otherwise already-rejected rows
    eat into the fraction and a 60% cutoff can retain far fewer than 60% of
    what's actually still in play."""
    df = pd.DataFrame({
        "seq_id": [f"s{i}" for i in range(10)],
        "score": [10, 9, 8, 7, 6, 5, 4, 3, 2, 1],
        # The 5 highest scores were already rejected by an earlier hard filter.
        "t0_pass": [False] * 5 + [True] * 5,
        "t0_reject_reason": ["hard filter"] * 5 + [""] * 5,
    })
    out = tiers.top_fraction(df, "score", 0.6, "t0")
    # 60% of the 5 surviving rows = 3, not 0 (which a whole-batch ranking
    # would produce, since the top 60% by score are all pre-rejected).
    assert out["t0_pass"].sum() == 3
    assert set(out.loc[out["t0_pass"], "seq_id"]) == {"s5", "s6", "s7"}
    # Rows that failed the earlier filter keep their original reason.
    assert out.loc[out["seq_id"] == "s0", "t0_reject_reason"].iloc[0] == "hard filter"
