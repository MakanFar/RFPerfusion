# PRD — Agentic Design Framework

**A general system that converts an underspecified scientific design objective into evidence-grounded, computationally evaluable candidate designs.**

| | |
|---|---|
| **Document** | PRD-2 (framework/product) |
| **Relationship to `PRD.md`** | Complementary, not superseding. See §1.3 |
| **Date** | 2026-08-15 |
| **Status** | Draft for team review |
| **Working name** | TBD — "the Framework" throughout |

---

## 1. Framing

### 1.1 What the product is

The product is **not** a protein. It is a system that takes a sentence from a scientist and returns a ranked, cited, uncertainty-annotated set of candidate designs — along with the reasoning trace that produced them.

> **Input:** *"Design an ion channel that is sensitive to radio frequency pulses."*
>
> **Output:** A portfolio of mechanistic routes (ranked, cited, with rejected alternatives and the reason for rejection), a design specification for each surviving route, candidate sequences generated against those specifications, and evaluation scores with calibrated error bars.

The domain instance is interchangeable. The loop is the product.

### 1.2 The user and the job

The user is a **working experimental scientist** with a design goal they cannot immediately reduce to a computable task. Their actual bottleneck is not sequence generation — it is the step *before* that: knowing which of the many possible physical mechanisms is worth spending months of wet-lab time on.

The job to be done: **compress months of literature review and mechanism triage into hours, without producing confident nonsense.**

That last clause is the whole product. A system that outputs twenty plausible-sounding mechanisms with no ability to distinguish the real from the ruled-out is worse than nothing, because it launders speculation into something that looks like analysis.

### 1.3 Relationship to `PRD.md`

`PRD.md` is deliberately scoped to win a specific hackathon track that judges *the biological artifact*. It optimizes for one vertical (SWIR → TlpA thermal switch) and explicitly names "scope creep toward a general framework" as a high risk.

**Both documents are correct within their scope.** This one describes the product; that one describes the 48-hour demo. The reconciliation:

| | `PRD.md` | This document |
|---|---|---|
| Judged artifact | Sequences | The loop |
| Time horizon | 48 h | Post-hackathon product |
| Reference instance | SWIR → TlpA | RF → ion channel, *plus* TlpA as the calibration instance |
| Role of the other doc | — | `PRD.md`'s pipeline is **instance #1**, the proof the loop closes |

**If forced to choose during the hackathon, `PRD.md` wins.** This document defines what instance #1 must not foreclose.

---

## 2. What changed from the proposed three-layer architecture

The originating proposal was three layers: **(1)** ideate mechanisms and write specs → **(2)** subagents generate sequences → **(3)** evaluate with folding tools.

That decomposition is sound. Five changes, each with a reason:

| Proposed | This PRD | Reason |
|---|---|---|
| Ideation → Generation → Evaluation (one direction) | Evaluator capability registry is an **input to ideation** | You cannot design against an objective you cannot score. Detail in §4.2 |
| Rank 20 routes by "feasibility" | Rank by **decisiveness of the cheapest next test**; cluster into mechanism *classes* for review | LLM feasibility ranking is unreliable and anchors on fame, not physics. §4.3 |
| Ideation → Specification directly | A **Falsification stage** sits between them | The single highest-value component. §4.4 |
| Waterfall | Evaluation results **feed back** and reallocate route budget | Otherwise 19 of 20 routes are wasted work. §4.6 |
| Human reviews the 20 routes | Human's **mandatory** gate is spec approval; route review is assisted and optional | Scientist attention is the scarce resource; the spec is what everything downstream optimizes. §6 |

---

## 3. Product Principles

These are the tiebreakers. When a design decision is contested, resolve it against this list in order.

1. **Nothing enters the pipeline without a computable evaluator.** A design objective that cannot be scored is a wish, not a specification.
2. **Every score carries calibrated uncertainty, or it is not reported.** An uncalibrated number is worse than no number.
3. **Rejection is a first-class output.** The routes the system killed, and why, are as valuable as the ones it kept — often more.
4. **Evidence has provenance and epistemic status.** `established | contested | speculative` is machine-readable and load-bearing. Nothing `speculative` becomes a hard constraint.
5. **The human is consulted where they are decisive, not where they are merely present.**
6. **Generality is proven by a second instance, never asserted.**

---

## 4. Architecture

### 4.1 Overview

```
                          ┌───────────────────────────────────┐
                          │      EVALUATOR REGISTRY           │
                          │  what properties can we compute,  │
                          │  and how accurate is each one?    │
                          └───────────────┬───────────────────┘
                                          │ constrains
                                          ▼
  Scientist ──objective──▶ ┌──────────────────────────┐
      ▲                    │  L1  IDEATION            │  ≥20 routes → clustered
      │                    │      mechanism discovery │     into classes
      │  cluster review    └────────────┬─────────────┘
      │  (assisted)                     │
      │                                 ▼
      │                    ┌──────────────────────────┐
      │                    │  L1.5  FALSIFICATION     │  adversarial: kill routes
      │                    │        red-team          │  on physics / evidence
      │                    └────────────┬─────────────┘
      │                                 │ survivors
      │  ██ SPEC APPROVAL ██            ▼
      │  (mandatory gate)   ┌──────────────────────────┐
      └────────────────────▶│  L2  SPECIFICATION       │  DesignSpec per route
                            │      objective → task    │  (evaluator-bound)
                            └────────────┬─────────────┘
                                         │ fan-out, one subagent per spec
                                         ▼
                            ┌──────────────────────────┐
                            │  L3  GENERATION          │  Candidate sequences
                            └────────────┬─────────────┘
                                         ▼
                            ┌──────────────────────────┐
                            │  L4  EVALUATION          │  scores + uncertainty
                            └────────────┬─────────────┘
                                         │
                    ┌────────────────────┴─────────────┐
                    │  PORTFOLIO CONTROLLER            │
                    │  reallocate budget across routes │──┐
                    └──────────────────────────────────┘  │
                                         ▲                │
                                         └────────────────┘
                                          retire / double down
```

Five stages, not three — the two additions are the Falsification stage and the Portfolio Controller. Both exist to prevent specific, predictable failures.

Agents communicate **only** through typed artifacts (§5). No agent reads another agent's prose.

### 4.2 The Evaluator Registry — the inversion

**This is the most important structural decision in the document.**

The proposed architecture flows ideation → generation → evaluation. But the binding constraint flows the other way:

> What we can **evaluate** determines what we can meaningfully **generate**, which determines what routes are worth **ideating** about.

A system that ideates freely and evaluates last will reliably produce beautiful, well-cited, completely unfalsifiable output — sequences designed against objectives nothing can score. This is the dominant failure mode for agentic design systems and it is not obvious from the outside, because the output *looks* excellent.

The fix: the registry of available evaluators is an **input** to ideation, and the specification stage **cannot emit a spec whose objectives lack evaluator bindings.**

```json
{
  "evaluator_id": "esmfold_plddt",
  "measures": ["fold_confidence"],
  "applicable_to": {"molecule_class": ["soluble_protein"], "length_max": 1000},
  "known_reliability": {"benchmark": "casp15_subset", "metric": "TM-score", "value": 0.81, "n": 70},
  "cost": {"gpu_seconds": 12},
  "status": "validated"
}
```

Routes whose objectives have **no** evaluator are not discarded — they are returned to the scientist labeled `requires_new_evaluator`, with an estimate of what building it would cost. That is genuinely useful output ("this idea is good but you'd need to build an assay first"), and it is honest.

### 4.3 Ideation (L1) — breadth without the ranking illusion

**Requirement:** ≥20 candidate mechanistic routes.

**But raw count is a coverage metric, not a quality metric.** Twenty LLM-generated mechanisms will typically contain ~3 genuinely distinct real options, ~7 restatements of each other, and ~10 that are physically ruled out but confidently phrased. Two corrections:

**(a) Enforce structural diversity, not numeric count.** Routes are tagged by *mechanism class* (direct absorption / thermal transduction / mechanical / chemical intermediary / cofactor-dependent / synthetic-material-coupled / …). Coverage is measured over classes. Twenty routes in three classes is worse than twelve routes across eight.

**(b) Do not rank by "feasibility."** LLM feasibility judgments anchor on how frequently a mechanism appears in the training corpus, which correlates with fame, not with physics. Rank instead by:

> **Decisiveness** — how cheaply and how definitively can this route be killed or confirmed?

This is a question about *evidence and evaluators*, which is far more tractable than an abstract physics judgment. It also produces a genuinely useful ordering: the scientist works down the list killing cheap-to-kill routes first, and the expensive ambiguous ones are deferred until the field has narrowed.

Each route carries a mandatory **kill criterion** — the specific finding that would eliminate it. A route without a kill criterion is not a hypothesis and is rejected at emission.

### 4.4 Falsification (L1.5) — the adversarial stage

A dedicated stage whose **only** job is to kill routes. It is prompted adversarially — its success metric is routes eliminated, not routes preserved.

Three checks per route:

1. **Physical bound check.** Order-of-magnitude feasibility against conservation laws and known limits. (*Energy per photon vs. transition energies; thermal budget vs. protein stability; force scales vs. gating thresholds; SNR vs. thermal noise at 310 K.*)
2. **Evidence status check.** Does the literature *establish* this, *contest* it, or merely *mention* it? A contested mechanism is not disqualifying — but it must be labeled, and it cannot become a hard constraint.
3. **Evaluator availability check.** Can any registered evaluator score this route's objective?

`PRD.md` §2.1 is exactly this stage, executed manually and hardcoded for one instance. **Generalizing it is the single highest-value thing this framework does**, because it is the step that separates the product from a well-dressed brainstorming tool.

The falsification stage's output — the rejected routes with reasons and citations — is a **headline deliverable**, not a byproduct.

### 4.5 Specification (L2) — where the real difficulty lives

The proposal treats "the agent will write specification files for subagents" as a single step. It is the hardest step in the system.

A spec must convert a *mechanism* into an *executable design task*:

> mechanism: photothermal coiled-coil de-repression
> → spec: shift transition midpoint 43.5 °C → 41.0 ± 0.5 °C; cooperativity ≥ WT; residues 1–120 immutable; heptad register preserved; pLDDT ≥ 70 over the coiled-coil

That translation is a dense act of scientific judgment: choosing a scaffold, identifying which degrees of freedom are mutable, setting quantitative targets, and knowing which structural features carry the mechanism. If the framework cannot do this reliably, **L1 is a brainstorming toy and L3 is a human-driven pipeline in an agent costume.**

Accordingly the `DesignSpec` is the most tightly-typed artifact in the system (§5.3), it is the **mandatory human approval gate** (§6), and it is invalid unless every objective carries an evaluator binding.

### 4.6 Portfolio Controller — closing the loop

In a waterfall, twenty routes are generated and one is pursued; the other nineteen are wasted tokens. Worse, if the chosen route fails at L4, there is no path back.

Treat routes as a **portfolio of hypotheses under a compute budget**:

- Each surviving route gets an initial allocation, weighted by decisiveness rank.
- L4 results update the route's posterior.
- Routes that fail hard constraints across their candidate batch are **retired**, and their remaining budget is reallocated.
- The scientist sees the allocation and can override it.

This is what makes "≥20 routes" pay for itself rather than being a number that looks impressive in a demo.

---

## 5. Data Contracts

Frozen early; the only cross-workstream dependency. Everything else may change freely.

### 5.1 DesignObjective

```json
{
  "id": "obj_001",
  "statement": "An ion channel that opens in response to radio-frequency pulses",
  "molecule_class": "membrane_protein",
  "actuation": {"modality": "electromagnetic", "band": "RF", "frequency_hz": 1e7},
  "context": {"host": "mammalian_neuron", "temperature_k": 310},
  "success_definition": "RESOLVE_AT_SPEC",
  "constraints_from_scientist": ["no exogenous nanoparticle injection"],
  "provenance": {"author": "scientist", "at": "2026-08-15T09:00:00Z"}
}
```

### 5.2 Route

```json
{
  "id": "route_007",
  "objective_id": "obj_001",
  "mechanism_class": "thermal_transduction",
  "chain": ["RF_field", "magnetic_nanoparticle_hysteresis", "local_dT", "TRPV1_gating", "Ca_influx"],
  "evidence_refs": ["ev_014", "ev_022"],
  "support": "established",
  "kill_criterion": "If required field strength exceeds safe SAR limits by >10x, route is dead",
  "decisiveness": {"cheapest_decisive_test": "analytic thermal budget calculation", "cost_hours": 0.5, "rank": 3},
  "evaluator_coverage": "full",
  "status": "surviving"
}
```

### 5.3 DesignSpec — the load-bearing artifact

```json
{
  "id": "spec_007",
  "route_id": "route_007",
  "scaffold": {"name": "TRPV1", "uniprot": "Q8NER1", "immutable_regions": [[1, 110]]},
  "mutable_space": {"regions": [[430, 470]], "max_mutations": 8},
  "objectives": [
    {
      "id": "o_gating_temp",
      "description": "Gating threshold lowered to 39.0 +/- 0.5 C",
      "kind": "target_range",
      "target": {"min": 38.5, "max": 39.5, "unit": "celsius"},
      "hard": true,
      "evaluator_binding": "evaluator:tm_regression_v2",
      "evidence_refs": ["ev_031"]
    }
  ],
  "human_approval": {"by": "curator", "at": "...", "notes": "narrowed mutable region"},
  "unbound_objectives": []
}
```

**Validation rule:** `unbound_objectives` must be empty for the spec to enter L3. This is the mechanical enforcement of Principle 1.

### 5.4 EvidenceItem, Candidate, ScoredCandidate

Reuse `PRD.md` §6.2 and §6.4 unchanged. They are well-designed and domain-neutral already — the only edit is that `ScoredCandidate` gains `spec_id` and `route_id` so results attribute back to the portfolio.

---

## 6. Human-in-the-Loop Model

The scientist's attention is the scarcest and most expensive resource in the system. Spend it where it changes outcomes.

| Stage | Interaction | Mandatory? | Cost to scientist |
|---|---|---|---|
| Objective entry | Free text + clarifying questions | ✅ | ~5 min |
| Route review | Review **clusters** (5–8 classes), not 20 items; drill down on demand | ⬜ assisted | ~15 min |
| Falsification review | Confirm/override kills; surface any the scientist disagrees with | ⬜ | ~10 min |
| **Spec approval** | Approve or edit the objective function | ✅ **hard gate** | ~20 min |
| Portfolio reallocation | Override budget shifts | ⬜ | ~5 min |
| Final ranking | Curate shortlist | ✅ | ~15 min |

**Why the gate moved.** The originating proposal puts the heavy human review at the route stage — read 20 mechanisms, pick some. But the route choice is *recoverable* (the portfolio controller can retire a bad route and move on) while the spec is *not* — everything downstream optimizes against it, and a subtly wrong objective function produces a large volume of confidently-wrong output. Put the mandatory gate where errors are unrecoverable.

Reviewing 20 unclustered routes is also a poor use of 20 minutes. Clustering to mechanism classes cuts review cost roughly 3× with negligible information loss, because within-class routes usually share a fate.

---

## 7. Calibration — what makes any of this credible

Every evaluator carries **measured** reliability on a held-out benchmark, recorded in the registry and surfaced in every score that uses it. This generalizes `PRD.md` §7.2 from one instance to a standing requirement.

- **Uncalibrated evaluators may run, but their scores cannot rank candidates** — they are advisory only and displayed as such.
- **Gate rule:** the system may not claim a design margin finer than the measured error of the evaluator that produced it. If Tm prediction is ±3 °C, a 2 °C design win is not claimable. This rule is enforced in the reporting layer, not left to the presenter's judgment.
- **OOD flagging:** candidates outside the evaluator's applicability domain are shown but excluded from ranking.

The framework's credibility rests almost entirely on this section. Without it, the output is well-formatted speculation.

---

## 8. Proving Generality

A framework that has run one objective is a pipeline with extra indirection. Minimum evidence of generality:

**Two structurally dissimilar objectives, end to end, with no code changes — only new registry entries.**

| Instance | Objective | Molecule class | Why it tests something different |
|---|---|---|---|
| **A** | SWIR-actuated transcriptional switch (`PRD.md`) | Soluble coiled-coil | Strong evaluators, known ground truth (Piraner variants) |
| **B** | RF-sensitive ion channel | Membrane protein | Weak evaluators, contested literature, no ground truth |
| **C** *(calibration)* | A solved problem with published answer | Any | Does the loop *recover* the known answer? |

Instance C is the honest test and should be run first. If the framework cannot rediscover an answer that is already known, its output on genuinely novel problems is not trustworthy.

---

## 9. Success Criteria

**Minimum:**
- [ ] One objective traverses all five stages without human code intervention
- [ ] ≥20 routes generated, covering ≥6 mechanism classes, each with a kill criterion
- [ ] Falsification stage kills ≥1 route on physical grounds, with citation
- [ ] Every spec objective has an evaluator binding; `unbound_objectives` empty at L3 entry
- [ ] Every reported score carries calibrated uncertainty
- [ ] Rejected routes are a visible output artifact

**Target:**
- [ ] Two structurally dissimilar objectives run with registry entries only
- [ ] Portfolio controller retires a route on L4 evidence and reallocates
- [ ] Calibration instance recovers a known published answer
- [ ] Scientist total interaction time < 90 min per objective

**Stretch:**
- [ ] `requires_new_evaluator` routes returned with build-cost estimates
- [ ] Third-party can add an evaluator to the registry without touching framework code

---

## 10. Non-Goals

- **Not an autonomous scientist.** The human approves the objective function. Always.
- **Not a wet-lab replacement.** Output is a prioritized hypothesis set, not a result.
- **Not a new predictor.** The framework orchestrates and calibrates existing tools; it does not train models.
- **Not domain-locked to proteins.** The contracts are written molecule-class-agnostic, but proteins are the only validated instance and we will not claim otherwise.

---

## 11. Risks

| Risk | L | Impact | Mitigation |
|---|---|---|---|
| Specification stage is too hard to automate; humans write specs by hand | **High** | The framework becomes a UI over a manual process | Instrument it: log every human edit to a generated spec. That edit distance *is* the metric for L2 quality |
| Ideation produces fluent, well-cited, physically impossible routes | **High** | Core credibility failure | Falsification stage (§4.4); kill criterion mandatory at emission |
| No evaluator exists for the interesting objectives | **High** | Pipeline runs but proves nothing | Evaluator registry as ideation input (§4.2); `requires_new_evaluator` as a legitimate output |
| Twenty routes, one pursued, nineteen wasted | Med | Cost with no return | Portfolio controller (§4.6) |
| Generality asserted from one instance | Med | The claim collapses under questioning | §8 — two instances or no claim |
| Framework work cannibalizes the hackathon artifact | **High** | Lose Track C | `PRD.md` §1.1 tiebreaker stands: candidate set wins |

---

## 12. Open Questions

1. **Which reference objective leads — SWIR/TlpA or RF/ion channel?** They differ sharply in evaluator strength (§8). Recommendation: TlpA as the *calibration* instance, RF ion channel as the *generality* instance. Decide before any L2 work.
2. **How is "mechanism class" defined?** A fixed taxonomy is brittle; an emergent one is unstable across runs. Suggest: fixed top-level classes, emergent sub-classes.
3. **What is the unit of portfolio budget?** GPU-seconds, wall-clock, or candidate count. Affects the controller's design.
4. **Does the scientist edit specs directly, or converse?** Direct editing is faster for experts and produces a cleaner edit-distance metric; conversation is more accessible.
5. **Where does the evaluator registry live**, and who is allowed to write to it?

---

## References

- `PRD.md` — instance #1, SWIR/TlpA vertical
- `Team Discussion Summary & Proposed Project Direction.md` — originating discussion; §7 (skills vs. agents), §10 (framework framing), §12 (open risks)
