litkb -- concept -> corpus -> typed evidence
============================================

Mines PubMed Central and bioRxiv full text into EvidenceItem records for the
ideation layer of docs/PRD-framework.md.

Exposed as nine deterministic subcommands so an agent can drive the pipeline,
inspect any stage, and retry one step without rerunning the rest.  All
judgement -- what the mechanism classes are, what a span claims, how well
supported it is -- belongs to the calling agent.  This tool searches, greps,
parses and fetches citations; it never invents a claim or a support level.

Agent-facing usage guidance lives in .claude/skills/litkb/SKILL.md.

paperclip_kb.py is the original single-shot script.  It is superseded by this
package and kept only for reference.


REQUIREMENTS
------------

  * Python >= 3.10.  This package and `paperclip` both use `str | None`
    syntax; a 3.9 interpreter fails at import, not at runtime.
  * `paperclip` on PATH and authenticated:

        paperclip config          # want: Auth: OK

    If it reports an auth error, run `paperclip login` (interactive browser).

No API keys.  The planner that used to call Claude is gone -- the agent plans.


PIPELINE
--------

    plan-template -> (agent writes plan) -> plan-validate --probe
                                                  |
                                                  v
              search -> extract -> evidence -> label -> validate -> report
                                                 ^
                                        (agent writes labels)

Run from this directory as `python -m litkb <command>`.  Every command writes
JSON to stdout, or to -o FILE.

    python -m litkb plan-template -o rfp_plan.json
    python -m litkb plan-validate rfp_plan.json --probe --sources pmc,biorxiv
    python -m litkb search        rfp_plan.json -n 20 -o rfp_search.json
    python -m litkb extract       rfp_plan.json rfp_search.json -o rfp_hits.json
    python -m litkb evidence      rfp_hits.json -o rfp_evidence.json
    python -m litkb label         rfp_evidence.json labels.json
    python -m litkb validate      rfp_evidence.json
    python -m litkb registry-check rfp_plan.json --registry ../registry/evaluators.json
    python -m litkb report        rfp_evidence.json --search rfp_search.json \
                                  -o knowledge_base_rfp.txt


LAYOUT
------

    litkb/paperclip.py   subprocess wrapper + output parsing
    litkb/patterns.py    fixed structural patterns (sequence, accession, mutation)
    litkb/contracts.py   plan + EvidenceItem schemas and validation
    litkb/report.py      human-readable rendering
    litkb/cli.py         the nine subcommands

    rfp_plan.json        worked example: the RF-responsive-protein concept


HOW IT MAPS TO THE FRAMEWORK
----------------------------

  * The unit of coverage is the mechanism class, not the phrase.  §8 wants
    >=6 classes; `search` reports coverage.meets_framework_minimum.
  * Output is typed EvidenceItem[] per §6.2 of PRD-(outdated).md, so
    Route.evidence_refs resolves to real records with citations.
  * support ∈ established|contested|speculative is mandatory before an item
    reaches L1; `validate` enforces it.  Nothing speculative may become a
    hard constraint.
  * Zero-yield phrases, empty classes and planner exclusions are recorded as
    rejections and rendered in the report -- rejection is a first-class output.
  * registry-check implements the §77 inversion: classes nothing can evaluate
    come back requires_new_evaluator rather than silently competing.


PAPERCLIP BEHAVIOUR THIS PACKAGE WORKS AROUND
---------------------------------------------

Verified against paperclip 0.7.36.  Re-check if that version moves.

  * `search` has no --tag and does not accumulate; each search returns its own
    set, so every set ID is carried separately.
  * `merge` is broken -- it resolves only its first argument and reports
    "not found" for every later one, even for sets `results --list` shows.
    That is why there is no union step.
  * Exit code 1 means "no matches", as in grep.  Only codes >= 2 are failures.
  * The engine supports lookaround, which is what lets the accession patterns
    exclude DOI context -- 10.1039/C5CP06731F otherwise reads as "P06731".
  * -i is applied per category.  The amino-acid classes are case-significant:
    [ACDEFGHIKLMNPQRSTVWY]{25,} under -i matches ordinary lowercase prose.


KNOWN LIMITS
------------

  * paperclip truncates long per-document hit lists; provenance.truncated_after
    records how many were dropped.
  * Hits are paragraph-level, so citation URLs carry no #L line anchor.
  * PDB[ :]?[0-9][A-Za-z0-9]{3} still matches the software name "PDB2PQR".
  * registry-check has nothing to resolve against until an evaluator registry
    exists; registry/evaluators.json was removed in commit 945164f with the
    Tamarind integration.
