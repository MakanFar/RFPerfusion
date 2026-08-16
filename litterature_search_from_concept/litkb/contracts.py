"""Typed artifacts. The framework's §4 rule -- "agents communicate only
through typed artifacts, no agent reads another agent's prose" -- is enforced
here.

Every judgement field on an EvidenceItem starts null. This module builds
drafts and validates completions; it never guesses a claim or a support level.
That work belongs to the agent, via `litkb label`.
"""

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


def draft_item(index, class_id, hit, category, citation):
    """One raw grep hit -> one draft EvidenceItem (PRD §6.2 shape).

    Judgement fields are null by construction. `provenance` is the part this
    tool can actually vouch for."""
    return {
        "id": f"ev_{index:03d}",
        "question_id": class_id,
        "claim": None,
        "claim_type": None,
        "quantitative": None,
        "support": None,
        "citation": citation,
        "evidence_kind": None,
        "extracted_by": "paperclip",
        "confidence": None,
        "provenance": {
            "doc_id": hit["doc_id"],
            "set_id": hit["set_id"],
            "section": hit.get("section"),
            "category": category,
            "span": hit["text"],
            "truncated_after": hit.get("truncated_after", 0),
            "url": f"https://paperclip.gxl.ai/citations/papers/{hit['doc_id']}",
        },
    }


def draft_artifact(index, record, doc_id, set_id):
    """One extracted sequence -> one ProtoArtifact, unbound and unconfirmed."""
    return {
        "id": f"art_{index:03d}",
        "kind": "subsequence" if record.get("region") else "sequence",
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
            "extractor": "exhaustive-extraction",
        },
        "proto_binding": {"status": "unbound", "tools": [],
                          "unverified": [], "rejected_by": []},
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


def apply_labels(items, labels):
    """Merge agent-supplied judgements into draft items, by id."""
    by_id = {it["id"]: it for it in items}
    errors, applied = [], 0

    for lab in labels:
        iid = lab.get("id")
        if iid not in by_id:
            errors.append(f"unknown evidence id '{iid}'")
            continue
        item = by_id[iid]
        for field, value in lab.items():
            if field == "id":
                continue
            if field == "support" and value not in SUPPORT_LEVELS:
                errors.append(f"{iid}: support must be one of {SUPPORT_LEVELS}, got '{value}'")
                continue
            if field == "claim_type" and value not in CLAIM_TYPES:
                errors.append(f"{iid}: claim_type must be one of {CLAIM_TYPES}, got '{value}'")
                continue
            if field == "evidence_kind" and value not in EVIDENCE_KINDS:
                errors.append(f"{iid}: evidence_kind must be one of {EVIDENCE_KINDS}, got '{value}'")
                continue
            if field == "confidence" and not (isinstance(value, (int, float)) and 0 <= value <= 1):
                errors.append(f"{iid}: confidence must be a number in [0, 1], got '{value}'")
                continue
            if field == "provenance":
                errors.append(f"{iid}: provenance is tool-owned and cannot be relabelled")
                continue
            item[field] = value
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
