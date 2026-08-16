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

from . import contracts, proto, reader, report
from .paperclip import PaperclipError, count, grep_set, map_papers, meta, search


def _load(path):
    return json.loads(Path(path).read_text())


def _emit(data, out):
    text = json.dumps(data, indent=2)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
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


def rows_to_plan(rows, objective, slug, groups):
    """Turn curated keyword rows into a class-structured plan.

    Rows are expert-written keyword bags, not verbatim phrases, so they are
    searched semantically. An ungrouped row is an error rather than a silent
    drop -- losing an expert query without saying so is the failure mode this
    guards against."""
    grouped = {r for rs in groups.values() for r in rs}
    orphans = [r for r in rows if r not in grouped]
    if orphans:
        raise contracts.ContractError(
            f"rows not assigned to any mechanism class: {orphans}")

    return {
        "objective": objective,
        "slug": slug,
        "search_mode": "semantic",
        "mechanism_classes": [
            {"id": cid,
             "question": f"What does the literature say about {cid.replace('_', ' ')}?",
             "candidate_evaluators": [],
             "search_phrases": phrases,
             "mechanism_patterns": ["mechanism"]}
            for cid, phrases in groups.items()
        ],
        "exclusions": [],
    }


def cmd_plan_import(args):
    rows = [line.strip() for line in Path(args.csv).read_text().splitlines()[1:]
            if line.strip()]
    groups = _load(args.groups)
    _emit(rows_to_plan(rows, args.objective, args.slug, groups), args.out)


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

    exact = plan.get("search_mode") != "semantic"
    result = {"valid": True, "classes": [], "warnings": []}
    for c in plan["mechanism_classes"]:
        entry = {"id": c["id"], "n_phrases": len(c["search_phrases"])}
        if args.probe:
            probes = [{"phrase": p, "n_papers": count(p, args.sources, exact=exact)}
                      for p in c["search_phrases"]]
            entry["probes"] = probes
            entry["n_papers_estimated"] = sum(p["n_papers"] for p in probes)
            for p in probes:
                if p["n_papers"] == 0:
                    if exact:
                        warning = (
                            f"{c['id']}: phrase '{p['phrase']}' returns 0 papers -- "
                            "exact match is literal, rewrite it as something authors write"
                        )
                    else:
                        warning = (
                            f"{c['id']}: phrase '{p['phrase']}' returns 0 papers under hybrid ranking"
                        )
                    result["warnings"].append(warning)
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

    exact = plan.get("search_mode") != "semantic"
    out = {"slug": plan["slug"], "sources": args.sources, "classes": [],
           "rejections": list(plan.get("exclusions", []))}

    for c in plan["mechanism_classes"]:
        sets = []
        for phrase in c["search_phrases"]:
            r = search(phrase, args.sources, args.n, exact=exact)
            print(f"  {c['id']:<28} {r['n_papers']:>4}  {phrase}", file=sys.stderr)
            if r["set_id"]:
                sets.append(r)
            else:
                reason = (
                    "exact-phrase search returned no papers" if exact
                    else "hybrid ranking returned no papers"
                )
                out["rejections"].append({
                    "kind": "phrase_zero_yield",
                    "class_id": c["id"],
                    "phrase": phrase,
                    "reason": reason,
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


# ---------------------------------------------------------- screen / dig / bind


def cmd_screen(args):
    found = _load(args.search)
    records = []
    for cls in found["classes"]:
        for s in cls["sets"]:
            # structured-extraction is gated to GXL testers on this account
            # (see litkb/paperclip.py's map_papers default-worker comment);
            # omit worker= so both passes run on quick-reader, the only
            # worker this account can actually run.
            raw = map_papers(s["set_id"], reader.SCREEN_QUERY,
                             reader.SCREEN_SCHEMA, n=args.n)
            for rec in reader.parse_map_output(raw):
                rec["class_id"] = cls["id"]
                rec["set_id"] = s["set_id"]
                records.append(rec)
            print(f"  {cls['id']:<28} {s['set_id']} read", file=sys.stderr)
    flagged = reader.flagged_for_dig(records)
    print(f"  {len(flagged)}/{len(records)} papers claim a sequence", file=sys.stderr)
    _emit({"slug": found["slug"], "papers": records, "flagged": flagged}, args.out)


def cmd_dig(args):
    screened = _load(args.screen)
    flagged = set(screened["flagged"])
    by_set = {}
    for rec in screened["papers"]:
        if rec["doc_id"] in flagged:
            by_set.setdefault(rec["set_id"], []).append(rec["doc_id"])

    artifacts, n = [], 0
    for set_id, docs in by_set.items():
        # exhaustive-extraction is likewise gated (see cmd_screen); omit
        # worker= to fall back to quick-reader here too.
        raw = map_papers(set_id, reader.DIG_QUERY, reader.DIG_SCHEMA, n=args.n)
        for rec in reader.parse_map_output(raw):
            if rec["doc_id"] not in flagged:
                continue
            for seq in rec.get("sequences", []):
                n += 1
                artifacts.append(contracts.draft_artifact(n, seq, rec["doc_id"], set_id))
    print(f"  {len(artifacts)} candidate sequences", file=sys.stderr)
    _emit({"slug": screened["slug"], "artifacts": artifacts}, args.out)


def cmd_bind(args):
    dug = _load(args.artifacts)
    catalog = _load(args.registry)
    kept, rejections = [], []

    for art in dug["artifacts"]:
        # confirm_in_source's grep_fn is 2-arg (set_id, patterns) and cannot
        # itself request fixed-string matching -- so this closure asks for
        # it explicitly. A bare grep_set would send the sequence to
        # `paperclip grep -e` as a REGEX, and a sequence containing `*`
        # (stop codon) or `.` (masked residue) could then match text that
        # is not actually the sequence, producing a false confirmation --
        # exactly what this check exists to prevent.
        art["provenance"]["confirmed_in_source"] = reader.confirm_in_source(
            {"value": art["value"], "verbatim": art["provenance"]["verbatim"],
             "provenance": art["provenance"]},
            lambda set_id, patterns: grep_set(set_id, patterns, fixed=True),
        )
        if not art["provenance"]["confirmed_in_source"]:
            rejections.append({"kind": "not_confirmed_in_source", "id": art["id"],
                               "doc_id": art["provenance"]["doc_id"],
                               "reason": "sequence does not literally appear in its source document"})
            continue
        art["proto_binding"] = proto.bind_artifact(art, catalog)
        status = art["proto_binding"]["status"]
        if status == "runnable":
            kept.append(art)
        elif status == "unsupported_kind":
            rejections.append({"kind": f"proto_{status}", "id": art["id"],
                               "reason": art["proto_binding"].get("reason",
                                         "no proto tool consumes this artifact kind")})
        else:
            rejections.append({"kind": f"proto_{status}",
                               "id": art["id"],
                               "reason": art["proto_binding"]["rejected_by"] or
                                         art["proto_binding"]["unverified"]})

    print(f"  {len(kept)} runnable, {len(rejections)} rejected", file=sys.stderr)
    _emit({"slug": dug["slug"], "artifacts": kept, "rejections": rejections}, args.out)


# ------------------------------------------------------------- evidence


def cmd_evidence(args):
    screened = _load(args.screen)
    catalog = _load(args.registry) if Path(args.registry).exists() else {"tools": []}
    items, cache, n = [], {}, 0

    for rec in screened["papers"]:
        doc = rec["doc_id"]
        if doc not in cache:
            cache[doc] = contracts.citation_from_meta(meta(doc))
        for mech in rec.get("mechanisms", []):
            n += 1
            item = contracts.item_from_mechanism(n, rec["class_id"], mech, doc, cache[doc])
            item["testable_by"] = {
                "properties": mech.get("measurable_properties", []),
                **proto.resolve_properties(mech.get("measurable_properties", []), catalog),
            }
            items.append(item)

    need_eval = sum(1 for i in items if i["testable_by"]["requires_new_evaluator"])
    print(f"  {len(items)} items, {need_eval} need a new evaluator", file=sys.stderr)
    _emit({"slug": screened["slug"], "items": items,
           "unlabelled": len(contracts.validate_items(items))}, args.out)


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


def resolve_coverage(plan, catalog):
    """Resolve each mechanism class against the proto catalogue.

    §6: an uncalibrated evaluator may run but may not rank, so a class is
    `full` only when every tool it names is both known and validated."""
    known = {t["key"]: t for t in catalog["tools"]}
    classes = []
    for c in plan["mechanism_classes"]:
        wanted = c.get("candidate_evaluators", [])
        bound = [w for w in wanted if w in known]
        usable = [b for b in bound if known[b].get("status") == "validated"]
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
    return classes


def cmd_proto_sync(args):
    tools = proto.fetch_tools(args.project)
    print(f"  {len(tools)} tools from proto-tools", file=sys.stderr)
    catalog = proto.build_catalog(tools, lambda k: proto.fetch_input_doc(k, args.project))
    parsed = sum(1 for t in catalog["tools"] if t["max_length"] is not None)
    print(f"  {parsed}/{len(tools)} have a parseable length cap", file=sys.stderr)
    _emit(catalog, args.out)


def cmd_registry_check(args):
    plan = _load(args.plan)
    path = Path(args.registry)
    if not path.exists():
        _emit({"registry": str(path), "status": "missing",
               "classes": [{"id": c["id"], "evaluator_coverage": "unknown"}
                           for c in plan["mechanism_classes"]],
               "note": "run `litkb proto-sync -o registry/proto_catalog.json` first"},
              args.out)
        return
    _emit({"registry": str(path), "status": "loaded",
           "classes": resolve_coverage(plan, _load(path))}, args.out)


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

    p = sub.add_parser("plan-import", help="curated keyword CSV -> class-structured plan")
    p.add_argument("csv")
    p.add_argument("groups", help="JSON mapping class id -> list of CSV rows")
    p.add_argument("--objective", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_plan_import)

    p = sub.add_parser("search", help="run every phrase, keep every set ID")
    p.add_argument("plan")
    p.add_argument("--sources", default="pmc,biorxiv")
    p.add_argument("-n", type=int, default=100)
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("screen", help="cheap full-text sweep for mechanisms")
    p.add_argument("search")
    p.add_argument("-n", type=int, default=None)
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_screen)

    p = sub.add_parser("dig", help="deep read of papers that claim a sequence")
    p.add_argument("screen")
    p.add_argument("-n", type=int, default=None)
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_dig)

    p = sub.add_parser("bind", help="verify artifacts against the proto catalogue")
    p.add_argument("artifacts")
    p.add_argument("--registry", default="../registry/proto_catalog.json")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_bind)

    p = sub.add_parser("evidence", help="screen output -> draft EvidenceItems (judgement fields null)")
    p.add_argument("screen")
    p.add_argument("--registry", default="../registry/proto_catalog.json")
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

    p = sub.add_parser("proto-sync", help="regenerate the proto-tools constraint catalogue")
    p.add_argument("--project", default="../proto")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_proto_sync)

    p = sub.add_parser("registry-check", help="resolve mechanism classes against the evaluator registry")
    p.add_argument("plan")
    p.add_argument("--registry", default="../registry/proto_catalog.json")
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
