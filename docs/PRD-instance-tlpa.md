# PRD — RFPerfusion

**A literature-grounded agentic pipeline that designs a SWIR-actuated protein thermal switch.**

| | |
|---|---|
| **Event** | re:AGENT Hackathon — **Track C: Build the Biological Design** |
| **Date** | 2026-08-15 |
| **Duration** | ~48 h (full weekend) |
| **Team** | 4–6 people, 3 workstreams |
| **Status** | Draft for team review |
| **Supersedes** | The originating team discussion's §13 framing (see §1.2); that document is no longer in the repo |

---

## 1. Framing

### 1.1 The deliverable is a sequence, not a framework

Track C states: *"What you demo is the new biological design you made — the sequence or system that didn't exist before you built it."*

The team discussion doc (§13) recommends the inverse — framework as the contribution, protein as a test case. **This PRD reverses that.** The judged artifact is a set of novel protein sequences with predicted, quantified properties. The agentic pipeline is *how we got there*, and it earns credit through the **Literature Integration** and **Constraint Design** criteria — not on its own merits.

Practical consequence: if at hour 36 we must choose between a more general orchestrator and a better candidate set, **we choose the candidate set.**

### 1.2 What changed from the discussion doc, and why

| Discussion doc | This PRD | Reason |
|---|---|---|
| Framework is the product; protein is the test case (§13) | Sequence is the product; pipeline is the method | Track C judges the artifact |
| Design a protein with direct sensitivity at >1500 nm (§1) | Design a protein that is *actuated by* >1500 nm light, via photothermal transduction | Direct absorption is physically ruled out — see §2.1 |
| 4 teams (A/B/C/D) (§8) | 3 workstreams | 48 h; Proto absorbs most of Teams C and D |
| Simulation as secondary validation (§5) | No MD. Structure prediction + scoring functions only | MD does not fit in 48 h, and Proto's constraint stack is the better spend |
| Construct design as stretch goal (§11) | Retained as stretch, via Benchling | Unchanged |

---

## 2. Problem & Mechanism

### 2.1 Why the literal target is impossible — and why that is the story

The originating question was *"how can we design a protein that responds to wavelengths greater than 1500 nm?"*

A photon at 1500 nm carries **0.83 eV**. Every known biological chromophore's lowest electronic transition sits far above this:

| Chromophore | λmax | Photon energy |
|---|---|---|
| Retinal (rhodopsins) | ~500 nm | ~2.5 eV |
| Flavin (LOV, BLUF) | ~450 nm | ~2.8 eV |
| Biliverdin (bacteriophytochromes) | ~750–800 nm | ~1.6 eV |
| Bacteriochlorophyll *b* (red edge of known biology) | ~1020 nm | ~1.2 eV |

There is no π→π* transition in known protein cofactor chemistry at 0.83 eV. A pipeline that outputs "here is a protein that absorbs 1550 nm light" would be a hallucination, and would fail the **Biological Plausibility** criterion outright.

What *does* absorb strongly beyond 1500 nm is **water** — vibrational overtone and combination bands, not electronic transitions. This is not a workaround; it is the established mechanism of **infrared neural stimulation (INS)**, where pulsed 1850–2000 nm light drives neural activity. The photothermal origin is confirmed by the D₂O substitution control (lower absorption coefficient → markedly reduced response), and heat-sensitive **TRPV4** channels are implicated as the downstream transducer at 1875 nm.

**This redirect is the project's Literature Integration exhibit.** The pipeline must *discover* the infeasibility from the literature and re-scope the design space itself — not have it hardcoded by us. See §5.2 (G2) and §8.1.

### 2.2 The mechanism we design against

```
SWIR laser (1550 nm)  →  water vibrational absorption  →  localized ΔT (+4-5 °C, ms)
                                                                    ↓
                                              engineered coiled-coil thermal switch
                                                                    ↓
                                                      de-repression → gene expression
```

The protein does not see the photon. It sees the heat the photon makes. The **system** is >1500 nm-responsive, and nothing else in the cell is — that is the functional win, and the PRD states it in exactly these terms rather than overclaiming.

**Wavelength choice: 1550 nm primary.** Satisfies the >1500 nm spec, absorption coefficient ~10 cm⁻¹ gives ~1 mm penetration (good localization without surface-only deposition), and telecom fiber lasers make it the cheapest possible wet-lab follow-up. **1930 nm** is the documented alternative (~100 cm⁻¹, ~100 µm penetration) if tighter confinement is wanted; the pipeline should carry both and let the thermal model choose.

### 2.3 The scaffold: TlpA

**TlpA**, the transcriptional autorepressor from the *Salmonella typhimurium* virulence plasmid, is the design substrate:

- **371 aa** total, with a remarkably long **~250-residue α-helical coiled-coil** running to the C-terminus, which uncoils sharply between 37 °C and 45 °C
- **N-terminal DNA-binding domain** (≈ residues 1–120); represses its own promoter in the low-temperature dimeric state
- Sharp transition: **>30-fold induction over a 5 °C range centered at 43.5 °C**
- Shapiro group (Piraner et al., *Nat Chem Biol* 2017) produced **engineered variants spanning 32–46 °C**

Three properties make it the right choice: the transition is *steep* (small ΔT → large output), the mechanism is *coiled-coil stability* (which sequence-based models can actually reason about, unlike photophysics), and **engineered variants already exist as ground truth** for the positive-control benchmark (§7).

### 2.4 The design gap

Wild-type TlpA switches at 43.5 °C. From a 37 °C baseline that demands a **+6.5 °C** transient — high enough to risk thermal damage and hard to deliver safely.

> **Design target: a TlpA variant with a transition midpoint at 41.0 ± 0.5 °C, tightly OFF at 37 °C, with cooperativity equal to or steeper than wild-type.**

That is a **+4 °C** actuation window — within documented safe INS transients — while preserving the sharp switching that makes the scaffold useful. This is a concrete, novel, and gradeable generative task.

---

## 3. Goals & Non-Goals

### 3.1 Goals

**G1 — Generation.** Produce ≥20 novel TlpA variant sequences not present in any database or prior publication, each with a predicted transition midpoint, a cooperativity estimate, and a calibrated uncertainty. Ship a ranked top-5.

**G2 — Literature integration.** The pipeline autonomously reaches the photothermal redirect from literature, and extracts *quantitative* parameters (water absorption coefficients, safe transient magnitudes, known variant→Tm pairs) that become numeric constraints. Every constraint traces to a citation.

**G3 — Constraint design.** Encode the target biology as executable Proto `Constraint` functions at a resolution that reflects real failure modes: coiled-coil register, dimer interface packing, DNA-binding domain integrity, foldability, aggregation.

**G4 — Uncertainty.** Every score carries an explicit confidence. Out-of-distribution predictions are flagged, not silently reported. Ranking is uncertainty-aware.

**G5 — Positive control.** The pipeline recovers known Piraner variants from a held-out set before we trust its novel output.

### 3.2 Non-Goals

- **No wet-lab validation.** 48 h. All results are computational predictions, labeled as such.
- **No molecular dynamics.** Explicitly cut (see §1.2).
- **No de novo protein design.** We engineer an existing scaffold. Inventing a thermal switch from scratch is not 48-h work and has no ground truth.
- **No general-purpose scientific reasoning framework.** Generality is a *narrative* claim supported by clean interfaces, not an engineering deliverable.
- **No claim of direct >1500 nm protein absorption.** Ever, anywhere in the demo.

---

## 4. Sponsor Tool Map

Each stage is anchored to a sponsor tool. This is deliberate — "Use of sponsor tools" is a judging criterion.

| Stage | Sponsor tool | Use |
|---|---|---|
| 2 — Literature & Evidence | **Paperclip** | Full-text biomedical retrieval; mechanism discovery; quantitative parameter extraction with citations |
| 3 — Generation | **Proto** (`Generators`) | ESM2/ESM3 masked-LM variant proposal, ProteinMPNN inverse folding on the coiled-coil |
| 4 — Evaluation | **Proto** (`Constraints`) | ESMFold, PyRosetta ΔΔG, FoldSeek, DSSP, structure metrics |
| 4 — Embeddings/clustering | **Biohub / ESM** | ESM embeddings for scaffold-space clustering and novelty scoring |
| 5 — Optimization | **Proto** (`Optimizers`) | Multi-objective steering over the constraint set |
| 7 — Benchmark harness | **BenchFlow** | Reproducible positive-control eval; scoring the pipeline as an agent task |
| 8 — Construct (stretch) | **Benchling** | Export orderable construct: promoter, RBS, tags, sequence map |

**Proto is the backbone.** Its four primitives — Sequences, Generators, Constraints, Optimizers — *are* our Stages 3–5, and its `Constraint` abstraction is a direct expression of the Constraint Design criterion. Install: `pip install "git+https://github.com/evo-design/proto-tools.git[mcp]"`, then run `proto-tools agent-context` so the orchestrator discovers the `Input → Config → run_*() → Output` pattern. Heavy structure prediction offloads to Modal via `device="modal"`.

---

## 5. Architecture

### 5.1 Decision: orchestrator + specialized agents

Discussion doc §7 left this open. **We commit to multi-agent with a thin orchestrator**, for one concrete reason: the literature agents produce far more text than the design loop can hold, and the design loop runs many iterations. Forcing both into one context guarantees the orchestrator forgets its own constraints mid-optimization.

The orchestrator holds only the **Design Record** (§6.1) — a compact JSON document. It never holds raw paper text or raw candidate batches.

```
                        ┌──────────────────┐
   Scientist ──────────▶│   ORCHESTRATOR   │◀──── Design Record (JSON, single source of truth)
        ▲               └────────┬─────────┘
        │                        │
        │ curate/approve    ┌────┴────┬───────────┬────────────┐
        │                   ▼         ▼           ▼            ▼
   ┌────┴──────┐      ┌──────────┐ ┌────────┐ ┌────────┐ ┌──────────┐
   │Formulation│      │Literature│ │ Design │ │  Eval  │ │Construct │
   │  Agent    │      │ Agents   │ │ Agent  │ │ Agent  │ │  Agent   │
   └───────────┘      │ (xN, ||) │ │        │ │        │ │(stretch) │
                      └────┬─────┘ └───┬────┘ └───┬────┘ └────┬─────┘
                       Paperclip    Proto Gen  Proto Cons  Benchling
                           │            │          │
                           ▼            ▼          ▼
                    ┌──────────────────────────────────────┐
                    │  Evidence Store  +  Candidate Store  │
                    └──────────────────────────────────────┘
```

Agents communicate **only** through the typed artifacts in §6. No agent reads another agent's prose.

### 5.2 Agent specifications

Per discussion doc §9, each spec answers: input, action, tools, output, format, consumer.

---

**Formulation Agent**

- **In:** free-text design goal (`"a protein that responds to λ > 1500 nm"`)
- **Does:** decomposes into physical/biological sub-questions; proposes a constraint skeleton with unfilled numeric slots; surfaces contradictions to the human
- **Tools:** LLM + human-in-the-loop
- **Out:** `DesignRecord` v0 (goal, sub-questions, empty `constraints[]`)
- **Consumer:** Orchestrator → Literature Agents

---

**Literature Agents** (parallel, one per sub-question)

- **In:** one `ResearchQuestion`
- **Does:** grounded full-text search; extracts *mechanisms* and *numbers*; classifies each finding as `established | contested | speculative`
- **Tools:** **Paperclip**
- **Out:** `EvidenceItem[]`
- **Consumer:** Orchestrator (mechanism selection), Design Agent (scaffold selection), Eval Agent (numeric constraint values)

Four fixed sub-questions, spawned concurrently:

| # | Question | Expected finding |
|---|---|---|
| L1 | What is the longest-wavelength electronic transition in any known protein chromophore? | Ceiling ~1020 nm → **direct absorption infeasible** |
| L2 | What absorbs >1500 nm in biological tissue, and what happens downstream? | Water vibrational bands; INS; photothermal transduction |
| L3 | What protein switches respond to small temperature changes near physiological? | TlpA, TcI, TRPV; coiled-coil thermal switches |
| L4 | What mutations shift coiled-coil transition midpoints, and by how much? | Piraner variant→Tm table; heptad-position rules |

**L1 is the load-bearing one.** It produces the negative result that forces the redirect. Its output must be logged prominently — this is the demo's Literature Integration moment, and it must be reached by the agent, not asserted by us.

---

**Design Agent**

- **In:** `DesignRecord` (chosen scaffold + constraint set)
- **Does:** proposes variant sequences; masked-LM sampling at heptad `a`/`d` core positions and interface `e`/`g` positions; inverse folding on the coiled-coil; enforces the DNA-binding domain as immutable
- **Tools:** **Proto** `Generators` — ESM2/ESM3, ProteinMPNN
- **Out:** `Candidate[]` (sequence + mutation list + generation provenance)
- **Consumer:** Eval Agent

---

**Evaluation Agent**

- **In:** `Candidate[]`
- **Does:** runs every constraint in §6.3; produces per-constraint score **and** uncertainty; flags OOD
- **Tools:** **Proto** `Constraints` — ESMFold, PyRosetta, DSSP, FoldSeek; **ESM** embeddings for novelty
- **Out:** `ScoredCandidate[]`
- **Consumer:** Orchestrator (ranking), Optimizer (next round)

---

**Construct Agent** *(stretch — only if §9 M5 lands early)*

- **In:** top-ranked `ScoredCandidate`
- **Does:** codon-optimizes; adds promoter, RBS, reporter, tags; produces an orderable map
- **Tools:** **Benchling**
- **Out:** annotated construct + order-ready sequence

---

## 6. Data Contracts

Discussion doc §9 and §14.10 are right that the interfaces matter more than the modules. **These schemas are frozen at hour 4 and are the only cross-workstream dependency.** Everything else may change freely.

### 6.1 DesignRecord — orchestrator's single source of truth

```json
{
  "goal": "Protein switch actuated by >1500nm illumination",
  "mechanism": {
    "id": "photothermal-coiled-coil",
    "chain": ["1550nm", "water_vibrational_absorption", "local_dT", "coiled_coil_uncoiling", "derepression"],
    "evidence_refs": ["ev_003", "ev_007"],
    "status": "established",
    "rejected_alternatives": [
      {"id": "direct-chromophore-absorption", "reason": "0.83 eV below lowest known biological electronic transition (~1.2 eV)", "evidence_refs": ["ev_001"]}
    ]
  },
  "scaffold": {"name": "TlpA", "length_aa": 371, "uniprot": "RESOLVE_AT_M0", "immutable_regions": [[1, 120]]},
  "constraints": [ /* see 6.3 */ ],
  "human_decisions": [
    {"at": "mechanism_selection", "decision": "approved photothermal redirect", "by": "curator"}
  ]
}
```

### 6.2 EvidenceItem

```json
{
  "id": "ev_003",
  "question_id": "L2",
  "claim": "Water absorption is the primary energy-absorption mechanism for infrared neural stimulation",
  "claim_type": "mechanism",
  "quantitative": {"parameter": "absorption_coefficient", "value": 10, "unit": "cm^-1", "at_wavelength_nm": 1550},
  "support": "established",
  "citation": {"doi": "...", "title": "...", "year": 2016},
  "evidence_kind": "experimental",
  "extracted_by": "paperclip",
  "confidence": 0.9
}
```

`support` ∈ `established | contested | speculative` is the discussion doc's §3 requirement — *"distinguish literature-supported mechanisms from speculative hypotheses"* — made machine-readable. **Nothing marked `speculative` may become a hard constraint.**

### 6.3 Constraint

Each maps to one Proto `Constraint` callable.

```json
{
  "id": "c_tm_target",
  "description": "Transition midpoint in [40.5, 41.5] °C",
  "kind": "target_range",
  "target": {"min": 40.5, "max": 41.5, "unit": "celsius"},
  "evaluator": "proto:pyrosetta_ddg + calibrated_tm_regression",
  "weight": 1.0,
  "hard": true,
  "evidence_refs": ["ev_012"],
  "known_reliability": {"benchmark": "piraner_holdout", "mae_celsius": 2.1, "n": 12}
}
```

`known_reliability` is what separates this from a plausible-sounding number: each constraint reports *measured* accuracy on the positive-control set (§7), so the demo can say "this predictor is ±2.1 °C, here is how we know."

**The constraint set:**

| ID | Constraint | Hard? | Rationale |
|---|---|---|---|
| `c_tm_target` | Transition midpoint 40.5–41.5 °C | ✅ | The design goal (§2.4) |
| `c_off_state` | Predicted stable dimer at 37 °C | ✅ | No basal leak |
| `c_dbd_intact` | DNA-binding domain (≈1–120) unmutated | ✅ | Preserve DNA binding |
| `c_coiled_coil` | Heptad register preserved; DSSP helix content within 10% of WT | ✅ | Preserve mechanism |
| `c_fold_conf` | ESMFold pLDDT ≥ 70 over coiled-coil | ✅ | Reject unfoldable |
| `c_cooperativity` | Interface packing ≥ WT proxy | ⬜ | Preserve switch sharpness |
| `c_aggregation` | No introduced aggregation-prone motifs | ⬜ | Expressibility |
| `c_novelty` | ESM embedding distance from all known TlpA variants | ⬜ | Track C requires *new* |
| `c_evaluatability` | Testable by standard reporter assay | ⬜ | Discussion doc §5 |

### 6.4 ScoredCandidate

```json
{
  "id": "cand_017",
  "sequence": "MKIA...",
  "parent": "TlpA_WT",
  "mutations": ["L217A", "I224V", "N231D"],
  "generated_by": "proto:esm3_masked_sampling",
  "scores": {
    "c_tm_target":  {"value": 41.2, "unit": "celsius", "confidence": 0.61, "ood": false, "method": "calibrated_tm_regression"},
    "c_fold_conf":  {"value": 84.3, "unit": "pLDDT",   "confidence": 0.88, "ood": false, "method": "proto:esmfold"},
    "c_novelty":    {"value": 0.34, "unit": "cosine",  "confidence": 0.95, "ood": false, "method": "esm2_embedding"}
  },
  "aggregate": {"score": 0.78, "ci_low": 0.61, "ci_high": 0.89},
  "hard_violations": [],
  "flags": []
}
```

---

## 7. Uncertainty & the Positive-Control Benchmark

**Biological Plausibility** is scored on whether *"each model's uncertainty is surfaced rather than buried."* This section is the answer, and it is not optional polish.

### 7.1 Three uncertainty mechanisms

1. **Per-score confidence.** No bare numbers. Every entry in `scores` carries `confidence`, derived from ensemble variance across generation seeds and structure-prediction replicates.
2. **OOD flagging.** A candidate whose ESM embedding falls outside the convex hull of the training/reference set is flagged `ood: true`. Flagged predictions are **displayed but excluded from ranking**, and shown in the demo as excluded.
3. **Interval ranking.** Candidates rank by `ci_low`, not point estimate. A confidently-mediocre candidate beats a wildly-uncertain excellent one. This directly implements the discussion doc's §5 evaluatability argument.

### 7.2 The benchmark that makes it credible

Piraner et al.'s engineered TlpA variants span 32–46 °C with measured transition midpoints. We **hold out** a subset and require the pipeline to recover them.

- **Calibration set:** known variants → fit and calibrate the Tm predictor
- **Held-out set:** never seen → measures true predictive error
- **Report:** MAE in °C, populating `known_reliability` on `c_tm_target`

**Gate:** if held-out MAE > 3 °C, we do not claim a 41 °C design target. We widen the stated interval to match measured error and say so plainly on the slide. *A predictor that cannot resolve 2 °C cannot be used to claim a 2 °C design win.*

This is discussion doc §6's positive-control idea, with a real dataset behind it — and it is the single strongest defense against "plausible-sounding but unfounded" in front of judges.

### 7.3 Honest limitations (stated in the demo, not hidden)

- ΔTm prediction for coiled-coils is **weakly validated**; PyRosetta ΔΔG correlates with but does not equal transition midpoint shift.
- The thermal transient magnitude is estimated from published INS parameters, not simulated for our specific geometry.
- No candidate has been expressed. All results are predictions.
- Cooperativity is a **structural proxy**, not a measured Hill coefficient.

---

## 8. Demo Narrative

Three minutes, four beats. The narrative is the product; build toward it from hour 0.

**Beat 1 — The question and the wall (45 s).**
Type the original goal. Watch agent L1 search the literature and return the ceiling: nothing in known protein chemistry absorbs below ~1.2 eV. Show the pipeline *rejecting its own initial framing* and writing `rejected_alternatives` into the Design Record. **This is the Literature Integration moment.** Most teams will show search improving a design; we show search *killing* one.

**Beat 2 — The redirect (45 s).**
Agent L2 finds water absorption and the INS literature. The mechanism chain assembles. The human curator approves. Constraints acquire real numbers with citations attached.

**Beat 3 — Generation under constraint (60 s).**
Proto generators propose variants; constraints filter; the optimizer steers. Show the funnel: N proposed → N passing hard constraints → N novel. Show a candidate getting **rejected** for breaking heptad register — evidence the constraints have teeth.

**Beat 4 — The artifact and its error bars (30 s).**
Top-5 sequences with mutations, predicted midpoints, and confidence intervals. Next to them: the held-out benchmark MAE. Say the sentence out loud: *"our Tm predictor is accurate to ±X °C on held-out known variants, so here is what we can and cannot claim."*

Judges see a lot of confident wrong answers at hackathons. Calibrated confidence is the differentiator.

---

## 9. Milestones (48 h)

| # | Hour | Milestone | Owner | Exit criteria |
|---|---|---|---|---|
| **M0** | 0–4 | Setup & contracts frozen | All | Proto MCP responding; Paperclip verified; §6 schemas committed; **TlpA sequence + UniProt accession resolved and the DBD/coiled-coil boundary confirmed from annotation** (PRD's ≈120 is an estimate from 371 aa − ~250 aa coiled-coil) |
| **M1** | 4–12 | Literature layer | WS2 | L1–L4 run; ≥20 `EvidenceItem`s; **L1 negative result reproduced end-to-end** |
| **M2** | 8–16 | Constraint layer | WS3 | All hard constraints executable as Proto `Constraint`s; run on WT TlpA as sanity check |
| **M3** | 16–26 | **Benchmark gate** | WS3 | Piraner held-out MAE measured and recorded. **Go/no-go on the 41 °C claim (§7.2)** |
| **M4** | 20–32 | Generation loop | WS3 + WS1 | ≥100 candidates generated, scored, ranked; funnel numbers recorded |
| **M5** | 30–38 | Orchestration end-to-end | WS1 | Single command: goal → ranked candidates. Design Record complete with human decisions logged |
| **M6** | 36–44 | Demo build | All | Beats 1–4 rehearsed; funnel + benchmark visuals done |
| **M7** | 44–48 | Buffer & submission | All | Rehearsed twice. Slides frozen |
| **S1** | *if M5 ≤ h34* | Benchling construct | WS1 | Orderable construct for top candidate |

### 9.1 Critical path and the one real risk

`M0 → M2 → M3 → M4`. **M3 is the gate.** If the Tm predictor is uninformative, §7.2 says we widen the claim rather than fake it — the demo survives, because a calibrated negative is still a legitimate Track C result. Do not let M3 slip past hour 26.

### 9.2 Workstreams

| WS | People | Owns | Depends on |
|---|---|---|---|
| **WS1 — Orchestration** | 1–2 | Design Record, orchestrator loop, human-in-loop curation, demo, Benchling stretch | §6 schemas |
| **WS2 — Literature** | 1–2 | Paperclip agents L1–L4, evidence extraction, citation tracking | §6.2 schema |
| **WS3 — Design & Eval** | 2 | Proto generators, constraint implementations, benchmark, ranking | §6.3, §6.4 schemas |

After hour 4, workstreams are independent. **Anyone blocked on another workstream should mock the interface and keep moving** — the schemas are frozen precisely so this is always possible.

---

## 10. Risks

| Risk | L | Impact | Mitigation |
|---|---|---|---|
| Tm predictor uninformative | **High** | Weakens the central claim | M3 gate; widen stated interval; report honestly (§7.2) |
| Proto install/GPU friction eats hours | **High** | Blocks critical path | Timeboxed to M0; fall back to `device="modal"`; if both fail, ESM2 pseudo-likelihood only |
| Literature agent misses the L1 negative result | Med | Kills demo Beat 1 | Pre-test L1 in M1; keep a curated fallback evidence set (disclosed if used) |
| Candidates are trivial (single conservative mutations) | Med | Weak on Generation | Require ≥3 mutations and `c_novelty` above threshold |
| Paperclip coverage gaps on optics/physics literature | Med | L1/L2 thin | Paperclip is biomedical-focused; supplement L1 with general web search and label the source |
| Scope creep toward "general framework" | **High** | Loses Track C focus | §1.1 tiebreaker: candidate set always wins |
| Over-claiming in the demo | Med | Fails Biological Plausibility | §7.3 limitations slide is mandatory, not optional |

---

## 11. Success Criteria

**Minimum (must have):**
- [ ] ≥5 novel TlpA variants, each ≥3 mutations, none in any database
- [ ] Every design constraint traces to a cited `EvidenceItem`
- [ ] The L1 negative result is agent-derived and shown in the demo
- [ ] Every reported score carries a confidence value
- [ ] Held-out benchmark MAE measured and reported

**Target:**
- [ ] ≥100 candidates generated and scored; funnel visualized
- [ ] Held-out Tm MAE ≤ 3 °C
- [ ] End-to-end single-command run
- [ ] All 5 sponsor tools used substantively

**Stretch:**
- [ ] Benchling construct, order-ready
- [ ] Second scaffold (TcI) run through the same pipeline — the generality evidence
- [ ] BenchFlow-packaged eval others can reproduce

---

## 12. Open Questions

1. **Which Tm predictor?** PyRosetta ΔΔG + calibrated regression is the plan, but a simple heptad-position lookup fit to Piraner data may outperform it. **Decide at M2 by benchmark, not by preference.**
2. **How much orchestrator autonomy?** Discussion doc §12 flags this. Default: human approves at mechanism selection and final ranking only. Everything else is autonomous.
3. **Host organism?** *E. coli* (matches Piraner's characterization, simplest) vs. mammalian (matches the INS/tissue story). Affects only the stretch construct. **Defer to S1.**
4. **1550 nm vs 1930 nm?** Carry both to M4; let the required ΔT decide.

---

## References

- [Tunable thermal bioswitches for in vivo control of microbial therapeutics — *Nature Chemical Biology*](https://www.nature.com/articles/nchembio.2233) (Piraner et al.) — TlpA/TcI engineered variants, 32–46 °C
- [In vitro neuronal depolarization and increased synaptic activity induced by infrared neural stimulation — *Biomed. Opt. Express*](https://opg.optica.org/boe/fulltext.cfm?uri=boe-7-9-3211&id=348271) — TRPV4 involvement at 1875 nm
- [Advances in the Regulation of Neural Function by Infrared Light — *IJMS*](https://www.mdpi.com/1422-0067/25/2/928) — photothermal mechanism review
- [Identifying optimal parameters for infrared neural stimulation in the peripheral nervous system](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8010905/) — D₂O control, water absorption as primary mechanism
- [Modular Thermal Control of Protein Dimerization — *bioRxiv*](https://www.biorxiv.org/content/10.1101/694448v1.full) — coiled-coil thermal switch engineering
- [A proteinaceous gene regulatory thermometer in Salmonella — *Cell*](https://www.cell.com/fulltext/S0092-8674(00)80313-X) (Hurme et al. 1997) — TlpA thermosensing mechanism
- [A new alpha-helical coiled coil protein encoded by the Salmonella typhimurium virulence plasmid — PubMed](https://pubmed.ncbi.nlm.nih.gov/1601892/) — TlpA is 371 aa, Mr 41600, pI 4.63
- [DNA binding exerted by a bacterial gene regulator with an extensive coiled-coil domain — PubMed](https://pubmed.ncbi.nlm.nih.gov/8647874/) — N-terminal DBD, ~250 aa coiled-coil to C-terminus
- [Proto: A programming language for generative biology — Arc Institute](https://arcinstitute.org/news/proto) — Sequences/Generators/Constraints/Optimizers
- [evo-design/proto-tools — GitHub](https://github.com/evo-design/proto-tools) — ~80 tools, MCP server mode
- [BenchFlow](https://www.benchflow.ai/) — agent evaluation environments
- The originating team discussion — no longer in the repo; superseded by this document (see §1.2)
