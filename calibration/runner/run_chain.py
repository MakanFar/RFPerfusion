"""Executed with `uv run --project ../proto python runner/run_chain.py`.

Reads one job as JSON on stdin, writes one result as JSON on stdout. It is
the only code here that cannot be exercised offline, so it makes NO
decisions: it emits both of usalign's normalisations, the protein-chain
count, and both lengths, and `calib.driver` -- which is tested -- decides
what any of it means. A decision taken here would be uncatchable: silently
reporting `tm_score_structure_1` instead of `tm_score_structure_2`
normalises by the prediction rather than the reference, which lets a
truncated model score well on the fragment it did predict, and every number
downstream still looks plausible.

Ground truth is downloaded from RCSB rather than fetched with a proto tool.
`pdb-fetch-entry` returns metadata only and `alphafold-db-fetch` returns
AlphaFold predictions; aligning against a prediction would measure agreement
between two predictors, not reliability against experiment.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

# `calib` is pure stdlib and is imported for parsing only -- it pulls in no
# proto_tools, so this stays a one-way dependency.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calib import cif  # noqa: E402 -- after the path insert, by necessity

RCSB_CIF = "https://files.rcsb.org/download/{}.cif"

# proto-tools' `device` selects WHERE a tool runs, not just which local
# accelerator: RemoteDevice is Literal["proto", "modal"], alongside "cuda"
# and "cpu". The config docstring lists only the local pair, so calling
# run_esmfold() with defaults runs the model IN THIS PROCESS -- which on a
# machine without a GPU fails with "requested 'cuda' but no GPUs visible",
# never reaching the deployed Modal app. Dispatching is opt-in and this is
# the opt-in. Overridable so a CPU-local run stays possible without an edit.
DEVICE = os.environ.get("PROTO_DEVICE", "modal")


def main():
    job = json.load(sys.stdin)
    pdb_id = job["pdb_id"]
    stage = "import"
    try:
        from proto_tools.tools.database_retrieval.pdb.fetch_fasta import (
            PdbFetchFastaInput, run_pdb_fetch_fasta,
        )
        from proto_tools.tools.structure_alignment.usalign.usalign import (
            USalignConfig, USalignInput, run_usalign,
        )
        from proto_tools.tools.structure_prediction.esmfold.esmfold import (
            ESMFoldConfig, ESMFoldInput, run_esmfold,
        )

        stage = "pdb-fetch-fasta"
        fasta = run_pdb_fetch_fasta(PdbFetchFastaInput(pdb_id=pdb_id))
        chains = [c for c in fasta.chains if c.is_protein]
        if not chains:
            # Not a judgement about the benchmark -- with no chain there is
            # nothing to fold and so no data to report either way.
            raise ValueError("no protein chain in the PDB fasta")
        sequence = chains[0].sequence

        stage = "rcsb-download"
        with urllib.request.urlopen(RCSB_CIF.format(pdb_id), timeout=60) as resp:
            reference_cif = resp.read().decode()

        stage = "esmfold"
        predicted = run_esmfold(ESMFoldInput(complexes=[sequence]),
                                ESMFoldConfig(device=DEVICE)).structures[0]

        stage = "usalign"
        aln = run_usalign(
            USalignInput(query_structure=predicted,
                         reference_structure=reference_cif),
            USalignConfig(device=DEVICE),
        )

        json.dump({"ok": True,
                   "n_protein_chains": len(chains),
                   "query_length": len(sequence),
                   "reference_length": cif.count_residues(reference_cif),
                   "avg_plddt": predicted.metrics.avg_plddt,
                   "tm_score_structure_1": aln.metrics.tm_score_structure_1,
                   "tm_score_structure_2": aln.metrics.tm_score_structure_2},
                  sys.stdout)
    except Exception as exc:  # noqa: BLE001 -- reported, not swallowed
        json.dump({"ok": False, "stage": stage,
                   "error": f"{type(exc).__name__}: {exc}"}, sys.stdout)


if __name__ == "__main__":
    main()
