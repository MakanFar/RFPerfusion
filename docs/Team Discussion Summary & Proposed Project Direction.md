# Team Discussion Summary & Proposed Project Direction

## Core Problem

The team discussed using an **AI-driven, multi-agent pipeline for protein design**, with the initial motivating example being the design of a protein that responds to a particular physical stimulus—specifically, a protein with sensitivity at wavelengths greater than ~1500 nm.

The important realization was that the project should **not be framed only as “design this one protein.”** The more general and potentially impactful goal is to build a reusable system that takes a complex scientific design problem, decomposes it into tractable research and engineering questions, searches the literature for candidate mechanisms, evaluates possible designs, and iteratively narrows the solution space.

The RF/wavelength-responsive protein would therefore serve as a **challenging test case for the general protein-design pipeline**, rather than necessarily being the sole deliverable.

## Proposed High-Level Pipeline

### Input: Scientific Design Goal

A researcher begins with a high-level question such as:

> *“How can we design a protein that responds to wavelengths greater than 1500 nm?”*

Rather than immediately asking an LLM to design the protein, the system first helps **formalize and decompose the problem**.

### Stage 0 — Problem Formulation & Decomposition + Literature Research Agent

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

The output of this stage should decompose the protein design into distinct subtasks curated and validated by the domain expert. Each task can be given to one of the Stage 2 agents.

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

Not sure if relevant, but a curation step should be done here by a single agent to see whether all proposals are consistent for the design of a single protein - can we make sure that we’re not trying to design physically impossible proteins - maybe this is relevant at the end of step 3

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

At this stage, we need to figure out what is the input layer to the simulation, so we shape the ouput of this stage to slot into it

### Stage 2 — Computational Evaluation / Simulation

The next stage evaluates whether the proposed candidates are computationally plausible.

The team discussed several possible levels of evaluation:

#### Protein-level evaluation

Depending on the proposed mechanism:

- Structure prediction
- Protein language-model representations
- Sequence/structure similarity
- Functional-property prediction
- Optical-property prediction

#### Stage 2.1 Establishment of Structure - Feature relationship space (JRP)

- Using FBbase as a starting protein space, embed proteins with ESM and look to see if a relationship with excitation wavelength can be had
  - Approach A: UMAP protein embeddings and see if they cluster by wavelength
  - Approach B: Foldseek cluster protein structures
  - Approach C: Focus just on 20A around the chromophore
- Action items
  - Create a skill that takes new data an appends it into a similar format

Protein property datasets:

- <https://flip.protein.properties/> (RhoMax for rhodopsin wavelength)
- VPOD opsin data: <https://github.com/VisualPhysiologyDB/visual-physiology-opsin-db>

#### Simulation

Where feasible, simulations could be used to test whether a proposed mechanism behaves as expected.

However, the team noted that expensive molecular-dynamics simulations may be too slow to place directly inside an iterative agent loop.

Therefore, simulation may initially function better as a **benchmark or secondary validation stage** rather than as something run on every generated candidate.

The pipeline should also consider the **evaluatability of a candidate**. Some designs may be theoretically interesting but extremely difficult to verify experimentally or computationally.

This suggests another useful score:

> ***Evaluatability / verification feasibility***

A candidate that is slightly less promising scientifically but substantially easier to validate may be preferable to a highly speculative candidate that cannot realistically be tested.

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

- LigandMPNN for retinal transition for opsin, likelihood of structure “binding” cis/trans states as a proxy for transitions between closed and open states?

For example, if the system is given a problem for which the correct design is already well established, the pipeline should be able to recover it. This provides a way to test whether the agentic workflow actually works before applying it to a genuinely novel design problem.

## Stage 3 — Proto-based build.

Given a designed light-responsive protein, create a genetic architecture that is likely to create a vesicle around it.

## Proposed Team Architecture

Rather than strictly separating everyone into isolated projects, the team should work on **interconnected modules** with clearly defined interfaces.

Possible groups:

### Team A — Problem Decomposition / Orchestration + Literature & Evidence + Candidate Generation

Responsible for:

- Defining the general input/output interface
- Designing the recursive expert-LLM interaction
- Decomposing scientific problems
- Coordinating specialized agents
- Defining how outputs move between stages

- Literature-search agent(s)
- Candidate discovery
- Evidence extraction
- Citation tracking
- Mechanism identification
- Connecting papers to candidate proteins/designs

Literature search setup:

- Take one topic per agent delivered by previous output and use an LLM to turn into sentence shards that can be regex-ed to identify correct papers or searched in full text papers through paperclip. Additionally extract sentences that have to do with why that sequence likely produce said mechanism to further refine search
- For each paper, extract relevant FASTA sequence tied to the mechanism, and the full protein it belongs to?
- Identify references that are commonly cited in the papers but are not available as full text in paper clip. Read those paper’s abstracts for extra information.

### Team B — Protein Representation & Evaluation & Simulation

Responsible for:

- Protein sequence datasets
- ESM/other protein embeddings
- Clustering known protein families
- Identifying relevant sequence/structural neighborhoods
- Generating candidate starting points

- Defining evaluation metrics
- Investigating feasible simulations
- Benchmarking computational predictions
- Evaluating structural/functional plausibility
- Developing a candidate-ranking framework

The exact division can remain flexible, but **the interfaces between teams need to be defined early**.

### Shared Infrastructure

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

## Potential Final Deliverable

The strongest framing discussed was:

> ***A reusable agentic framework for solving complex scientific/protein-design problems through iterative problem decomposition, literature-grounded hypothesis generation, candidate generation, computational evaluation, and verification.***

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

## Recommended Project Framing

The project should therefore be framed at **two levels**:

### General scientific contribution

> *Build an agentic framework that converts high-level scientific design questions into evidence-grounded, computationally evaluable candidate solutions.*

### Demonstration problem

> *Use the design of a wavelength-responsive protein as a difficult test case for the framework.*

This framing gives the project a stronger research story. Even if the final protein candidates are not experimentally validated during the project, the team can still demonstrate that the system successfully:

1. Decomposes the problem.
2. Identifies relevant mechanisms.
3. Retrieves and synthesizes the relevant literature.
4. Generates plausible candidates.
5. Evaluates candidates using computational evidence.
6. Ranks candidates according to multiple criteria.
7. Produces an experimentally actionable shortlist.

### Working Thesis

**The central idea is not simply to use an LLM to design a protein. It is to build an agentic scientific reasoning loop in which an LLM converts an underspecified design goal into structured hypotheses, experts curate those hypotheses, specialized agents gather evidence and generate candidates, computational tools evaluate them, and the system iteratively converges toward experimentally actionable solutions.**

The RF/wavelength-responsive protein is the test case through which we demonstrate that workflow.
