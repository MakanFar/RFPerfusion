#!/usr/bin/env python3
"""litkb -- concept -> corpus -> typed evidence, as discrete tool calls.

Each subcommand reads JSON, writes JSON, and does exactly one thing, so an
agent can drive the pipeline, inspect any stage, and retry one step without
rerunning the rest. All judgement (planning, claim wording, support level)
belongs to the calling agent; this tool only does deterministic work.

Feeds L1 of docs/PRD-framework.md. Requires Python >= 3.10.
"""

import argparse
import json
import sys
from pathlib import Path

from . import contracts, patterns, report
from .paperclip import PaperclipError, count, grep_set, meta, search


def _load(path):
    return json.loads(Path(path).read_text())


def _emit(data, out):
    text = json.dumps(data, indent=2)
    if out:
        Path(out).write_text(text + "\n")
        print(f"-> {out}", file=sys.stderr)
    else:
        print(text)


def _fail(lines):
    for line in lines:
        print(f"  {line}", file=sys.stderr)
    sys.exit(1)


# ----------------------------------------------------------------- plan

TEMPLATE = {
    "objective": "<the free-text design concept>",
    "slug": "<short name>",
    "mechanism_classes": [
        {
            "id": "<snake_case mechanism class, e.g. thermal_transduction>",
            "question": "<the sub-question this class answers>",
            "candidate_evaluators": [],
            "search_phrases": [
                "<multi-word phrase authors write VERBATIM in a title or abstract>"
            ],
            "mechanism_patterns": [
                "<distinctive multi-word fragment flagging mechanistic content>"
            ],
        }
    ],
    "exclusions": [
        {"excluded": "<what you deliberately left out>", "reason": "<why>"}
    ],
}


def cmd_plan_template(args):
    _emit(TEMPLATE, args.out)
    print(
        "\nWrite one class per mechanism class, not per phrase -- the framework "
        "measures coverage over classes (>=6) and this is where that is decided.\n"
        "search_phrases are matched as STRICT LITERALS. Probe each with "
        "`litkb plan-validate <plan> --probe` before searching.",
        file=sys.stderr,
    )


def cmd_plan_validate(args):
    plan = _load(args.plan)
    errors = contracts.validate_plan(plan)
    if errors:
        print("plan is invalid:", file=sys.stderr)
        _fail(errors)

    result = {"valid": True, "classes": [], "warnings": []}
    for c in plan["mechanism_classes"]:
        entry = {"id": c["id"], "n_phrases": len(c["search_phrases"])}
        if args.probe:
            probes = [{"phrase": p, "n_papers": count(p, args.sources)}
                      for p in c["search_phrases"]]
            entry["probes"] = probes
            entry["n_papers_estimated"] = sum(p["n_papers"] for p in probes)
            for p in probes:
                if p["n_papers"] == 0:
                    result["warnings"].append(
                        f"{c['id']}: phrase '{p['phrase']}' returns 0 papers -- "
                        "exact match is literal, rewrite it as something authors write"
                    )
        result["classes"].append(entry)

    if args.probe:
        total = sum(e.get("n_papers_estimated", 0) for e in result["classes"])
        for e in result["classes"]:
            got = e.get("n_papers_estimated", 0)
            if total and got / total > 0.5:
                result["warnings"].append(
                    f"{e['id']}: {got}/{total} papers come from this one class -- "
                    "it will swamp the corpus"
                )
    _emit(result, args.out)


# --------------------------------------------------------------- search


def cmd_search(args):
    plan = _load(args.plan)
    errors = contracts.validate_plan(plan)
    if errors:
        _fail(errors)

    out = {"slug": plan["slug"], "sources": args.sources, "classes": [],
           "rejections": list(plan.get("exclusions", []))}

    for c in plan["mechanism_classes"]:
        sets = []
        for phrase in c["search_phrases"]:
            r = search(phrase, args.sources, args.n)
            print(f"  {c['id']:<28} {r['n_papers']:>4}  {phrase}", file=sys.stderr)
            if r["set_id"]:
                sets.append(r)
            else:
                out["rejections"].append({
                    "kind": "phrase_zero_yield",
                    "class_id": c["id"],
                    "phrase": phrase,
                    "reason": "exact-phrase search returned no papers",
                })
        entry = {
            "id": c["id"],
            "sets": sets,
            "n_papers_total": sum(s["n_papers"] for s in sets),
            "status": "covered" if sets else "empty",
        }
        if not sets:
            out["rejections"].append({
                "kind": "class_no_corpus",
                "class_id": c["id"],
                "reason": "every phrase in this mechanism class returned no papers",
            })
        out["classes"].append(entry)

    covered = sum(1 for c in out["classes"] if c["status"] == "covered")
    out["coverage"] = {"classes_covered": covered,
                       "classes_total": len(out["classes"]),
                       "meets_framework_minimum": covered >= 6}
    _emit(out, args.out)


# -------------------------------------------------------------- extract


def cmd_extract(args):
    plan = _load(args.plan)
    found = _load(args.search)
    by_id = {c["id"]: c for c in plan["mechanism_classes"]}

    out = {"slug": found["slug"], "classes": []}
    for sc in found["classes"]:
        cls = by_id.get(sc["id"])
        if cls is None or sc["status"] != "covered":
            continue
        categories = {
            "mechanism": {"ignore_case": True, "patterns": cls["mechanism_patterns"]},
            **patterns.STRUCTURAL,
        }
        cat_hits = {}
        for cat, spec in categories.items():
            hits = []
            for s in sc["sets"]:
                hits += grep_set(s["set_id"], spec["patterns"], spec["ignore_case"])
            cat_hits[cat] = hits
            print(f"  {sc['id']:<28} {cat:<12} {len(hits):>4} hits", file=sys.stderr)
        out["classes"].append({"id": sc["id"], "categories": cat_hits})
    _emit(out, args.out)


# ------------------------------------------------------------- evidence


def cmd_evidence(args):
    hits = _load(args.hits)
    items, seen, cache, n = [], set(), {}, 0

    for cls in hits["classes"]:
        for category, hit_list in cls["categories"].items():
            for hit in hit_list:
                key = (hit["doc_id"], hit["text"])
                if key in seen:          # one span can match several categories
                    continue
                seen.add(key)
                doc = hit["doc_id"]
                if doc not in cache:
                    cache[doc] = contracts.citation_from_meta(meta(doc))
                n += 1
                items.append(contracts.draft_item(n, cls["id"], hit, category, cache[doc]))

    _emit({"slug": hits["slug"], "items": items,
           "unlabelled": len(items),
           "note": "judgement fields are null by design -- fill them with `litkb label`"},
          args.out)


def cmd_label(args):
    ev = _load(args.evidence)
    labels = _load(args.labels)
    if isinstance(labels, dict):
        labels = labels.get("labels", [])
    applied, errors = contracts.apply_labels(ev["items"], labels)
    if errors:
        print(f"applied {applied} labels, {len(errors)} rejected:", file=sys.stderr)
        _fail(errors)
    ev["unlabelled"] = len(contracts.validate_items(ev["items"]))
    _emit(ev, args.out or args.evidence)


def cmd_validate(args):
    ev = _load(args.evidence)
    errors = contracts.validate_items(ev["items"])
    if errors:
        print(f"{len(errors)} of {len(ev['items'])} items are not ready for L1:",
              file=sys.stderr)
        _fail(errors[:20])
    print(f"all {len(ev['items'])} items complete", file=sys.stderr)


# ------------------------------------------------------------- registry


def cmd_registry_check(args):
    """Framework §77: the registry constrains ideation, so it is an INPUT.
    Classes with no evaluator come back `requires_new_evaluator` -- a
    legitimate output, not a discard."""
    plan = _load(args.plan)
    registry_path = Path(args.registry)

    if not registry_path.exists():
        _emit({
            "registry": str(registry_path),
            "status": "missing",
            "classes": [{"id": c["id"], "evaluator_coverage": "unknown"}
                        for c in plan["mechanism_classes"]],
            "note": "No evaluator registry on disk, so coverage cannot be resolved. "
                    "registry/evaluators.json was removed in commit 945164f with the "
                    "Tamarind integration and has no replacement yet.",
        }, args.out)
        return

    raw = _load(registry_path)
    entries = raw if isinstance(raw, list) else raw.get("evaluators", [])
    known = {e.get("evaluator_id"): e for e in entries}

    classes = []
    for c in plan["mechanism_classes"]:
        wanted = c.get("candidate_evaluators", [])
        bound = [w for w in wanted if w in known]
        usable = [b for b in bound if known[b].get("status") == "validated"]
        # §6: uncalibrated evaluators may run, but their scores may not rank
        # candidates -- so a class is only "full" once every bound evaluator
        # is validated and nothing it asked for is unresolved.
        if not wanted or not bound:
            coverage = "none"
        elif len(bound) == len(wanted) and len(usable) == len(bound):
            coverage = "full"
        else:
            coverage = "partial"
        classes.append({
            "id": c["id"],
            "evaluator_coverage": coverage,
            "bound": bound,
            "unresolved": [w for w in wanted if w not in known],
            "uncalibrated": [b for b in bound if b not in usable],
            "requires_new_evaluator": coverage == "none",
        })
    _emit({"registry": str(registry_path), "status": "loaded", "classes": classes},
          args.out)


# --------------------------------------------------------------- report


def cmd_report(args):
    ev = _load(args.evidence)
    text = report.render(ev, _load(args.search) if args.search else None)
    Path(args.out).write_text(text)
    print(f"-> {args.out}", file=sys.stderr)


# ------------------------------------------------------------------ cli


def main(argv=None):
    ap = argparse.ArgumentParser(prog="litkb", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan-template", help="print an empty plan for the agent to fill")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_plan_template)

    p = sub.add_parser("plan-validate", help="schema-check a plan; --probe tests phrase yield")
    p.add_argument("plan")
    p.add_argument("--probe", action="store_true")
    p.add_argument("--sources", default="pmc")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_plan_validate)

    p = sub.add_parser("search", help="run every phrase, keep every set ID")
    p.add_argument("plan")
    p.add_argument("--sources", default="pmc,biorxiv")
    p.add_argument("-n", type=int, default=100)
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("extract", help="grep the sets into categorized raw hits")
    p.add_argument("plan")
    p.add_argument("search")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_extract)

    p = sub.add_parser("evidence", help="hits -> draft EvidenceItems (judgement fields null)")
    p.add_argument("hits")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_evidence)

    p = sub.add_parser("label", help="merge agent-written judgements into evidence")
    p.add_argument("evidence")
    p.add_argument("labels")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_label)

    p = sub.add_parser("validate", help="are all items complete enough for L1?")
    p.add_argument("evidence")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("registry-check", help="resolve mechanism classes against the evaluator registry")
    p.add_argument("plan")
    p.add_argument("--registry", default="registry/evaluators.json")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_registry_check)

    p = sub.add_parser("report", help="render the human-readable knowledge base")
    p.add_argument("evidence")
    p.add_argument("--search")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(fn=cmd_report)

    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except PaperclipError as e:
        sys.exit(f"paperclip: {e}")
    except (contracts.ContractError, FileNotFoundError) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
