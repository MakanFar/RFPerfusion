---
name: biophys-triage
description: Linear biophysical triage of protein sequences — FASTA plus a config of user-defined parameters in, one TSV out with every tier's pass/fail verdict and features. Tiers run T0 (sequence descriptors: IVYWREL, CvP bias, aliphatic index, net charge) then T1 (static-structure audit: pLDDT-gated salt bridges, SASA, secondary structure, cavities) then T2 (brief implicit-solvent dynamics). Use when triaging many candidate sequences down to a handful worth expensive compute, screening agent-proposed sequences for thermostability, filtering proteins before MD or QM/MM, or ranking in-silico mutants by cheap biophysical criteria.
---

# Biophysical triage pipeline

Sequences in, filtered TSV out. Built to sit downstream of a sequence-proposing
agent and upstream of MD/QM/MM, so the expensive tiers only ever see survivors.

## Read first

- `TIERS.md` — what each tier does, what it catches, what it cannot catch, and
  how to read the output columns. Give this to a human collaborator.
- `INSTALL.md` — bring-up on a clean machine, with verified versions and the
  traps that produce silently-wrong results.

## Quick start

```bash
PYTHONPATH=. PYTHONSAFEPATH= python -m biophys_triage.run \
  --fasta proposals.faa --config config.yaml \
  --structures esmfold_out/ --out triage_results.tsv --report run_report.md
```

`PYTHONSAFEPATH=` (empty) is required in this runtime or `-m` fails with
ModuleNotFoundError.

## Contract

- **One row per input sequence, always.** Rejects are retained with their
  reason. A filter you cannot audit is a filter you cannot trust.
- **Tiers are gated**: a protein enters T1 only if it passed T0, so cost scales
  with survivors, not input size.
- **No magic numbers**: every threshold comes from the config file.
- **The runner never folds anything.** Structures come from `esmfold2`/`boltz`
  upstream and are matched by `<seq_id>.pdb` in `--structures`.

## Two things that silently produce wrong answers

1. **`t0_reference_mode` = `batch_relative`** means no reference distribution
   was supplied and the batch scored itself. Ranking is meaningful; absolute
   values are not. Supply `t0_reference` for `external` mode.
2. **The pLDDT gate must be live.** Check `plddt_source` reads `b_factor`, not
   `absent`. Biotite drops B-factors unless the reader is called with
   `extra_fields=["b_factor"]`; without it `mean_plddt` reads a constant 100.0
   and the gate never fires while appearing to work. Compare `n_salt_bridges`
   against `n_salt_bridges_ungated` — a large gap means the structure is too
   uncertain for T1 to have an opinion.

## Validation

Score every tier on taxa-matched extremophile-mesophile pairs and report
pair-AUC, so each descriptor's marginal contribution over a pLM adapter is
measurable rather than assumed. Never let a proposing agent optimize against the
same model that scores it — hold one descriptor set out as an independent audit.
