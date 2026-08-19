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


# Slope 0.5, scatter 0.01, over the [0.7, 1.0] band, plus low-confidence rows
# that the 0.7 floor keeps out of the fit.
def _rows(noise=0.01, n=40, slope=0.5):
    return [{"pdb_id": f"P{i:03d}", "avg_plddt": 0.70 + 0.005 * i,
             "length": 200 + i,
             "tm_score": 0.55 + slope * 0.005 * i + noise * (1, -1, -1, 1)[i % 4]}
            for i in range(n)]


def test_an_anti_predictive_metric_is_not_promoted():
    """The failure C1 named: with |slope| the fit below returns a
    healthy-looking measured_error, the registry accepts it because the value
    is positive, and the system is licensed to rank candidates in exactly the
    inverted order framework section 6 exists to forbid."""
    inverted = [{"pdb_id": r["pdb_id"], "avg_plddt": r["avg_plddt"],
                 "length": r["length"], "tm_score": 1.5 - r["tm_score"]}
                for r in _rows()]
    out = propose.build("esmfold-prediction", "avg_plddt", inverted, META)

    assert out["promoted"] is False
    assert "negative" in out["reason"]
    assert "esmfold-prediction" not in out


def test_the_applicability_domain_spans_only_the_rows_that_entered_the_fit():
    """The domain is a claim about where the number holds. Rows below the 0.7
    floor never entered the fit, so stretching the band to cover them claims
    the resolution was measured somewhere it was not."""
    rows = _rows() + [{"pdb_id": "LOW", "avg_plddt": 0.30,
                       "tm_score": 0.20, "length": 900}]
    rec = propose.build("esmfold-prediction", "avg_plddt", rows,
                        META)["esmfold-prediction"]["metrics"]["avg_plddt"]

    assert rec["applicability_domain"]["length"] == [200, 239]


def test_the_record_says_where_the_slope_was_taken():
    """`measured_error.n` counts the rows in the band, not the size of the
    benchmark. Without the band and the chain count a reviewer cannot tell
    which of the two the number is."""
    rows = _rows() + [{"pdb_id": "LOW", "avg_plddt": 0.30,
                       "tm_score": 0.20, "length": 120}]
    rec = propose.build("esmfold-prediction", "avg_plddt", rows,
                        META)["esmfold-prediction"]["metrics"]["avg_plddt"]

    assert rec["benchmark"]["validity"]["slope_band"] == [0.7, 1.0]
    assert rec["benchmark"]["validity"]["n_chains_measured"] == 41
    assert rec["measured_error"]["n"] == 40


def test_a_very_tight_fit_does_not_round_down_to_a_non_positive_error():
    """`apply_calibration` refuses a measured_error whose value is not
    positive, so a fit tighter than the fourth decimal would round itself out
    of a promotion it earned."""
    rec = propose.build("esmfold-prediction", "avg_plddt", _rows(noise=1e-6),
                        META)["esmfold-prediction"]["metrics"]["avg_plddt"]

    assert rec["measured_error"]["value"] > 0


def test_the_benchmark_records_what_the_date_filter_does_not_buy():
    """"Held out" rests on release date alone. A post-cutoff entry can be a
    point mutant or close homolog of a pre-cutoff structure whose sequence
    ESMFold saw, which biases the resolution finer than earned. No homology
    screen is performed, so the record has to say so rather than let the
    reader read `held_out: true` as more than it is."""
    rec = propose.build("esmfold-prediction", "avg_plddt", _rows(),
                        META)["esmfold-prediction"]["metrics"]["avg_plddt"]

    assert "homology" in rec["benchmark"]["limitations"]
