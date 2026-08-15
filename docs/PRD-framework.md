# PRD — Agentic Design Framework

**Converts an underspecified scientific design objective into evidence-grounded, computationally evaluable candidate designs.**

| | |
|---|---|
| **Document** | PRD-2 (framework/product) |
| **Relationship to `PRD-(outdated).md`** | Complementary. `PRD-(outdated).md` is instance #1; if the two conflict during the hackathon, `PRD-(outdated).md` wins |
| **Date** | 2026-08-15 |
| **Status** | Draft for team review |

---

## 1. Product

**In:** *"Design an ion channel sensitive to radio frequency pulses."*

**Out:** ranked mechanistic routes (cited, with rejected alternatives and reasons), a design spec per surviving route, candidate sequences, and evaluation scores with calibrated error bars.

The domain instance is interchangeable. The loop is the product.

**User:** an experimental scientist whose bottleneck is mechanism triage, not sequence generation.

---

## 2. Principles

Tiebreakers, in order.

1. **No objective enters the pipeline without a computable evaluator.**
2. **Every score carries calibrated uncertainty, or it is not reported.**
3. **Rejection is a first-class output.** Killed routes and their reasons ship.
4. **Evidence carries `established | contested | speculative`.** Nothing speculative becomes a hard constraint.
5. **Consult the human where they are decisive.**
6. **Generality is proven by a second instance, never asserted.**

---

## 3. Architecture

```
                      ┌─────────────────────────────┐
                      │   EVALUATOR REGISTRY        │
                      │   what can we compute, and  │
                      │   how accurate is each one? │
                      └──────────────┬──────────────┘
                                     │ constrains
                                     ▼
 Scientist ──objective──▶ ┌────────────────────────┐
     ▲                    │ L1  IDEATION           │ ≥20 routes → clustered
     │  cluster review    └───────────┬────────────┘
     │  (assisted)                    ▼
     │                    ┌────────────────────────┐
     │                    │ L1.5  FALSIFICATION    │ adversarial: kill routes
     │                    └───────────┬────────────┘
     │  ██ SPEC APPROVAL ██           ▼
     │  (mandatory gate)   ┌────────────────────────┐
     └────────────────────▶│ L2  SPECIFICATION      │ evaluator-bound DesignSpec
                           └───────────┬────────────┘
                                       ▼  fan-out, one subagent per spec
                           ┌────────────────────────┐
                           │ L3  GENERATION         │
                           └───────────┬────────────┘
                                       ▼
                           ┌────────────────────────┐
                           │ L4  EVALUATION         │ scores + uncertainty
                           └───────────┬────────────┘
                                       ▼
                           ┌────────────────────────┐
                           │ PORTFOLIO CONTROLLER   │──┐ retire / reallocate
                           └────────────────────────┘  │
                                       ▲───────────────┘
```

Agents communicate only through typed artifacts (§4). No agent reads another agent's prose.

**Evaluator registry (the inversion).** What we can evaluate determines what we can generate, which determines which routes are worth ideating. The registry is an *input* to L1. Routes with no evaluator return to the scientist labeled `requires_new_evaluator` with a build-cost estimate — a legitimate output, not a discard.

**L1 Ideation.** ≥20 routes, but coverage is measured over *mechanism classes*, not count. Rank by **decisiveness** — how cheaply and definitively can this route be killed — not by feasibility. Every route carries a mandatory kill criterion; a route without one is rejected at emission.

**L1.5 Falsification.** Adversarial stage, scored on routes eliminated. Three checks: physical bounds (order-of-magnitude against conservation laws), evidence status, evaluator availability. `PRD-(outdated).md` §2.1 is this stage hardcoded for one instance.

**L2 Specification.** Converts mechanism → executable design task: scaffold, mutable degrees of freedom, quantitative targets. The hardest step in the system. Instrument it — log every human edit to a generated spec; edit distance is the L2 quality metric.

**Portfolio Controller.** Routes are hypotheses under a compute budget. L4 results update allocation; routes failing hard constraints across their batch are retired and their budget reallocated.

---

## 4. Data Contracts

Frozen early. The only cross-workstream dependency.

### DesignObjective
```json
{
  "id": "obj_001",
  "statement": "An ion channel that opens in response to radio-frequency pulses",
  "molecule_class": "membrane_protein",
  "actuation": {"modality": "electromagnetic", "band": "RF", "frequency_hz": 1e7},
  "context": {"host": "mammalian_neuron", "temperature_k": 310},
  "constraints_from_scientist": ["no exogenous nanoparticle injection"]
}
```

### Route
```json
{
  "id": "route_007",
  "objective_id": "obj_001",
  "mechanism_class": "thermal_transduction",
  "chain": ["RF_field", "magnetic_nanoparticle_hysteresis", "local_dT", "TRPV1_gating"],
  "evidence_refs": ["ev_014", "ev_022"],
  "support": "established",
  "kill_criterion": "If required field strength exceeds safe SAR limits by >10x, route is dead",
  "decisiveness": {"cheapest_decisive_test": "analytic thermal budget", "cost_hours": 0.5, "rank": 3},
  "evaluator_coverage": "full",
  "status": "surviving"
}
```

### DesignSpec
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

**Validation rule:** `unbound_objectives` must be empty for a spec to enter L3.

### Evaluator
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

**EvidenceItem, Candidate, ScoredCandidate:** reuse `PRD-(outdated).md` §6.2 and §6.4 unchanged, plus `spec_id` and `route_id` on `ScoredCandidate`.

---

## 5. Human-in-the-Loop

| Stage | Interaction | Mandatory | Cost |
|---|---|---|---|
| Objective entry | Free text + clarifying questions | ✅ | ~5 min |
| Route review | Review 5–8 clusters, drill down on demand | ⬜ | ~15 min |
| Falsification review | Confirm/override kills | ⬜ | ~10 min |
| **Spec approval** | Approve or edit the objective function | ✅ **gate** | ~20 min |
| Portfolio reallocation | Override budget shifts | ⬜ | ~5 min |
| Final ranking | Curate shortlist | ✅ | ~15 min |

The gate is at spec approval because route choice is recoverable and spec choice is not.

---

## 6. Calibration

- Every evaluator carries measured reliability on a held-out benchmark, surfaced in every score using it.
- **Uncalibrated evaluators may run; their scores may not rank candidates.**
- **No claimed design margin finer than the evaluator's measured error.** Enforced in the reporting layer.
- Candidates outside an evaluator's applicability domain are shown, flagged, and excluded from ranking.

---

## 7. Proving Generality

Two structurally dissimilar objectives, end to end, **new registry entries only, no code changes.**

| Instance | Objective | Class | Tests |
|---|---|---|---|
| **A** | SWIR transcriptional switch (`PRD-(outdated).md`) | Soluble coiled-coil | Strong evaluators, known ground truth (Piraner) |
| **B** | RF-sensitive ion channel | Membrane protein | Weak evaluators, contested literature, no ground truth |
| **C** | A solved problem with published answer | Any | Does the loop recover the known answer? |

Run C first.

---

## 8. Success Criteria

**Minimum**
- [ ] One objective traverses all five stages without code intervention
- [ ] ≥20 routes across ≥6 mechanism classes, each with a kill criterion
- [ ] Falsification kills ≥1 route on physical grounds, with citation
- [ ] `unbound_objectives` empty at every L3 entry
- [ ] Every reported score carries calibrated uncertainty
- [ ] Rejected routes ship as a visible artifact

**Target**
- [ ] Two dissimilar objectives run with registry entries only
- [ ] Portfolio controller retires a route on L4 evidence
- [ ] Calibration instance recovers a known published answer
- [ ] Scientist interaction < 90 min per objective

---

## 9. Non-Goals

- Not an autonomous scientist — the human approves the objective function.
- Not a wet-lab replacement — output is a prioritized hypothesis set.
- Not a new predictor — the framework orchestrates and calibrates existing tools.
- Not domain-general in claim — contracts are molecule-class-agnostic, proteins are the only validated instance.

---

## 10. Risks

| Risk | L | Mitigation |
|---|---|---|
| L2 too hard to automate; humans write specs by hand | **High** | Log spec edit distance — it is the metric |
| Ideation produces fluent, cited, impossible routes | **High** | L1.5; mandatory kill criterion |
| No evaluator for the interesting objectives | **High** | Registry as L1 input; `requires_new_evaluator` as output |
| 20 routes, one pursued | Med | Portfolio controller |
| Generality asserted from one instance | Med | §7 — two instances or no claim |
| Framework work cannibalizes the hackathon artifact | **High** | `PRD-(outdated).md` tiebreaker stands |

---

## 11. Open Questions

1. **Which reference objective leads — SWIR/TlpA or RF/ion channel?** They differ sharply in evaluator strength. Recommend TlpA as calibration, RF as generality. Decide before any L2 work.
2. **How is "mechanism class" defined?** Suggest fixed top-level classes, emergent sub-classes.
3. **Unit of portfolio budget** — GPU-seconds, wall-clock, or candidate count?
4. **Does the scientist edit specs directly or converse?**
5. **Where does the evaluator registry live, and who writes to it?**

---

## References

- `PRD-(outdated).md` — instance #1, SWIR/TlpA vertical
- `Team Discussion Summary & Proposed Project Direction.md` — originating discussion
