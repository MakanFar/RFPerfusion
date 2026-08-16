# Related work for RFPerfusion

Searched with Valency (arXiv + bioRxiv + PubMed, semantic) and alphaXiv. Grouped
against the PRD-framework stages rather than by topic, so each entry says what it
does to *your* design, not just what it is about.

Paperclip is a skill in this repo but its MCP is not connected to this session, so
nothing below came from full-text mining — abstracts and metadata only.

---

## 0. Read these five first

| Paper | Why it lands on your loop |
|---|---|
| [BioDesignBench — Kim & Romero 2026](https://doi.org/10.64898/2026.05.06.723381) | 76 expert-curated protein design tasks + human baselines. Finding: frontier agents **pick the right tools but evaluate shallowly** — narrow metric sets, no candidate comparison, premature termination. A forced-depth intervention (score every candidate on structure/interface/physics/affinity) closes most of the gap. This is your L4 and your "evaluator registry" thesis, measured. It is also a benchmark you can literally run. |
| [Meister, *Physical limits to magnetogenetics*, eLife 2016](https://arxiv.org/abs/1604.01359) | The canonical L1.5 kill: order-of-magnitude argument against conservation laws, discrepancies of 5–10 log units, published as a standalone rejection. This is PRD §8's "falsification kills ≥1 route on physical grounds, with citation" already written for the RF instance. Cite it as your worked example. |
| [Piraner et al., *Tunable thermal bioswitches for in vivo control of microbial therapeutics*, Nat Chem Biol 2017](https://pubmed.ncbi.nlm.nih.gov/27842069/) | The TlpA-family switch paper your README names as the held-out Tm calibration gate. Two orthogonal repressor families, thresholds across 32–46 °C, focused-ultrasound spatial activation. The 32–46 °C threshold series is the labelled set your `tm_regression_v2` evaluator needs. |
| [HLER: Human-in-the-Loop Economic Research](https://arxiv.org/abs/2603.07444) | Different domain, same inversion as your evaluator registry: constraining hypothesis generation by *what the available data can actually support* raises feasible-question rate from **41% → 87%**. The strongest quantitative evidence anyone has published for "the registry is an input to L1." |
| [PseudoBench: Measuring How Agentic Auto-Research Fuels Pseudoscience](https://www.alphaxiv.org/abs/2606.18060) | Your Risk table's top-line item — "ideation produces fluent, cited, impossible routes" — as a measured failure mode with a benchmark attached. |

---

## 1. Whole-loop analogues (objective → evidence → candidates → scores)

- [Robin: A multi-agent system for automating scientific discovery](https://arxiv.org/abs/2505.13400) — FutureHouse. Literature agents + data-analysis agents in a lab-in-the-loop; produced and validated ripasudil for dAMD. Closest published thing to your end-to-end claim, and it *did* the wet-lab close that you list as a non-goal — useful as the boundary marker for what you are and are not claiming.
- [MechAInistic: Reviewer-Supervised Multi-Agent LLM for Auditable Mechanistic Drug-Hypothesis Generation](https://pubmed.ncbi.nlm.nih.gov/42182411/) — an independently configured **Reviewer** agent scores a planning **Architect** at every stage against pre-specified rubrics and forces re-planning below threshold; all reasoning grounded in executable COBRApy runs, never model text. This is your "nothing fabricates a score" guardrail implemented as an architecture. Steal the rubric-threshold-replan pattern for L1.5.
- [BioDisco: Multi-agent hypothesis generation with dual-mode evidence, iterative feedback and temporal evaluation](https://arxiv.org/abs/2508.01285) — knowledge graph *plus* literature retrieval as two evidence modes, with temporal held-out evaluation (can it propose what was later discovered?). The temporal protocol is a cheap version of your Instance C ("does the loop recover the known answer?").
- [InternAgent: Building Closed-Loop System from Hypothesis to Verification](https://arxiv.org/abs/2505.16938) — 12 task domains, explicit human-feedback interface. Good prior art for your §5 human-in-the-loop table.
- [Toward Generalist Autonomous Research via Hypothesis-Tree Refinement](https://www.alphaxiv.org/abs/2606.11926) — hypotheses as a tree with lessons carried across branches. Relevant to your Portfolio Controller: it is the retire-and-reallocate problem framed as tree search.
- [Rethinking Scientific Discovery in the Agentic Era](https://www.alphaxiv.org/abs/2607.03863) — position paper arguing exactly your framing: AI4Science systems are fragmented tools and the missing product is the coordination layer. Useful for the pitch.
- [EvoScientist](https://www.alphaxiv.org/abs/2603.08127) / [EvoSci](https://www.alphaxiv.org/abs/2605.24018) / [AutoResearchClaw](https://www.alphaxiv.org/abs/2605.20025) — the current crop of multi-role evolving-agent scientists. Skim for role decompositions to compare against your L1–L4.
- [Evidence-Grounded Frontier Mapping and Agentic Hypothesis Generation in Nanomedicine](https://www.alphaxiv.org/abs/2605.18144) — same shape as yours in a fragmented, multi-physics domain.
- [Multi-Persona Debate System for hypothesis generation](https://arxiv.org/abs/2605.23917) — literature snapshots of ≤500 papers, corpus-induced personas, citation-aware three-round debate, temporally controlled evaluation on battery materials. The persona-induction-from-corpus trick is a plausible upgrade for your per-shard mining agents.

## 2. Protein-design agents (your L3 fan-out and proto-tools layer)

- [AutoBinder Agent: An MCP-Based Agent for End-to-End Protein Binder Design](https://arxiv.org/abs/2602.00019) — LLM + **Model Context Protocol** coordinating MaSIF → Rosetta → ProteinMPNN → AlphaFold3, explicitly motivated by reproducibility and auditability over script-based pipelines. Architecturally the nearest neighbour to your `.mcp.json` + `proto-tools` design; worth citing as prior art for the MCP choice.
- [Protein Design with Agent Rosetta: A Case Study for Specialized Scientific Agents](https://www.alphaxiv.org/abs/2603.15952) — the specialist-vs-generalist agent question for protein design specifically.
- [ProtoCycle: Reflective Tool-Augmented Planning for Text-Guided Protein Design](https://www.alphaxiv.org/abs/2604.16896) — natural-language functional requirement → tool plan → reflect. This is your L2 (spec generation) as a standalone paper; read it before you instrument spec edit distance.
- [MAESD: Unified Multi-Agent Evolutionary Framework for Protein Sequence Design](https://pubmed.ncbi.nlm.nih.gov/41824966/) — semantic-to-biological translation module (NL → actionable design constraints) + generate/validate evolutionary loop over ProGen2/ProteinMPNN. Direct analogue of your `design-brief-007` → cascade split.
- [Self-evolving AI agents for protein discovery and directed evolution (VenusFactory2)](https://www.alphaxiv.org/abs/2603.27303) — automated orchestration of protein algorithms; the "general agents are insufficient in complex domain projects" claim is your Skills-vs-generalist argument.
- [PRAXIS: Case-distilled and code-verified AI agents for biological research](https://www.alphaxiv.org/abs/2605.23169) — object validation and methodological suitability checks; relevant to `litkb bind`'s schema-check-is-not-a-run caveat.

## 3. Falsification, calibration, and rejection-as-output (L1.5 and §6)

Your two hardest-to-defend claims are "rejection is a first-class output" and "every
score carries calibrated uncertainty." This is the literature that either supports or
attacks them.

- [SoundnessBench: Can Your AI Scientist Really Tell Good Research Ideas from Bad Ones?](https://www.alphaxiv.org/abs/2605.30329) — tests discrimination, not generation. Your L1.5 is a discriminator; this is how to score it.
- [TRACES: A Benchmark for Epistemic Reliability in Scientific Reasoning by LLMs](https://www.alphaxiv.org/abs/2608.11415) — explicitly about domains "where no downstream verifier exists," which is precisely your RF/ion-channel instance B.
- [The Calibration Turn in AI-Assisted Research: Evidence-Licensed Claims](https://www.alphaxiv.org/abs/2606.31273) — a conceptual framework for "what claim is this evidence licensed to support." Reads as an academic statement of your §6 rule: *no claimed design margin finer than the evaluator's measured error*.
- [Autonomous Research Agents: A Survey of AI Scientists and the Verification Gap](https://www.alphaxiv.org/abs/2608.05179) — the survey to cite when you justify the mandatory human gate.
- [EviGraph: Evidence-Guided Autonomous Research Agents](https://www.alphaxiv.org/abs/2608.04738) — targets unsupported claims and inconsistency between question, experiment, and conclusion. Same failure your `evidence_status: discovery_only_unverified` flag is defending against.
- [An AI Scientist that Doesn't Drift: Taste, Structure, and Falsifiable Findings](https://www.alphaxiv.org/abs/2608.07542) — loops drift toward local metric refinement instead of testing the hypothesis. Direct warning for your Portfolio Controller's reallocation rule.
- [One Reflection Is Not Enough: Multi-Hypothesis Failure Attribution](https://www.alphaxiv.org/abs/2606.31478) — when a gate fails, which upstream decision caused it. You will need this once L4 starts retiring routes.

## 4. Domain — the thermal / TlpA instance (Instance A)

- [Piraner et al. 2017, Tunable thermal bioswitches](https://pubmed.ncbi.nlm.nih.gov/27842069/) — see §0. Your calibration set.
- [Genetically Encoded Protein Thermometer (HEAT / FeverSense), Adv Sci 2021](https://pubmed.ncbi.nlm.nih.gov/34496151/) — **mutant coiled-coil temperature sensor fused to a synthetic transcription factor**, tuned to trigger across 37–40 °C, validated in vivo to insulin release. Mechanistically the same architecture as your SWIR/TlpA switch, in mammalian cells, with a narrower and more useful threshold window. If you need a second scaffold for the same route, this is it.
- [Modular engineering of thermoresponsive allosteric proteins, Nat Chem Biol 2026](https://pubmed.ncbi.nlm.nih.gov/41680487/) ([preprint](https://doi.org/10.1101/2025.05.02.651844)) — LOV2-insertion strategy makes *arbitrary* proteins thermoswitchable in 37–41 °C, incl. CRISPR-Cas editors; also reports chemoreceptor domains as an alternative thermosensing module. This generalizes your scaffold choice from "TlpA" to "insertion site selection," which is a much better L2 mutable-space definition.
- [Thermally Controlled State Switches for Engineered Macrophages, ACS Synth Biol 2025 (Shapiro lab)](https://pubmed.ncbi.nlm.nih.gov/41075299/) — thermal stimulus → *stable* transcriptional latch, 14 days in vivo. Relevant if your actuation is transient but the desired output is not.
- [Robust network topologies for temperature-inducible bioswitches](https://pubmed.ncbi.nlm.nih.gov/35606858/) — exhaustive search of 3-node topologies for Off-On / On-Off / Off-On-Off thermal switching. A circuit-level route class your L1 ideation probably does not currently enumerate.
- [Reverse Engineering of a Thermosensing Regulator Switch (DesK DOTs)](https://pubmed.ncbi.nlm.nih.gov/30738600/) — thermosensing decomposed into three transferable "determinants of thermodetection," rebuilt on a poly-valine scaffold. A worked mechanism→modular-part decomposition, i.e. your L2 done by hand.

## 5. Domain — the RF instance (Instance B), including the contested-evidence test case

The RF branch is valuable to you *precisely because* the literature is contested. It is
a live test of the `established | contested | speculative` field.

- [Huang, Delikanli, Zeng, Ferkey & Pralle, *Remote control of ion channels and neurons through magnetic-field heating of nanoparticles*, Nat Nanotech 2010](https://pubmed.ncbi.nlm.nih.gov/20581833/) — the founding RF→nanoparticle→TRPV1 result. `established` for the nanoparticle-mediated path.
- [Meister 2016, Physical limits to magnetogenetics](https://arxiv.org/abs/1604.01359) — the kill. `speculative`/dead for the ferritin-without-nanoparticle path.
- [Barbic, *Possible magneto-mechanical and magneto-thermal mechanisms*, eLife 2019](https://pubmed.ncbi.nlm.nih.gov/31373554/) — the rebuttal arguing Meister's spin-configuration assumptions were too restrictive. Together with Meister this is your `contested` exemplar, and a good regression test: does L1.5 correctly refuse to promote either to a hard constraint?
- [Hernández-Morales et al., *Electrophysiological Mechanisms and Validation of Ferritin-Based Magnetogenetics (FeRIC)*, J Neurosci 2024](https://pubmed.ncbi.nlm.nih.gov/38777598/) — solved the RF/patch-clamp interference problem and got direct Ephys evidence; effects are real but slow, moderate, and biochemical (ROS/oxidized lipids), not instantaneous gating. The nuance your evidence layer has to be able to represent.
- [Wood & Karipidis, *Radiofrequency Fields and Calcium Movements Into and Out of Cells*, Radiat Res 2021](https://pubmed.ncbi.nlm.nih.gov/33206197/) — 50 years of VGCC-sensitivity claims reviewed and rejected on induced-current grounds vs ICNIRP limits. Feeds directly into your `kill_criterion` template about SAR limits.
- [Sebesta et al., *Sub-second multi-channel magnetic control of select neural circuits in behaving flies*](https://doi.org/10.1101/2021.03.15.435264) — rate-sensitive TRPA1-A + tuned nanoparticles gives sub-second, *frequency-multiplexed* actuation. The strongest existing answer to "what would a working RF-actuated switch look like."
- [High-Power Dual-Channel Field Chamber for High-Frequency Magnetic Neuromodulation](https://arxiv.org/abs/2511.00745) — 50 kHz / 550 kHz, 88 / 12.5 mT, measured heating rates. Real numbers for your analytic thermal budget.
- [Non-thermal effects of radiofrequency electromagnetic fields](https://pubmed.ncbi.nlm.nih.gov/32778682/) — 13.56 MHz; models rectification to ~1 µV DC across a channel. A non-thermal route class, weakly supported — good `speculative` fodder.

## 6. Domain — the >1500 nm / SWIR framing from the original team discussion

- [Near-Infrared-II Chemo-Optogenetics for Deep-Brain Stimulation (HaloNeu)](https://doi.org/10.64898/2026.05.13.724823) — cpHaloTag fused to TRPV1 + covalently conjugated NIR-II photothermal nanotransducers; 1064 nm, 1.0 cm depth at ~60 mW/cm², 5 cm at the safe exposure limit, stable >2 months in vivo. **This is the SWIR-actuated thermal switch, built.** Read it before you re-derive the route; then decide whether your contribution is the loop recovering it (Instance C) rather than the molecule.
- [MagRed: A red light-responsive photoswitch for deep tissue optogenetics, Nat Biotech 2022](https://pubmed.ncbi.nlm.nih.gov/35697806/) — bacterial phytochrome + biliverdin + Affibody-selected photostate-specific binder. The *evolved-binder-against-a-conformational-state* trick is a design pattern your generation stage could adopt.
- [NIR-Light Activatable Nanoparticles for Deep-Tissue-Penetrating Wireless Optogenetics](https://pubmed.ncbi.nlm.nih.gov/30633858/) — review splitting the field into upconversion (NIR→visible→opsin) vs photothermal (NIR→heat→thermosensitive protein). That is a clean top-level `mechanism_class` partition for L1.
- [Near-infrared up-conversion optogenetics](https://pubmed.ncbi.nlm.nih.gov/26552717/) — includes the honest energy-efficiency caveat, which is the quantitative kill criterion for the upconversion branch.
- [Near-Infrared Fluorescent Proteins: Multiplexing and Optogenetics across Scales](https://pubmed.ncbi.nlm.nih.gov/30041828/) — the phytochrome/biliverdin scaffold family, for starting-material availability scoring.

## 7. Sequence → property evaluators (Stage 2.1, the ESM/wavelength thread)

Your team doc names FLIP/RhoMax and VPOD. Here is the surrounding chain, and one
result that already closed your loop.

- [Takaramoto et al. 2025, *Functional characterization of red-shifted rhodopsin channels from giant viruses explored by a machine-learning model*](https://doi.org/10.1101/2025.09.16.676488) — elastic-net trained on 1,163 λmax measurements → predicted red-shifted candidates → **experimentally characterized ChR024 at ~578 nm**, second only to Chrimson. This is the full ML-shortlist-to-validated-protein loop in your exact demo domain, done by a wet lab. Best available positive control for Instance C.
- [Karasuyama et al., *Understanding Colour Tuning Rules and Predicting Absorption Wavelengths of Microbial Rhodopsins*, Sci Rep 2018](https://pubmed.ncbi.nlm.nih.gov/30349075/) — 796-protein database, statistical model, two new colour-shift residues. The precursor to the above.
- [RhoMax: Computational Prediction of Rhodopsin Absorption Maxima Using Geometric Deep Learning](https://pubmed.ncbi.nlm.nih.gov/38829021/) — AlphaFold2 structures + geometric DL, 0.03 eV on over half of the test set. Note the "over half" — a natural **applicability domain** boundary, exactly the kind of thing your Evaluator record's `known_reliability` and applicability filter are for.
- [VPOD: Discovering genotype-phenotype relationships with ML and the Visual Physiology Opsin Database](https://pubmed.ncbi.nlm.nih.gov/39460934/) — 864 genotype/λmax pairs from 73 publications.
- [Frazer & Oakley 2026, *Accessible and robust ML approaches to improve the opsin genotype-phenotype map* (OPTICS)](https://pubmed.ncbi.nlm.nih.gov/42301139/) ([preprint](https://doi.org/10.1101/2025.08.22.671864)) — **read this for the calibration lesson**: they introduce Phylogenetically Weighted Cross-Validation because ordinary CV *overestimates* performance on non-independent homologous sequences, and they find physicochemical encodings competitive with protein language models while staying interpretable. Two direct hits on your §6: naive held-out benchmarks will inflate your `known_reliability`, and ESM embeddings are not automatically the right representation. Their Mine-N-Match pipeline (published sequences → compiled in-vivo λmax) is also basically `litkb` for one property.
- [Yang, Wu, Bedbrook & Arnold, *Learned protein embeddings for machine learning*](https://pubmed.ncbi.nlm.nih.gov/29584811/) — the foundational case that embeddings suffice without alignments or structures.
- [Ten quick tips for sequence-based prediction of protein properties using ML](https://pubmed.ncbi.nlm.nih.gov/36454728/) — a checklist for the evaluator registry's `known_reliability` field. Short; make it required reading for whoever writes registry entries.

---

## Three things the search suggests you change

1. **Your L1.5 exemplar already exists in print.** Meister 2016 + Barbic 2019 + Wood & Karipidis 2021 give you an established / contested / killed triple on a single mechanism class, with numbers. Hardcode that trio as the L1.5 regression test rather than inventing one.
2. **BioDesignBench says the gap is evaluation depth, not tool choice.** Your PRD spends most of its architecture budget on ideation and specification. The measured failure of comparable systems is downstream of that — agents run the right tool once and stop. If you want the Target success criteria to mean something, instrument *metrics-per-candidate* and *candidates-compared*, not just spec edit distance.
3. **Instance C may already be sitting in §7.** Takaramoto 2025 (ML → ChR024) and the HaloNeu NIR-II switch are both published, recent, and squarely in your demo domain. Either is a better "solved problem with a published answer" than something invented, and both postdate enough of the training corpus to make recovery non-trivial.
