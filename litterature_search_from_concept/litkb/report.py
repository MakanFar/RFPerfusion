"""Human-readable rendering of the typed evidence.

The old knowledge_base_<slug>.txt counted paperclip's "No matches" message as
a kept line, so every category reported a floor of one line per empty set.
Counts here are of EvidenceItems, so an empty category reads as 0.
"""

from collections import Counter, defaultdict
from datetime import datetime

RULE = "=" * 70


def render(evidence, search=None, artifacts=None):
    """Render the human-readable knowledge base.

    `artifacts` is `bind`'s output ({"artifacts": [...], "rejections": [...]}),
    optional since a report can be rendered before `dig`/`bind` ever ran. When
    given, it adds a PROTO-RUNNABLE ARTIFACTS section. Acceptance there is a
    schema check against the proto-tools constraint table (molecule,
    alphabet, length cap), not a run -- nothing in that section has actually
    been executed."""
    items = evidence["items"]
    out = [f"# knowledge base :: {evidence['slug']} :: "
           f"{datetime.now():%Y-%m-%d %H:%M}",
           f"# {len(items)} evidence items, "
           f"{sum(1 for i in items if i.get('support'))} labelled"]

    if search:
        cov = search.get("coverage", {})
        out.append(f"# coverage: {cov.get('classes_covered')}/{cov.get('classes_total')} "
                   f"mechanism classes (framework minimum 6: "
                   f"{'met' if cov.get('meets_framework_minimum') else 'NOT met'})")

    by_class = defaultdict(list)
    for it in items:
        by_class[it["question_id"]].append(it)

    for class_id, class_items in by_class.items():
        out += ["", "", RULE, f"## {class_id.upper()}  ({len(class_items)} items)", RULE]
        by_cat = defaultdict(list)
        for it in class_items:
            by_cat[it["provenance"]["category"]].append(it)

        for cat, cat_items in by_cat.items():
            support = Counter(i.get("support") or "unlabelled" for i in cat_items)
            out += ["", f"### {cat}  ({len(cat_items)} items; "
                        f"{', '.join(f'{v} {k}' for k, v in support.items())})"]
            for it in cat_items:
                cite = it["citation"]
                head = f"[{it['id']}] {it['provenance']['doc_id']}"
                if cite.get("year"):
                    head += f" ({cite['year']})"
                if it.get("support"):
                    head += f" :: {it['support']}"
                out.append(head)
                if it.get("claim"):
                    out.append(f"    claim: {it['claim']}")
                section = it["provenance"].get("section")
                out.append(f"    {'[' + section + '] ' if section else ''}"
                           f"{it['provenance']['span'][:400]}")
                out.append(f"    {it['provenance']['url']}")

    rejections = (search or {}).get("rejections", [])
    if rejections:
        out += ["", "", RULE, f"## REJECTED  ({len(rejections)})", RULE,
                "# Rejection is a first-class output (framework principle 3)."]
        for r in rejections:
            label = r.get("kind", "exclusion")
            what = r.get("phrase") or r.get("class_id") or r.get("excluded", "")
            out.append(f"- [{label}] {what}: {r.get('reason', '')}")

    if artifacts:
        kept = artifacts.get("artifacts", [])
        out += ["", "", RULE, f"## PROTO-RUNNABLE ARTIFACTS  ({len(kept)})", RULE,
                "# Every artifact below is confirmed present in its source document",
                "# and accepted by at least one proto tool. Acceptance is a schema",
                "# check, not a run -- nothing here has been executed."]
        for a in kept:
            tools = ", ".join(t["key"] for t in a.get("proto_binding", {}).get("tools", []))
            parent = (a.get("parent") or {}).get("name") or "unnamed"
            out.append(f"[{a['id']}] {a['kind']} :: {parent} :: {a['length']} aa :: {tools}")
            out.append(f"    {a['value'][:120]}")
            prov = a.get("provenance", {})
            out.append(f"    {prov.get('doc_id')} :: {prov.get('where')}")

        rejected = artifacts.get("rejections", [])
        if rejected:
            out += ["", f"### rejected artifacts ({len(rejected)})"]
            for r in rejected:
                out.append(f"- [{r.get('kind')}] {r.get('id')}: {r.get('reason')}")

    return "\n".join(out) + "\n"
