from calib import benchmark

CUTOFF = "2020-05-01"


def _entry(**over):
    base = {"pdb_id": "7ABC", "released": "2023-01-01", "method": "X-RAY DIFFRACTION",
            "n_chains": 1, "length": 200}
    base.update(over)
    return base


def test_a_post_cutoff_single_chain_is_kept():
    kept, rejected = benchmark.select([_entry()], CUTOFF)
    assert kept == ["7ABC"]
    assert rejected == []


def test_a_pre_cutoff_entry_is_rejected_as_potentially_in_training():
    """The whole held-out claim rests on this filter. ESMFold was trained on
    the PDB, so an entry released before the cutoff may be in its training
    set and would produce a number that looks measured and is not."""
    kept, rejected = benchmark.select([_entry(released="2019-06-01")], CUTOFF)
    assert kept == []
    assert "cutoff" in rejected[0]["reason"]


def test_a_multi_chain_entry_is_rejected():
    kept, rejected = benchmark.select([_entry(n_chains=3)], CUTOFF)
    assert kept == []
    assert "chain" in rejected[0]["reason"]


def test_a_chain_outside_the_length_band_is_rejected():
    short, _ = benchmark.select([_entry(length=40)], CUTOFF)
    long_, _ = benchmark.select([_entry(length=900)], CUTOFF)
    assert short == [] and long_ == []


def test_a_non_xray_entry_is_rejected():
    kept, rejected = benchmark.select([_entry(method="SOLUTION NMR")], CUTOFF)
    assert kept == []
    assert "method" in rejected[0]["reason"]


def test_every_rejection_names_its_reason():
    """Rejections ship: a filtered-out entry must say which filter removed
    it, so a reviewer can audit the set rather than trust it."""
    entries = [_entry(pdb_id="A", released="2019-01-01"),
               _entry(pdb_id="B", n_chains=4),
               _entry(pdb_id="C", length=10),
               _entry(pdb_id="D", method="SOLUTION NMR")]
    _, rejected = benchmark.select(entries, CUTOFF)
    assert len(rejected) == 4
    assert all(r["reason"] and isinstance(r["reason"], str) for r in rejected)
    assert {r["pdb_id"] for r in rejected} == {"A", "B", "C", "D"}


def test_an_entry_released_exactly_on_cutoff_is_rejected():
    """The <= comparison is what makes the held-out claim honest. An entry
    released exactly on the cutoff date may be in ESMFold's training set and
    must be excluded. This boundary case pins the choice of <= over <, which
    is the only filter whose removal would silently invalidate a promotion."""
    kept, rejected = benchmark.select([_entry(released=CUTOFF)], CUTOFF)
    assert kept == []
    assert "cutoff" in rejected[0]["reason"]


def test_a_pre_cutoff_multi_chain_entry_is_rejected_for_cutoff_not_chains():
    """When an entry fails multiple filters, rejection is attributed to the
    honesty-critical filter (cutoff) rather than cosmetic ones (chain count).
    The elif chain ensures that pre-cutoff multi-chain entries report the
    cutoff reason, protecting the whole framework's held-out claim."""
    kept, rejected = benchmark.select([_entry(released="2019-01-01", n_chains=3)], CUTOFF)
    assert kept == []
    assert "cutoff" in rejected[0]["reason"]
    assert "chain" not in rejected[0]["reason"]
