# Biophysical triage pipeline

Linear biophysical triage of protein sequences: **FASTA + config in, one TSV
out** with every tier's pass/fail verdict and the features behind it.

Built to sit downstream of a sequence-proposing agent and upstream of MD/QM/MM,
so the expensive methods only ever see survivors.

```
20,000 proposals --T0--> ~4,000 --T1--> ~400 --T2--> ~40 --T3--> 5
   sequence only    static structure   brief dynamics   full MD/QM-MM
     ~10 ms/prot      2-45 s/prot        ~10 min/prot     hours-days
```

## Contents

| Path | What it is |
|---|---|
| `TIERS.md` | **Start here.** What each tier does, what it catches, what it cannot, how to read the output columns. Written for humans. |
| `INSTALL.md` | Clean-machine bring-up with verified versions and the traps that produce silently-wrong results. |
| `biophys_triage/` | The package: `tiers.py` (feature computation + filters), `run.py` (linear runner). |
| `example/` | Worked example: 15 real UniProt sequences, config, and the resulting TSV + report. |
| `skill/SKILL.md` | Claude Science skill wrapper, so an agent can load the pipeline directly. |

## Quick start

```bash
pip install -e .
python -m biophys_triage.run \
  --fasta proposals.faa --config example/config.yaml \
  --structures esmfold_out/ --out triage_results.tsv --report run_report.md
```

Reproduce the worked example:

```bash
python -m biophys_triage.run --fasta example/demo.faa --config example/config.yaml \
  --structures example/structures --out /tmp/out.tsv
# -> T0 sequence filters: 9/15 pass
# -> T1 structure filters: 3/3 pass
```

The three T1 survivors (Q56319, P43408, Q9WYT0) are thermophile-derived, which
is the cheapest check that the composite score is not inverted.

`example/structures/` is not committed -- fetch the AlphaFold models with:

```bash
mkdir -p example/structures
for A in Q56319 P43408 Q9WYT0 P00698; do
  curl -s -o "example/structures/$A.pdb" \
    "https://alphafold.ebi.ac.uk/files/AF-$A-F1-model_v6.pdb"
done
```

## Design contract

- **One row per input sequence, always.** Rejects are retained with their
  reason -- a filter you cannot audit is a filter you cannot trust. If T0 is
  discarding 95% of an agent's proposals, that is a fact about the agent worth
  seeing.
- **Tiers are gated.** A protein enters tier N+1 only if it passed tier N, so
  total cost scales with survivors rather than input size.
- **No magic numbers.** Every threshold lives in the config file.
- **The runner never folds anything.** Structures come from ESMFold2/Boltz
  upstream, matched by `<seq_id>.pdb` in `--structures`.

## Two things that silently produce wrong answers

1. **`t0_reference_mode = batch_relative`** means no reference distribution was
   supplied and the batch scored itself. The ranking is still meaningful; the
   absolute value is not, and a batch of uniformly poor sequences will still
   produce high scorers.
2. **The pLDDT gate must be live.** Check `plddt_source` reads `b_factor`, not
   `absent`. Biotite drops B-factors unless the reader is called with
   `extra_fields=["b_factor"]` -- without it `mean_plddt` reads a constant 100.0
   for every protein and the gate never fires *while appearing to work*.

   On real AlphaFold structure Q56319, varying only the cutoff:

   | pLDDT cutoff | Confident residues | Ion pairs counted | Discarded as artifact |
   |---|---:|---:|---:|
   | 70 | 99.6% | 21 | 0 |
   | 97 | 52.8% | 6 | 15 |

   A large `n_salt_bridges_lowconf_discarded` means the structure is too
   uncertain for T1 to have an opinion -- re-fold it rather than filter on it.

## Status

T0 and T1 are implemented and tested end-to-end against real UniProt sequences
and AlphaFold structures. T2 (brief implicit-solvent dynamics) is specified in
`TIERS.md` but not yet implemented. Explicit-solvent MD and QM/MM remain a
reference tier for confirming the final handful, not part of the filtering path.

Licensing note: PyRosetta and FoldX are deliberately not used -- both are
license-gated. ThermoMPNN (MIT) covers the ddG use case.
