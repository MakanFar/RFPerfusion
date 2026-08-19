from calib import propose

ROWS = [{"pdb_id": f"P{i}", "avg_plddt": 0.70 + 0.005 * i,
         "tm_score": 0.55 + 0.0025 * i + (0.01 if i % 2 else -0.01)}
        for i in range(40)]
META = {"name": "PDB post-cutoff single chains", "held_out": True,
        "cutoff_date": "2020-05-01",
        "selection": "X-ray, single chain, 50-400 aa, released after cutoff"}


def test_the_proposal_is_a_v2_curation_fragment():
    out = propose.build("esmfold-prediction", "avg_plddt", ROWS, META)

    rec = out["esmfold-prediction"]["metrics"]["avg_plddt"]
    assert rec["status"] == "validated"
    assert rec["measured_error"]["kind"] == "resolution"
    assert rec["measured_error"]["value"] > 0
    assert rec["benchmark"]["held_out"] is True
    assert rec["benchmark"]["cutoff_date"] == "2020-05-01"


def test_validity_is_recorded_beside_the_benchmark_not_in_measured_error():
    """measured_error is what the margin rule consumes; validity is what a
    reviewer judges the promotion by. Conflating them is the units error the
    spec exists to prevent."""
    rec = propose.build("esmfold-prediction", "avg_plddt", ROWS,
                        META)["esmfold-prediction"]["metrics"]["avg_plddt"]

    assert "spearman" in rec["benchmark"]["validity"]
    assert "spearman" not in rec["measured_error"]


def test_a_refused_measurement_produces_no_promotion():
    """A flat slope must not yield a record at all -- not a record with a
    large error, and not a record with status needs_calibration that a reader
    might mistake for a measured result."""
    flat = [{"pdb_id": f"P{i}", "avg_plddt": 0.70 + 0.005 * i, "tm_score": 0.8}
            for i in range(40)]
    out = propose.build("esmfold-prediction", "avg_plddt", flat, META)

    assert out["promoted"] is False
    assert "slope" in out["reason"]
    assert "esmfold-prediction" not in out
