"""Selecting a held-out benchmark set.

Framework section 6 asks for measured reliability on a HELD-OUT benchmark.
ESMFold's structure module was trained on the PDB, so an arbitrary selection
of entries would produce a number that looks measured and is not. The cutoff
filter is what makes the claim honest, and it is the only filter here whose
removal would silently invalidate a promotion.
"""

# ESMFold's PDB training cutoff, established from the primary source rather
# than inferred. Lin et al., "Evolutionary-scale prediction of atomic level
# protein structure with a language model" (bioRxiv 2022.07.20.500902),
# section "Structure training sets for ESMFold":
#
#   "We find all PDB chains until 2020-05-01 with resolution less than or
#    equal to 9A and length greater than 20."
#
# Corroborated within the same paper: its held-out Recent-PDB-Multimers set
# is "deposited in the Protein Data Bank between 2020-05-01 and 2022-06-01",
# and the released model's own evaluation set is CAMEO Apr-Jun 2022.
#
# A third-party comparison paper states "ESMFold (June 2020)". That is a
# secondary claim and disagrees with the authors' own methods section, so
# this constant follows the primary source. The whole held-out claim rests
# on this date: everything released on or before it may be in training.
ESMFOLD_PDB_CUTOFF = "2020-05-01"

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
