"""Executed with `uv run --project ../proto python runner/run_chain.py`.

Reads one job as JSON on stdin, writes one result as JSON on stdout. Kept
deliberately small: it is the only code here that cannot be tested offline,
so it holds no logic worth testing -- selection, maths and record-building
all live in `calib/`.

Ground truth is downloaded from RCSB rather than fetched with a proto tool.
`pdb-fetch-entry` returns metadata only and `alphafold-db-fetch` returns
AlphaFold predictions; aligning against a prediction would measure agreement
between two predictors, not reliability against experiment.
"""

import json
import sys
import urllib.request

RCSB_CIF = "https://files.rcsb.org/download/{}.cif"


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
        if len(chains) != 1:
            raise ValueError(f"expected one protein chain, got {len(chains)}")
        sequence = chains[0].sequence

        stage = "rcsb-download"
        with urllib.request.urlopen(RCSB_CIF.format(pdb_id), timeout=60) as resp:
            reference_cif = resp.read().decode()

        stage = "esmfold"
        predicted = run_esmfold(ESMFoldInput(complexes=[sequence]),
                                ESMFoldConfig()).structures[0]

        stage = "usalign"
        aln = run_usalign(
            USalignInput(query_structure=predicted,
                         reference_structure=reference_cif),
            USalignConfig(),
        )

        # structure_2 is the REFERENCE, so this is the reference-normalised
        # TM-score. Normalising by the prediction would let a truncated model
        # score well on the fragment it did predict.
        json.dump({"ok": True, "length": len(sequence),
                   "avg_plddt": predicted.metrics.avg_plddt,
                   "tm_score": aln.metrics.tm_score_structure_2}, sys.stdout)
    except Exception as exc:  # noqa: BLE001 -- reported, not swallowed
        json.dump({"ok": False, "stage": stage,
                   "error": f"{type(exc).__name__}: {exc}"}, sys.stdout)


if __name__ == "__main__":
    main()
