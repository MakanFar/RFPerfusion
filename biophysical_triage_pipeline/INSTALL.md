# Installation — bringing this up on a new machine

*Written for another Claude instance, or a human, starting from a clean
machine. Assumes proto is already installed; this covers only the biophysics
stack that the triage tiers add on top.*

Every version below was resolved and installed on macOS/arm64 on 2026-08-16 and
the pipeline was run end-to-end against real UniProt sequences and AlphaFold
structures. Where a tool is license-gated or GPU-only it is called out
explicitly rather than left to fail at runtime.

---

## 1. Core environment (T0 + T1, CPU-only)

This is the whole triage funnel minus the GPU tiers. No license negotiation, no
compilation, no GPU.

```bash
conda create -n biophys-triage python=3.11 -y
conda activate biophys-triage
pip install pandas numpy scipy pyyaml matplotlib biopython
pip install peptides propka freesasa biotite pyKVFinder localcider
```

From inside Claude Science, equivalently:

```python
manage_environments(mode="create", name="biophys-triage", python_version="3.11",
                    packages=["pandas","numpy","scipy","pyyaml","matplotlib","biopython"])
manage_packages(mode="install", environment="biophys-triage", use_pip=True,
                packages=["peptides","propka","freesasa","biotite","pyKVFinder","localcider"])
```

**Verified versions:** peptides 0.5.0 · biotite 1.6.0 · pyKVFinder 0.9.3 ·
biopython 1.88 · propka 3.5.1 · freesasa 2.2.1 · localcider 0.1.21

### Verify the install

```bash
python -c "
import peptides, biotite, pyKVFinder, freesasa, propka
p = peptides.Peptide('MKVLATTLAVGLGLSACSSSHKEEAPKAEEKAWTAAQ')
print('peptides OK:', round(p.aliphatic_index(), 2))   # -> 79.46
print('biotite', biotite.__version__, '| pyKVFinder', pyKVFinder.__version__)
"
```

Expected: `peptides OK: 79.46`. If the aliphatic index differs, the descriptor
scale changed between versions and the T0 reference distribution must be
refit — do not silently compare scores across versions.

> `freesasa` has no `__version__` attribute — probe it with
> `hasattr(freesasa, 'calc')` instead. A version check on it fails with
> `AttributeError` and is not an install problem.

---

## 2. Install the package

```bash
git clone <repo-url> && cd biophys_triage
pip install -e .
```

Without `pip install -e .`, run it with the package on the path:

```bash
PYTHONPATH=. PYTHONSAFEPATH= python -m biophys_triage.run --help
```

`PYTHONSAFEPATH=` (set to empty) is required inside Claude Science — the runtime
exports `PYTHONSAFEPATH=1`, which keeps the current directory off `sys.path`
and makes `-m biophys_triage.run` fail with `ModuleNotFoundError`. On an
ordinary machine it is harmless.

---

## 3. Smoke test on real data

Fetch a handful of real sequences and structures, then run the full funnel:

```bash
# sequences
for A in Q56319 P43408 Q9WYT0 P00698 P00761; do
  curl -s "https://rest.uniprot.org/uniprotkb/$A.fasta" >> example/demo.faa
done

# structures (note: model_v6 — v4 URLs now 404)
mkdir -p example/structures
for A in Q56319 P43408 Q9WYT0 P00698; do
  curl -s -o "example/structures/$A.pdb" \
    "https://alphafold.ebi.ac.uk/files/AF-$A-F1-model_v6.pdb"
done

PYTHONPATH=. PYTHONSAFEPATH= python -m biophys_triage.run \
  --fasta example/demo.faa --config example/config.yaml \
  --structures example/structures \
  --out example/demo_results.tsv --report example/demo_report.md
```

Expected on the 15-sequence demo set: `T0 sequence filters: 9/15 pass`, then
`T1 structure filters: 3/3 pass`. The three T1 survivors (Q56319, P43408,
Q9WYT0) are thermophile-derived, which is the correct direction and the
cheapest sanity check that the composite score is not inverted.

**If AlphaFold URLs 404:** the model version suffix advances. Resolve it from
the API rather than guessing:
`curl -s https://alphafold.ebi.ac.uk/api/prediction/P00698 | grep -o '"pdbUrl":"[^"]*"'`

---

## 4. Confirm the confidence gate is live

The pLDDT gate is the feature that separates a useful audit from noise, so
verify it rather than assuming it. Re-run with `plddt_min: 97.0`:

```bash
sed 's/plddt_min: 70.0/plddt_min: 97.0/' example/config.yaml > /tmp/strict.yaml
PYTHONPATH=. PYTHONSAFEPATH= python -m biophys_triage.run --fasta example/demo.faa \
  --config /tmp/strict.yaml --structures example/structures --out /tmp/strict.tsv
```

On Q56319 the ion-pair count must drop **21 → 6** with 15 discarded. If it does
not change, the gate is not reading pLDDT — check that `plddt_source` reads
`b_factor` and not `absent`.

> **Known trap:** biotite drops the B-factor column unless you ask for it. The
> structure reader must be called as
> `PDBFile.read(path).get_structure(model=1, extra_fields=["b_factor"])`.
> Without `extra_fields`, `mean_plddt` silently reads a constant 100.0 for every
> protein and the gate never fires — it looks like it is working.

---

## 5. Optional tiers

### T0-b — learned thermostability classifier (GPU recommended)

```bash
git clone https://github.com/ievapudz/TemStaPro.git   # MIT
```

Needs ProtTrans weights (~2.5 GB, downloaded on first run) and a GPU for
throughput. CPU works but is ~50× slower. Emits a per-threshold temperature
profile (40/45/50/55/60/65 °C), not a single scalar.

### T1-d — ΔΔG site-saturation scanning (GPU)

```bash
git clone https://github.com/Kuhlman-Lab/ThermoMPNN.git   # MIT
```

Full L×19 scan of a 300-aa protein in ~15 s on GPU.

### T1-b — full Poisson-Boltzmann electrostatics

`pip install pdb2pqr` gets you PQR generation; APBS itself is a separate binary
(`conda install -c conda-forge apbs`). PROPKA alone (already installed) covers
pKa shifts at ~5 s/protein — add APBS only when the full electrostatic free
energy term is needed, since it adds ~40 s/protein.

### T2 — brief dynamics

```bash
pip install openmm pdbfixer mdtraj
python -m openmm.testInstallation    # confirms the GPU platform is visible
```

### Deliberately NOT used

**PyRosetta** and **FoldX** are license-gated and not freely installable — both
return HTTP errors from PyPI. ThermoMPNN (MIT) covers the ΔΔG use case with no
license negotiation and is faster. If your group already holds a Rosetta
license, `ELELAB/RosettaDDGPrediction` (GPL-3.0) is the drop-in alternative.

---

## 6. Offline / cluster notes

On a compute node without internet egress, pre-stage model weights and set:

```bash
export HF_HOME=/shared/path/hf_cache
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
```

Setting `HF_HOME` **without** the two offline flags is a known failure mode: the
loader still pings the Hub for metadata at model load, and a transient network
failure mid-run makes it unable to read an already-present local cache. Set all
three together.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: biophys_triage` | `PYTHONSAFEPATH=1` in the runtime | prefix with `PYTHONPATH=. PYTHONSAFEPATH=` |
| `mean_plddt` = 100.0 for every protein | biotite dropped B-factors | pass `extra_fields=["b_factor"]` |
| `AttributeError: freesasa.__version__` | attribute does not exist | probe `hasattr(freesasa,'calc')` |
| AlphaFold 404 | model version advanced past v4 | resolve `pdbUrl` from the prediction API |
| All rows `passed_T0_pending_T1` | no structures supplied | populate `--structures` and re-run |
| `t0_reference_mode` = `batch_relative` | no reference distribution given | supply `t0_reference` in config |
