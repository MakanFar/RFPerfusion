# The triage tiers — what each one does and why

*A human-readable guide to how 20,000 proposed sequences become ~5 that are
worth expensive compute or bench time.*

---

## The core idea

You cannot afford to evaluate 20,000 proteins carefully. You can afford to
evaluate 20,000 proteins *cheaply*, 400 proteins *moderately*, and 5 proteins
*thoroughly*. The tiers exist to spend the expensive methods only where they
change a decision.

The ordering principle is not "cheap first" for its own sake — it is **what
input does the method need?** That is what actually sets cost:

| Tier | Needs | Cost/protein | Typical survivors |
|---|---|---|---|
| **T0** | sequence only | ~10 ms | 20,000 → 4,000 |
| **T1** | one static structure | 2–45 s | 4,000 → 400 |
| **T2** | brief dynamics | ~10 min | 400 → 40 |
| **T3** | full MD / QM/MM | hours–days | 40 → 5 |

A protein only enters tier N+1 if it passed tier N. Total cost is therefore set
by the *survivors*, not by the input size — which is the entire reason the
funnel is affordable.

---

## T0 — Sequence filters

**Question it answers:** *Does this sequence even look like a thermostable
protein, before we spend anything on structure?*

**Input:** FASTA. **Output:** 14 descriptors + a composite z-score.

Thermal adaptation leaves a compositional fingerprint that is measurable
without any 3D information. T0 computes:

- **IVYWREL fraction** — the residue set whose frequency correlates with
  optimal growth temperature across genomes.
- **CvP bias** — charged (D,E,K,R) minus polar-uncharged (N,Q,S,T) residues per
  100. One of the most reliable single discriminators of thermophilic proteins;
  thermophiles trade heat-labile polar residues for salt-bridge-capable charged
  ones.
- **Thermolabile fraction** — Q, N, C, M, D, S, T: residues prone to
  deamidation, oxidation, or backbone cleavage at high temperature. A protein
  loaded with these has a chemical stability ceiling regardless of its fold.
- **Aliphatic index** — relative volume occupied by A, V, I, L side chains; a
  proxy for hydrophobic core packing quality.
- **Net charge at target pH, pI, GRAVY, instability index, Boman index.**

These fold into a **composite z-score** measured against a mesophilic
background.

> **Read the `t0_reference_mode` column before trusting the score.**
> `external` means it was z-scored against a real reference distribution.
> `batch_relative` means no reference was supplied and the batch scored itself —
> the ranking is still meaningful, but the absolute value is not, and a batch of
> uniformly poor sequences will still produce high scorers. Supply
> `t0_reference` from your extremophile–mesophile pair set to get `external`.

**What T0 catches:** compositionally implausible proposals, degenerate or
low-complexity output, wrong-length sequences, aggregation-prone designs.

**What T0 cannot catch:** anything involving 3D arrangement. A sequence with
perfect thermophilic composition that folds into a molten globule passes T0
cleanly. T0 is a *necessary-not-sufficient* screen, and treating its score as a
stability prediction is the most likely way to misuse this pipeline.

---

## T1 — Static-structure filters

**Question it answers:** *Given the fold, are the stabilizing interactions
actually there?*

**Input:** one predicted structure per survivor (from ESMFold2/Boltz upstream —
the runner never folds anything itself). **Output:** geometric features + a
per-residue table.

- **Salt bridges and ion-pair networks.** Counted at a 4 Å carboxyl–amine
  criterion. What matters is less the raw count than the **network size
  distribution** — thermophilic proteins are distinguished by large cooperative
  networks more than by total pair count.
- **Solvent-accessible surface area**, per-residue and total; hydrophobic-core
  compactness.
- **Secondary-structure content** — helix/sheet/coil fractions; long exposed
  loops are typically the first region to melt.
- **Cavity volume and lining residues** (T1-c) — under-packed voids are the
  highest-yield target for stabilizing cavity-fill mutations.
- **pKa and pH-dependent stability** (T1-b) — answers what geometry alone
  cannot: *is that ion pair actually charged at the operating pH?*

### The confidence gate — the most important detail in T1

Every geometric feature is gated on per-residue pLDDT (default cutoff 70).
**A salt bridge inside a low-confidence loop is not counted.**

This is not conservatism, it is correctness: in a pLDDT<70 region the
coordinate error is larger than the 4 Å distance criterion being applied, so
such a "salt bridge" is an artifact of the structure prediction rather than a
property of the protein. Ungated, a triage run will happily rank designs by
features that exist only in the predictor's uncertainty.

The effect is large and worth internalizing. On the same real AlphaFold
structure (Q56319), varying only the cutoff:

| pLDDT cutoff | Confident residues | Ion pairs counted | Discarded as artifact |
|---|---:|---:|---:|
| 70 | 99.6% | 21 | 0 |
| 97 | 52.8% | 6 | 15 |

Three columns are always written so this is auditable rather than implicit:
`n_salt_bridges` (gated, used for filtering), `n_salt_bridges_ungated`, and
`n_salt_bridges_lowconf_discarded`. A large discard count means **the structure
is too uncertain for T1 to have an opinion** — that protein should be re-folded
or dropped, not filtered on.

---

## T2 — Brief dynamics

**Question it answers:** *Does it survive being given kinetic energy?*

Minimize in implicit solvent, then run 250 ps–1 ns **at the target
temperature**. Report Cα-RMSD drift, per-residue RMSF, radius-of-gyration
stability, secondary-structure retention, and — the informative one — **whether
the ion-pair network T1 found is still intact at the end.**

This catches designs that are static-structure-plausible and fall apart the
moment they move. At ~10 min/protein it sits exactly at the affordability
ceiling, which is why it runs on tens of survivors rather than thousands. It is
the cheapest honest probe of the actual question — *at what temperature does
this destabilize* — and the natural handoff into T3.

---

## T3 — Reference tier (MD / QM/MM)

Explicit-solvent MD and QM/MM active-site energetics stay in the plan, but as
**confirmation on the final handful** and as ground truth for calibrating the
cheap scores. They are 2–3 orders of magnitude above the triage budget; a
pipeline that puts them in the filtering path processes single-digit numbers of
proteins per week and cannot close a design loop.

---

## How to read the output TSV

**One row per input sequence, always.** Rejected proteins are retained with the
reason they were rejected — a filter you cannot audit is a filter you cannot
trust. If T0 is discarding 95% of your agent's proposals, that is a fact about
the agent worth knowing, and it is only visible if the rejects are in the file.

Key columns:

| Column | Meaning |
|---|---|
| `final_tier_reached` | `rejected_T0` / `rejected_T1` / `passed_T1` / `passed_T0_pending_T1` |
| `t0_pass`, `t1_pass` | per-tier boolean verdict |
| `t0_reject_reason`, `t1_reject_reason` | which threshold failed, or `not evaluated (failed T0)` |
| `t0_composite_z` | composite score — check `t0_reference_mode` first |
| `n_salt_bridges` vs `..._ungated` | gated vs raw; large gap = untrustworthy structure |
| `plddt_source` | `b_factor` (real pLDDT) or `absent` (gate inactive) |

`passed_T0_pending_T1` means the protein cleared T0 but no structure was
supplied — it is a **to-do, not a rejection**. Fold those and re-run.

---

## Two failure modes to watch

**Score-hacking.** An agent optimizing against a cheap score will find
compositional extremes that satisfy T0 and fail T1 — poly-charged sequences
with excellent CvP bias and no hydrophobic core. Countermeasure: never let the
proposing agent optimize against the same model that scores it. Hold one
descriptor set out as an independent audit.

**Confidence leakage.** Features computed from low-pLDDT regions driving
decisions. Countermeasure: the pLDDT gate above, plus monitoring
`n_salt_bridges_lowconf_discarded` across a batch. If it is large and growing,
your structures — not your filters — are the bottleneck.

---

## Tuning the funnel

Thresholds live entirely in the config file; there are no magic numbers in the
code. Two ways to set a tier's stringency:

- **Hard thresholds** (`t0_filters: {instability_index: {max: 60}}`) — use when
  the cut has physical meaning.
- **Rank-based** (`t0_keep_top_fraction: 0.2`) — use when you want a predictable
  survivor count regardless of batch quality. Recommended for the 20k→4k step,
  since it makes downstream cost deterministic.

Start permissive, read the feature distributions in the first run's report, then
tighten. Setting aggressive thresholds before seeing your own data's
distributions is how a funnel silently discards everything interesting at T0.
