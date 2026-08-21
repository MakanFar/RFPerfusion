"""The seam between the calibration harness and the registry that consumes it.

A proposal the registry would refuse is useless, and a proposal the registry
accepts but that changes nothing is equally useless -- so both halves are
pinned here rather than assumed. These live in litkb's suite because they need
`litkb.proto`; the harness itself is a sibling project and is reached the way
the operator reaches it, by path.

Offline by construction: the rows are synthetic and no proto tool is called.
Ground truth cannot come from a proto tool anyway, and a test that needed a
GPU would not be a test.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "calibration"))

from calib import propose  # noqa: E402 -- after the path insert, by necessity
from litkb import proto  # noqa: E402

# Slope 0.5 of TM-score per pLDDT with a scatter of 0.01, over the [0.7, 1.0]
# band where the gates are written. Signs in blocks of four so the pattern is
# uncorrelated with avg_plddt and the fitted slope is the nominal one.
ROWS = [{"pdb_id": f"P{i:03d}", "avg_plddt": 0.70 + 0.005 * i, "length": 200 + i,
         "tm_score": 0.55 + 0.0025 * i + 0.01 * (1, -1, -1, 1)[i % 4]}
        for i in range(40)]
META = {"name": "PDB post-cutoff single chains", "held_out": True,
        "cutoff_date": "2020-05-01",
        "selection": "X-ray, single chain, 50-400 aa, released after cutoff"}


def _fragment():
    frag = propose.build("esmfold-prediction", "avg_plddt", ROWS, META)
    assert frag["promoted"] is True
    frag.pop("promoted")
    return frag


def _catalog():
    return json.loads((_ROOT / "registry" / "proto_catalog.json").read_text())


def test_the_proposal_satisfies_the_registrys_own_v2_rules():
    """The harness and the registry were written against the same spec but by
    different code. If the proposal does not survive `apply_calibration`, the
    whole run produces a file nobody can promote."""
    out, orphans = proto.apply_calibration(
        _catalog(), {"schema_version": 2, "tools": _fragment()})

    assert orphans == []
    tool = [t for t in out["tools"] if t["key"] == "esmfold-prediction"][0]
    assert tool["status"] == "validated"


@pytest.mark.parametrize("dropped", ["measured_error", "benchmark"])
def test_a_promotion_missing_its_measurement_is_refused(dropped):
    """Framework section 6 promotes on MEASURED reliability. A bare
    `validated` flag with no number behind it is the claim it forbids, and
    the registry -- not the harness -- is the thing that has to refuse it."""
    frag = _fragment()
    frag["esmfold-prediction"]["metrics"]["avg_plddt"].pop(dropped)

    with pytest.raises(ValueError, match="esmfold-prediction:avg_plddt"):
        proto.apply_calibration(_catalog(),
                                {"schema_version": 2, "tools": frag})


def _uncalibrated_catalog():
    """The committed catalogue with every calibration reset.

    `_catalog()` reads the live registry, which now carries a real promotion
    (esmfold-prediction:avg_plddt). Using it directly would make this test's
    "before" state already-calibrated, so the transition it exists to
    demonstrate would collapse into a no-op that still passed. Reconstructing
    the pre-promotion world keeps the test measuring the thing it names.
    """
    catalog = _catalog()
    for tool in catalog["tools"]:
        tool["status"] = "needs_calibration"
        for row in tool.get("measures", []):
            row["calibration"] = {"status": "needs_calibration"}
    return catalog


def test_the_record_is_what_makes_rankable_by_non_empty():
    """The point of the whole exercise. Before this record `rankable_by` is
    empty for every term in the vocabulary -- fifteen tools can MEASURE
    fold_confidence and none of them may RANK on it, which is what section 6
    says about an uncalibrated evaluator. One promoted metric is what
    separates the two lists for the first time."""
    catalog = _uncalibrated_catalog()
    vocab = json.loads((_ROOT / "registry" / "property_vocabulary.json").read_text())

    before = proto.resolve_properties(["fold_confidence"], catalog, vocab)
    assert before["rankable_by"] == []
    assert before["tools"]

    after_catalog, _ = proto.apply_calibration(
        catalog, {"schema_version": 2, "tools": _fragment()})
    after = proto.resolve_properties(["fold_confidence"], after_catalog, vocab)

    assert after["rankable_by"] == ["esmfold-prediction"]
    assert after["tools"] == before["tools"]
