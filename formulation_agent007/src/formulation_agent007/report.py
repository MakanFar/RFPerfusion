"""The human-readable brief.

One document a scientist reads before spending a Modal budget: what was chosen,
what was rejected, what gets searched, what gets built, and what number kills a
design. Everything here also exists in the JSON — this is the read, not the
record.
"""

from __future__ import annotations

from .models import DesignBrief


def render_markdown(brief: DesignBrief) -> str:
    frame = brief.frame
    lines: list[str] = [
        f"# Design brief — {brief.slug}",
        "",
        f"**Question.** {brief.question}",
        "",
        f"*Generated {brief.created_at.strftime('%Y-%m-%d %H:%M')} UTC. Every "
        "fitness gate below names a proto-tools key that was checked against the "
        "tool catalogue, a metric those tools emit, and a numeric threshold. "
        "Nothing here has been verified against literature — that is what the "
        "mining and harvest steps are for.*",
        "",
        "## Framing",
        "",
        frame.reading_of_question,
        "",
        f"**Target function.** {frame.target_function}",
        "",
    ]
    if frame.stimulus:
        lines += [f"**Stimulus.** {frame.stimulus}", ""]
    lines += [
        f"**Chosen pathway.** {frame.chosen_pathway} "
        f"_({frame.pathway_confidence.value})_",
        "",
        frame.pathway_rationale,
        "",
    ]
    if frame.simulability_note:
        lines += [
            "> **Not simulable with this toolchain.** "
            f"{frame.simulability_note}",
            "",
        ]
    if frame.excluded_pathways:
        lines += ["**Considered and excluded.**", ""]
        for exc in frame.excluded_pathways:
            tag = "unsimulable here" if exc.unsimulable else "ruled out"
            lines.append(f"- **{exc.name}** _({tag})_ — {exc.reason}")
        lines.append("")
    if frame.assumptions:
        lines += ["**Assumptions.**", ""]
        lines += [f"- {a}" for a in frame.assumptions]
        lines.append("")

    # ---------------------------------------------------------------- shards
    lines += [
        "## Shards",
        "",
        "| id | shard | role | candidate families |",
        "|----|-------|------|--------------------|",
    ]
    for shard in brief.shards:
        families = ", ".join(shard.candidate_families) or "—"
        optional = "" if shard.required else " _(optional)_"
        lines.append(f"| {shard.id} | {shard.name}{optional} | {shard.role} | {families} |")
    lines.append("")
    for shard in brief.shards:
        if shard.failure_mode:
            lines.append(f"- **{shard.id} breaks by:** {shard.failure_mode}")
    lines.append("")

    # ------------------------------------------------------------ literature
    lit = brief.literature
    lines += [
        "## Literature mining",
        "",
        f"Concept and reviewed plan are emitted as `concept_{brief.slug}.txt` and "
        f"`plan_{brief.slug}.json`. Run `run_literature.sh` from the repository "
        "root; the plan is passed with `--plan-file`, so the mining script does "
        "not re-plan.",
        "",
        f"**Search phrases ({len(lit.search_phrases)}).** exact-phrase matched "
        "against titles and abstracts",
        "",
    ]
    lines += [f"- `{p}`" for p in lit.search_phrases]
    lines += [
        "",
        f"**Mechanism patterns ({len(lit.mechanism_patterns)}).** "
        "case-insensitive grep over retrieved full text",
        "",
    ]
    lines += [f"- `{p}`" for p in lit.mechanism_patterns]
    lines += ["", f"**Planner notes.** {lit.notes}", ""]

    # -------------------------------------------------------------- assembly
    a = brief.assembly
    lines += [
        "## Assembly",
        "",
        f"**Construct (N→C).** {' → '.join(a.construct_order) or '—'}",
        "",
    ]
    if a.linkers:
        lines += ["| between | sequence | type | why |", "|---|---|---|---|"]
        for linker in a.linkers:
            kind = "rigid" if linker.rigid else "flexible"
            lines.append(
                f"| {linker.after_shard} → {linker.before_shard} | "
                f"`{linker.sequence}` | {kind} | {linker.rationale} |"
            )
        lines.append("")
    if a.combinatorial_plan:
        lines += [f"**Variants.** {a.combinatorial_plan}", ""]

    # ----------------------------------------------------------------- gates
    p = brief.proto
    lines += [
        "## Fitness cascade",
        "",
        "| # | gate | tools | state | condition | cost | decisive |",
        "|---|------|-------|-------|-----------|------|----------|",
    ]
    for gate in p.ordered():
        tools = ", ".join(f"`{k}`" for k in gate.tool_keys)
        lines.append(
            f"| {gate.order} | {gate.name} | {tools} | {gate.state.value} | "
            f"`{gate.condition()}` | {gate.cost_tier} | "
            f"{'yes' if gate.decisive else ''} |"
        )
    lines += ["", f"**Ranking.** `{p.ranking_expression}`", ""]
    if p.ranking_rationale:
        lines += [p.ranking_rationale, ""]
    if p.known_limitations:
        lines += ["**Known limitations.**", ""]
        lines += [f"- {limit}" for limit in p.known_limitations]
        lines.append("")

    # -------------------------------------------------------------- warnings
    if brief.validation_warnings:
        lines += [
            "## Validation warnings",
            "",
            "These survived one repair attempt and are recorded rather than "
            "hidden. Read them before acting on the brief.",
            "",
        ]
        lines += [f"- {w}" for w in brief.validation_warnings]
        lines.append("")

    lines += [
        "## Next steps",
        "",
        "1. `bash run_literature.sh` from the repository root — mine the corpus.",
        f"2. Hand `harvest_{brief.slug}.md` to the Paperclip agent — extract "
        "sequences per shard.",
        f"3. Hand `proto_brief_{brief.slug}.md` to the Proto agent — assemble and "
        "run the cascade.",
        "",
    ]
    return "\n".join(lines) + "\n"
