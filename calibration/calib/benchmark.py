"""Selecting a held-out benchmark set.

Framework section 6 asks for measured reliability on a HELD-OUT benchmark.
ESMFold's structure module was trained on the PDB, so an arbitrary selection
of entries would produce a number that looks measured and is not. The cutoff
filter is what makes the claim honest, and it is the only filter here whose
removal would silently invalidate a promotion.
"""

MIN_LENGTH = 50
MAX_LENGTH = 400
METHOD = "X-RAY DIFFRACTION"


def select(entries, cutoff_date):
    """Split candidate PDB entries into a kept id list and named rejections.

    `cutoff_date` is an ISO date string; entries released on or before it are
    excluded. Dates compare lexically, which is correct for ISO-8601.
    """
    kept, rejected = [], []
    for e in entries:
        if e["released"] <= cutoff_date:
            rejected.append({"pdb_id": e["pdb_id"],
                             "reason": f"released {e['released']}, on or before the "
                                       f"training cutoff {cutoff_date}"})
        elif e["n_chains"] != 1:
            rejected.append({"pdb_id": e["pdb_id"],
                             "reason": f"{e['n_chains']} chains; the benchmark is "
                                       f"single-chain so TM-score is unambiguous"})
        elif not MIN_LENGTH <= e["length"] <= MAX_LENGTH:
            rejected.append({"pdb_id": e["pdb_id"],
                             "reason": f"{e['length']} residues outside the "
                                       f"{MIN_LENGTH}-{MAX_LENGTH} band"})
        elif e["method"] != METHOD:
            rejected.append({"pdb_id": e["pdb_id"],
                             "reason": f"method {e['method']!r}, not {METHOD}"})
        else:
            kept.append(e["pdb_id"])
    return kept, rejected
