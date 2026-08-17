"""Typed artifacts. The framework's §4 rule -- "agents communicate only
through typed artifacts, no agent reads another agent's prose" -- is enforced
here.

Every judgement field on an EvidenceItem starts null. This module builds
drafts and validates completions; it never guesses a claim or a support level.
That work belongs to the agent, via `litkb label`.
"""

import re
from datetime import datetime, timezone

from . import proto
from .vocabulary import UnknownTerm

SUPPORT_LEVELS = ("established", "contested", "speculative")
CLAIM_TYPES = ("mechanism", "quantity", "scaffold", "failure_mode", "negative_result")
EVIDENCE_KINDS = ("experimental", "computational", "review", "theoretical")

# Filled by `litkb label`, never by this tool.
JUDGEMENT_FIELDS = ("claim", "claim_type", "support", "evidence_kind", "confidence")


class ContractError(ValueError):
    pass


def validate_plan(plan):
    """A plan is mechanism classes, not a flat phrase list. Coverage in the
    framework is measured over mechanism classes (§8: >=6), so the class is the
    unit here and per-class yield is reportable."""
    errors = []
    if not plan.get("objective"):
        errors.append("plan.objective is required (the free-text concept)")
    if not plan.get("slug"):
        errors.append("plan.slug is required")

    classes = plan.get("mechanism_classes")
    if not isinstance(classes, list) or not classes:
        errors.append("plan.mechanism_classes must be a non-empty list")
        return errors

    seen = set()
    for i, c in enumerate(classes):
        where = f"mechanism_classes[{i}]"
        cid = c.get("id")
        if not cid:
            errors.append(f"{where}.id is required")
        elif cid in seen:
            errors.append(f"{where}.id '{cid}' is duplicated")
        else:
            seen.add(cid)
        if not c.get("question"):
            errors.append(f"{where}.question is required -- what this class is asked to answer")
        if not c.get("search_phrases"):
            errors.append(f"{where}.search_phrases must be a non-empty list")
        if not c.get("mechanism_patterns"):
            errors.append(f"{where}.mechanism_patterns must be a non-empty list")
    return errors


# design-brief-007 hands off a FLAT plan (exactly three keys:
# search_phrases/mechanism_patterns/notes), already validated against
# paperclip_kb.py's own `validate_plan` -- see
# .claude/skills/design-brief-007/references/handoff-contract.md. This is
# the same three-key check mirrored here rather than imported, so litkb has
# no import dependency on the sibling script; a plan that fails it names
# exactly which key is missing, per that handoff contract.
BRIEF_PLAN_KEYS = ("search_phrases", "mechanism_patterns", "notes")


def validate_brief_plan(plan):
    if not isinstance(plan, dict):
        return ["brief plan must be a JSON object"]
    missing = [k for k in BRIEF_PLAN_KEYS if k not in plan]
    if missing:
        return [f"brief plan is missing required key(s): {', '.join(missing)}"]
    errors = []
    for key in ("search_phrases", "mechanism_patterns"):
        values = plan[key]
        if not isinstance(values, list) or not values:
            errors.append(f"brief plan.{key} must be a non-empty list")
    if not isinstance(plan.get("notes"), str):
        errors.append("brief plan.notes must be a string")
    return errors


def adopt_brief_plan(plan, objective, slug, source_path):
    """Lift a design-brief's flat plan (search_phrases/mechanism_patterns/
    notes) into litkb's class-structured plan, honestly rather than by
    inventing structure the brief never had.

    A flat plan carries no mechanism-class decomposition -- design-brief-007
    never shards a mining plan by mechanism -- so it becomes exactly ONE
    class here. `search_mode` is set to "exact", not "semantic": the brief's
    phrases were written for paperclip_kb.py's own planner, which the
    handoff contract says matches them as strict literals, so switching them
    to hybrid/semantic ranking here would silently change what they search
    against. `notes` is carried into `exclusions` verbatim (as a single
    entry recording it came from the brief) rather than discarded, so the
    brief planner's own reasoning about what it left out is not lost.

    NOTE: a one-class plan built this way will report
    `coverage.meets_framework_minimum: false` the moment it reaches
    `litkb search` -- the framework wants >=6 mechanism classes (see
    `validate_plan`'s docstring above). That is ACCURATE, not a bug: a flat
    brief plan genuinely carries one class's worth of decomposition, and
    this function must not manufacture a false >=6 split just to make the
    coverage gate pass.
    """
    errors = validate_brief_plan(plan)
    if errors:
        raise ContractError("; ".join(errors))

    class_id = re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_") or "brief"
    notes = plan.get("notes", "").strip()
    question = notes or f"What does the literature say about {objective}?"

    return {
        "objective": objective,
        "slug": slug,
        "search_mode": "exact",
        "mechanism_classes": [{
            "id": class_id,
            "question": question,
            "candidate_evaluators": [],
            "search_phrases": list(plan["search_phrases"]),
            "mechanism_patterns": list(plan["mechanism_patterns"]),
        }],
        "exclusions": [{
            "excluded": notes or "(the brief plan's notes field was empty)",
            "reason": "carried verbatim from the design-brief plan's `notes` "
                      "field by `plan-adopt`, so the planner's reasoning is "
                      "not lost",
        }],
        "provenance": {
            "adopted_from": "brief_plan",
            "source_path": str(source_path),
        },
    }


def build_manifest(*, slug, objective, search=None, screen=None, dig=None,
                    artifacts=None, evidence=None, paths=None):
    """Assemble manifest_<slug>.json from whatever stage outputs exist for
    this run. Every stage argument is optional -- `litkb manifest` must
    produce a manifest describing what exists even from a partial run, per
    the mine-literature-from-concept output contract.

    `evidence_status` is always the literal string
    "discovery_only_unverified" -- non-negotiable, and every code path
    through this function sets it the same way, with nothing able to
    override it. A litkb line proves only that a reader (`paperclip map`)
    returned it from a saved result set; it does not prove the claim it
    carries is faithful to its source, entailed by it, or generalisable
    beyond the paper's own experimental conditions. Everything assembled
    from this manifest -- the report, the bound artifacts, any shortlist a
    downstream agent builds -- inherits that status through the cascade
    (see .claude/skills/design-brief-007/references/handoff-contract.md and
    .claude/skills/mine-literature-from-concept/references/output-contract.md).

    `set_ids` lists every paperclip set ID litkb kept, one row per
    (mechanism class, phrase) pair -- not just one ID -- because the output
    contract's whole point is that a reader reopens THAT specific set to
    verify a candidate, and litkb runs many searches per plan.
    """
    set_ids = []
    if search:
        for c in search.get("classes", []):
            for s in c.get("sets", []):
                set_ids.append({"class_id": c["id"], "phrase": s["phrase"],
                                "set_id": s["set_id"], "n_papers": s.get("n_papers")})

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "slug": slug,
        "objective": objective,
        "evidence_status": "discovery_only_unverified",
        "sources": search.get("sources") if search else None,
        "n": search.get("n") if search else None,
        "set_ids": set_ids,
        "extracted_by": {
            "screen": screen.get("extracted_by") if screen else None,
            "dig": dig.get("extracted_by") if dig else None,
        },
        "artifact_paths": {k: v for k, v in (paths or {}).items() if v},
        "counts": {
            "papers_screened": len(screen["papers"]) if screen else None,
            "papers_flagged": len(screen["flagged"]) if screen else None,
            "failed_extractions": len(screen["failed"]) if screen else None,
            "artifacts_runnable": len(artifacts["artifacts"]) if artifacts else None,
            "artifacts_rejected": len(artifacts["rejections"]) if artifacts else None,
        },
    }


def draft_artifact(index, record, doc_id, set_id, extractor="quick-reader", kind=None):
    """One extracted sequence (or mutation) -> one ProtoArtifact, unbound and
    unconfirmed.

    `extractor` must name the paperclip worker that actually produced this
    record, not an aspirational tier -- only quick-reader runs on this
    account (see paperclip.py's map_papers default-worker comment), so that
    is the correct default rather than "exhaustive-extraction", which never
    touches a real run.

    `kind` lets a caller declare a non-sequence kind explicitly (e.g.
    "mutation", which has no `region` to derive from); when omitted, kind is
    derived from `region` as before.
    """
    return {
        "id": f"art_{index:03d}",
        "kind": kind or ("subsequence" if record.get("region") else "sequence"),
        "molecule": record["molecule"],
        "value": record["value"],
        "length": len(record["value"]),
        "parent": {"name": record.get("name"), "accession": None,
                   "region": record.get("region")},
        "evidence_refs": [],
        "provenance": {
            "doc_id": doc_id,
            "set_id": set_id,
            "where": record.get("where"),
            "verbatim": record.get("verbatim", False),
            "confirmed_in_source": False,
            "extractor": extractor,
        },
        "proto_binding": {"status": "unbound", "tools": [],
                          "unverified": [], "rejected_by": []},
    }


def item_from_mechanism(index, class_id, mech, doc_id, citation, extracted_by="quick-reader"):
    """One mechanism read out of a paper -> one EvidenceItem.

    `claim` arrives filled because `screen` is itself an LLM call. `support`
    stays null: how well established a claim is cannot be read off a single
    paper's own wording.

    `extracted_by` must name the paperclip worker that actually produced
    this mechanism, not an aspirational tier -- same rule as
    `draft_artifact.extractor` above. Only quick-reader runs on this
    account (see paperclip.py's map_papers default-worker comment), so
    that is the correct default; callers that know the real worker (e.g.
    `cmd_evidence`, which reads it back off `screen`'s own output) should
    pass it explicitly rather than relying on this default."""
    return {
        "id": f"ev_{index:03d}",
        "question_id": class_id,
        "claim": mech["claim"],
        "claim_type": "mechanism",
        "quantitative": None,
        "support": None,
        "citation": citation,
        "evidence_kind": None,
        "extracted_by": extracted_by,
        "confidence": None,
        # `vocabulary` is filled by `litkb label`, like every other
        # judgement field -- the tool drafts, the agent judges. Until then
        # the assessment is unmade, and says so.
        "testable_by": {"properties": mech.get("measurable_properties", []),
                        "vocabulary": [], "tools": [],
                        "requires_new_evaluator": "unassessed"},
        "provenance": {
            "doc_id": doc_id,
            "section": None,
            "category": "mechanism",
            "span": mech["chain"],
            "url": f"https://paperclip.gxl.ai/citations/papers/{doc_id}",
        },
    }


def citation_from_meta(m):
    # Preprints carry pub_date and source but no pub_year or journal.
    year = m.get("pub_year")
    if not year and m.get("pub_date"):
        try:
            year = int(str(m["pub_date"])[:4])
        except ValueError:
            year = None
    return {
        "doi": m.get("doi"),
        "title": m.get("title"),
        "year": year,
        "journal": m.get("journal") or m.get("source"),
        "authors": m.get("authors"),
    }


def apply_labels(items, labels, catalog=None, vocab=None):
    """Merge agent-supplied judgements into draft items, by id.

    `vocabulary` is the one label that has a computed consequence: assigning
    terms re-resolves `testable_by`. Assigning an EMPTY list is meaningful
    and different from never labelling -- it records that the agent looked
    and found nothing in the catalogue, which is a finding worth shipping.
    """
    by_id = {it["id"]: it for it in items}
    errors, applied = [], 0

    for lab in labels:
        iid = lab.get("id")
        if iid not in by_id:
            errors.append(f"unknown evidence id '{iid}'")
            continue
        item = by_id[iid]

        if "vocabulary" in lab:
            terms = lab["vocabulary"]
            if not isinstance(terms, list):
                errors.append(f"{iid}: vocabulary must be a list of term ids")
                continue
            if vocab is None or catalog is None:
                errors.append(f"{iid}: cannot apply vocabulary without a "
                              f"registry and a vocabulary file")
                continue
            try:
                resolved = proto.resolve_properties(terms, catalog, vocab) if terms \
                    else {"tools": [], "requires_new_evaluator": True}
            except UnknownTerm as exc:
                errors.append(f"{iid}: {exc}")
                continue
            item["testable_by"]["vocabulary"] = list(terms)
            item["testable_by"]["tools"] = resolved["tools"]
            item["testable_by"]["requires_new_evaluator"] = \
                resolved["requires_new_evaluator"]

        bad_field = False
        for field, value in lab.items():
            if field in ("id", "vocabulary"):
                continue
            if field == "support" and value not in SUPPORT_LEVELS:
                errors.append(f"{iid}: support must be one of {SUPPORT_LEVELS}, got '{value}'")
                bad_field = True
                continue
            if field == "claim_type" and value not in CLAIM_TYPES:
                errors.append(f"{iid}: claim_type must be one of {CLAIM_TYPES}, got '{value}'")
                bad_field = True
                continue
            if field == "evidence_kind" and value not in EVIDENCE_KINDS:
                errors.append(f"{iid}: evidence_kind must be one of {EVIDENCE_KINDS}, got '{value}'")
                bad_field = True
                continue
            if field == "confidence" and not (isinstance(value, (int, float)) and 0 <= value <= 1):
                errors.append(f"{iid}: confidence must be a number in [0, 1], got '{value}'")
                bad_field = True
                continue
            if field == "provenance":
                errors.append(f"{iid}: provenance is tool-owned and cannot be relabelled")
                bad_field = True
                continue
            if field == "testable_by":
                errors.append(f"{iid}: testable_by is resolved from `vocabulary`, "
                              f"not set directly")
                bad_field = True
                continue
            item[field] = value
        if not bad_field:
            applied += 1
    return applied, errors


def validate_items(items):
    """An item is only usable by L1 once every judgement field is filled."""
    errors = []
    for it in items:
        missing = [f for f in JUDGEMENT_FIELDS if it.get(f) in (None, "")]
        if missing:
            errors.append(f"{it['id']}: unlabelled fields {missing}")
    return errors
