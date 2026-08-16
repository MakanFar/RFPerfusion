"""Tests for biophys_triage.run -- FASTA parsing edge cases, the
duplicate-id and empty-input guards, and tier-rank sort order.
"""
from __future__ import annotations
import pandas as pd
import pytest

from biophys_triage import run


# ---------------------------------------------------------------- Finding 12
def test_read_fasta_handles_bare_header(tmp_path):
    """A header line with no id text (a bare '>') must not crash the
    parser -- it must get a usable placeholder id instead of raising."""
    fasta = tmp_path / "bare.faa"
    fasta.write_text(">\nMKVLA\n>named seq\nMKVLB\n")
    recs = run.read_fasta(str(fasta))
    assert len(recs) == 2
    ids = [sid for sid, _ in recs]
    assert ids[1] == "named"
    assert ids[0] and ids[0] != ""  # got some non-empty placeholder, didn't raise


# ---------------------------------------------------------------- Finding 4
def test_run_exits_cleanly_on_empty_fasta(tmp_path):
    """An empty FASTA must exit with a message naming the input file, not
    crash deep inside with a bare KeyError on 'seq_id'."""
    fasta = tmp_path / "empty.faa"
    fasta.write_text("")
    with pytest.raises(SystemExit) as excinfo:
        run.run(str(fasta), out_tsv=str(tmp_path / "out.tsv"), verbose=False)
    assert str(fasta) in str(excinfo.value)


# ---------------------------------------------------------------- Finding 6
def test_run_fails_loudly_on_duplicate_seq_ids(tmp_path):
    """Duplicate FASTA ids must not be allowed to fan out the T1 merge and
    mis-attribute features; the run must fail loudly instead."""
    fasta = tmp_path / "dup.faa"
    fasta.write_text(
        ">A\n" + "MKVLA" * 20 + "\n"
        ">A\n" + "MKVLB" * 20 + "\n"
    )
    with pytest.raises(SystemExit) as excinfo:
        run.run(str(fasta), out_tsv=str(tmp_path / "out.tsv"), verbose=False)
    assert "A" in str(excinfo.value)
    assert "duplicate" in str(excinfo.value).lower()


def test_run_accepts_unique_ids(tmp_path):
    """Sanity check that the duplicate guard doesn't fire on ordinary,
    unique-id input."""
    fasta = tmp_path / "unique.faa"
    fasta.write_text(
        ">A\n" + "MKVLA" * 20 + "\n"
        ">B\n" + "MKVLB" * 20 + "\n"
    )
    df = run.run(str(fasta), out_tsv=str(tmp_path / "out.tsv"), verbose=False)
    assert set(df["seq_id"]) == {"A", "B"}


# ---------------------------------------------------------------- Finding 7
def test_output_sorted_by_tier_rank_not_string():
    """Rows must sort most-advanced-first by a defined tier rank, not by
    the 'final_tier_reached' string -- alphabetically
    'passed_T0_pending_T1' < 'passed_T1', which is backwards."""
    master = pd.DataFrame({
        "seq_id": ["never_evaluated", "real_survivor", "also_pending"],
        "final_tier_reached": ["passed_T0_pending_T1", "passed_T1", "passed_T0_pending_T1"],
        "t0_composite_z": [5.0, 0.1, 4.0],
    })
    tier_rank = master["final_tier_reached"].map(run.TIER_RANK).fillna(len(run.TIER_RANK))
    sorted_df = master.assign(_tier_rank=tier_rank.to_numpy()).sort_values(
        ["_tier_rank", "t0_composite_z"], ascending=[True, False]).drop(columns="_tier_rank")
    assert sorted_df.iloc[0]["seq_id"] == "real_survivor"
    assert list(sorted_df["final_tier_reached"]) == [
        "passed_T1", "passed_T0_pending_T1", "passed_T0_pending_T1"]


def test_run_end_to_end_sorts_t1_survivor_above_pending(tmp_path):
    """End-to-end: a real T1 survivor must sort above rows that were never
    evaluated by T1, reproducing the exact defect described for
    example/demo_results.tsv."""
    from tests.structure_fixtures import salt_bridge_pair, write_pdb

    fasta = tmp_path / "in.faa"
    # Both are long/stable enough to clear T0's default hard filters. Give
    # the never-folded one a slightly higher T0 score so a string sort would
    # (wrongly) still place it above the T1 survivor.
    seqA = "MKVLA" * 40  # gets a structure -> can reach T1
    seqB = "MKVLA" * 41  # no structure -> stays passed_T0_pending_T1
    fasta.write_text(f">A\n{seqA}\n>B\n{seqB}\n")

    struct_dir = tmp_path / "structures"
    struct_dir.mkdir()
    write_pdb(salt_bridge_pair("A", b_factor=95.0), struct_dir / "A.pdb")

    config = {
        "t0_filters": {"length": {"min": 10}},
        "t1_filters": {"mean_plddt": {"min": 70.0}},
    }
    import json
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    df = run.run(str(fasta), config_path=str(config_path), structures=str(struct_dir),
                  out_tsv=str(tmp_path / "out.tsv"), verbose=False)
    ranks = list(df["final_tier_reached"])
    assert ranks[0] == "passed_T1"
    assert ranks.index("passed_T1") < ranks.index("passed_T0_pending_T1")
