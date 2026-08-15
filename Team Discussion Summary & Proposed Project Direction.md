# Team Discussion Summary & Proposed Project Direction

## 1. Core Problem

The team discussed using an **AI-driven, multi-agent pipeline for protein design**, with the initial motivating example being the design of a protein that responds to a particular physical stimulus—specifically, a protein with sensitivity at wavelengths greater than ~1500 nm.

The important realization was that the project should **not be framed only as “design this one protein.”** The more general and potentially impactful goal is to build a reusable system that takes a complex scientific design problem, decomposes it into tractable research and engineering questions, searches the literature for candidate mechanisms, evaluates possible designs, and iteratively narrows the solution space.

The RF/wavelength-responsive protein would therefore serve as a **challenging test case for the general protein-design pipeline**, rather than necessarily being the sole deliverable.

---

# 2. Proposed High-Level Pipeline

### Input: Scientific Design Goal

A researcher begins with a high-level question such as:

> “How can we design a protein that responds to wavelengths greater than 1500 nm?”

Rather than immediately asking an LLM to design the protein, the system first helps **formalize and decompose the problem**.

### Stage 1 — Problem Formulation & Decomposition

An LLM interacts recursively with the researcher to identify:

- What exactly is the desired function?
- What physical mechanism could produce that function?
- What biological components are required?
- What constraints exist?
- What aspects of the problem are already understood?
- Which parts require literature evidence?
- Which parts can be evaluated computationally?
- Which candidate designs are realistically verifiable?

The human researcher acts as a **curator/validator**, accepting or rejecting proposed design directions.

This is important because expert prompting appears to substantially improve the ability of LLMs to converge on useful solutions. The system should therefore use the expert not merely at the beginning or end, but as part of an iterative narrowing process.

---

# 3. Stage 2 — Literature Research Agent

Once the problem has been decomposed into specific research questions, specialized literature agents investigate each component.

For example, the system could separately investigate:

- Existing wavelength-responsive proteins
- Naturally occurring proteins with related functions
- Engineered proteins and prior protein-engineering strategies
- Mechanisms capable of shifting wavelength sensitivity
- Structural features associated with the desired function
- Known sequence/function relationships
- Existing computational approaches for predicting the relevant property

Rather than having one LLM search everything, the team discussed potentially **spawning multiple specialized agents**, each investigating a different part of the problem.

The outputs would then be consolidated into an evidence layer containing:

- Candidate proteins
- Candidate mechanisms
- Supporting papers
- Relevant experimental evidence
- Sequence/structure information
- Citations
- Confidence/evidence strength

A key goal is to avoid simply producing plausible-sounding ideas. The system should be able to distinguish **literature-supported mechanisms from speculative hypotheses**.

---

# 4. Stage 3 — Candidate Generation

The literature stage should produce a constrained set of candidate starting points rather than asking the model to invent arbitrary proteins from scratch.

For example:

**Goal → mechanisms → known proteins → candidate sequences/design directions**

One proposed workflow was to identify several plausible mechanisms and then generate approximately 3–5 strong candidate directions.

The candidate-generation process could potentially use:

- Known protein sequences
- Protein language-model embeddings
- Structural similarity
- Functional annotations
- Sequence/function relationships
- Existing engineered variants
- Related protein families

One idea discussed was clustering known wavelength-responsive or fluorescent proteins using **ESM embeddings or structural representations** to identify classes and potentially discover useful regions of protein space.

---

# 5. Stage 4 — Computational Evaluation / Simulation

The next stage evaluates whether the proposed candidates are computationally plausible.

The team discussed several possible levels of evaluation:

### Protein-level evaluation

Depending on the proposed mechanism:

- Structure prediction
- Protein language-model representations
- Sequence/structure similarity
- Functional-property prediction
- Optical-property prediction

### Simulation

Where feasible, simulations could be used to test whether a proposed mechanism behaves as expected.

However, the team noted that expensive molecular-dynamics simulations may be too slow to place directly inside an iterative agent loop.

Therefore, simulation may initially function better as a **benchmark or secondary validation stage** rather than as something run on every generated candidate.

The pipeline should also consider the **evaluatability of a candidate**. Some designs may be theoretically interesting but extremely difficult to verify experimentally or computationally.

This suggests another useful score:

> **Evaluatability / verification feasibility**

A candidate that is slightly less promising scientifically but substantially easier to validate may be preferable to a highly speculative candidate that cannot realistically be tested.

---

# 6. Stage 5 — Candidate Ranking & Verification

The final candidates could be ranked using multiple dimensions rather than a single score.

For example:

**Candidate Score =**

- Evidence strength
- Mechanistic plausibility
- Novelty
- Predicted functional performance
- Computational confidence
- Experimental feasibility
- Evaluatability
- Availability of known starting materials/proteins

Known proteins with established behavior could also serve as **positive controls / benchmark cases**.

For example, if the system is given a problem for which the correct design is already well established, the pipeline should be able to recover it. This provides a way to test whether the agentic workflow actually works before applying it to a genuinely novel design problem.

---

# 7. Important Architectural Question: Skills vs. Specialized Agents

The team discussed two possible architectures.

### Option A — One orchestrator + skills

A central LLM would move through a sequence such as:

**Problem formulation → literature → candidate generation → simulation → evaluation**

Each step would be implemented as a reusable skill.

### Option B — Multi-agent architecture

A central orchestrator would delegate work to specialized agents:

- **Problem-formulation agent**
- **Literature-research agents**
- **Protein-design agent**
- **Simulation/evaluation agent**
- **Evidence/verification agent**

The discussion leaned toward the second approach because different parts of the problem require different expertise, tools, environments, and persistent context.

A particularly important concern was whether one orchestrator could maintain enough context to coordinate every subproblem effectively. Specialized agents could instead work continuously on their own portions of the problem and return structured outputs to the orchestrator.

---

# 8. Proposed Team Architecture

Rather than strictly separating everyone into isolated projects, the team should work on **interconnected modules** with clearly defined interfaces.

Possible groups:

### Team A — Problem Decomposition / Orchestration

Responsible for:

- Defining the general input/output interface
- Designing the recursive expert-LLM interaction
- Decomposing scientific problems
- Coordinating specialized agents
- Defining how outputs move between stages

### Team B — Literature & Evidence

Responsible for:

- Literature-search agent(s)
- Candidate discovery
- Evidence extraction
- Citation tracking
- Mechanism identification
- Connecting papers to candidate proteins/designs

### Team C — Protein Representation & Candidate Generation

Responsible for:

- Protein sequence datasets
- ESM/other protein embeddings
- Clustering known protein families
- Identifying relevant sequence/structural neighborhoods
- Generating candidate starting points

### Team D — Evaluation & Simulation

Responsible for:

- Defining evaluation metrics
- Investigating feasible simulations
- Benchmarking computational predictions
- Evaluating structural/functional plausibility
- Developing a candidate-ranking framework

The exact division can remain flexible, but **the interfaces between teams need to be defined early**.

---

# 9. Shared Infrastructure

The team discussed having everyone work through a shared repository and potentially sharing agent outputs, prompts, JSON files, literature results, and intermediate artifacts.

Each team should produce a short specification describing:

1. What their agent receives as input
2. What it does
3. What tools/data it requires
4. What it outputs
5. The output format
6. How another agent consumes that output

This is likely more important than simply dividing the work by topic.

The project should be designed around the **glue between components**, not just the individual components themselves.

---

# 10. Potential Final Deliverable

The strongest framing discussed was:

> **A reusable agentic framework for solving complex scientific/protein-design problems through iterative problem decomposition, literature-grounded hypothesis generation, candidate generation, computational evaluation, and verification.**

The wavelength/RF-responsive protein serves as the primary demonstration problem.

The final system could look conceptually like:

**Scientist**

↓  

**Scientific Design Question**

↓

**Problem-Decomposition Agent**

↓

**Human Expert Validation**

↓

**Multiple Specialized Research Agents**

↓

**Evidence + Candidate Database**

↓

**Candidate Generation**

↓

**Computational Evaluation / Simulation**

↓

**Candidate Ranking**

↓

**Verification / Experimental Recommendation**

↓

**Final Candidate Designs**

---

# 11. Possible Additional Deliverable

One team member proposed going beyond identifying a candidate protein and producing a more complete construct.

For example, once a promising protein is identified, the system could potentially design the surrounding components required for a usable experimental construct, such as localization tags or other supporting components.

This would make the output closer to:

> **“Here is an experimentally actionable construct you could order,”**

rather than simply:

> **“Here is a promising protein sequence.”**

This should probably remain a **stretch goal**, because the core agentic pipeline is already substantial.

---

# 12. Key Risks / Open Questions

Several unresolved questions came up that should be addressed before implementation:

### Data availability

There may not be enough labeled data for RF/wavelength-responsive proteins to train a highly reliable predictive model.

Therefore, the system should not assume that supervised learning alone can solve the problem.

### Simulation cost

Full molecular-dynamics or other high-fidelity simulations may be too expensive to execute repeatedly inside an agent loop.

### Verification

Some generated designs may be extremely difficult to experimentally validate.

The pipeline therefore needs to account for **verification feasibility**, not just predicted performance.

### Agent coordination

It remains unclear how much autonomy should be given to the orchestrator versus specialized agents.

### Generalization

The team needs to determine whether the system genuinely solves a general class of scientific design problems or merely works for the selected protein example.

---

# 13. Recommended Project Framing

The project should therefore be framed at **two levels**:

### General scientific contribution

> Build an agentic framework that converts high-level scientific design questions into evidence-grounded, computationally evaluable candidate solutions.

### Demonstration problem

> Use the design of a wavelength-responsive protein as a difficult test case for the framework.

This framing gives the project a stronger research story. Even if the final protein candidates are not experimentally validated during the project, the team can still demonstrate that the system successfully:

1. Decomposes the problem.
2. Identifies relevant mechanisms.
3. Retrieves and synthesizes the relevant literature.
4. Generates plausible candidates.
5. Evaluates candidates using computational evidence.
6. Ranks candidates according to multiple criteria.
7. Produces an experimentally actionable shortlist.

---

# 14. Immediate Next Steps

1. **Agree on the abstract problem definition.**
2. Define the exact input/output of the overall system.
3. Decide whether the architecture will be primarily **multi-agent + orchestrator** or a single agent with specialized skills.
4. Break the pipeline into 3–4 concrete modules.
5. Have each team write a short agent specification.
6. Investigate available protein databases, ESM/embedding tools, and simulation tools.
7. Define a benchmark problem where the correct/known answer already exists.
8. Define evaluation criteria based on the competition/judging rubric.
9. Build the literature component first, since it establishes the evidence layer and candidate space.
10. Establish the interfaces between modules before implementing each module independently.

## Working Thesis

**The central idea is not simply to use an LLM to design a protein. It is to build an agentic scientific reasoning loop in which an LLM converts an underspecified design goal into structured hypotheses, experts curate those hypotheses, specialized agents gather evidence and generate candidates, computational tools evaluate them, and the system iteratively converges toward experimentally actionable solutions.**

The RF/wavelength-responsive protein is the test case through which we demonstrate that workflow.