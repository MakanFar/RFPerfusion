"""Artifact emission.

The brief is only useful if the next agent can act on it without a human
translating first, so each downstream consumer gets a file shaped for it:

  concept_<slug>.txt        -> paperclip_kb.py positional argument
  plan_<slug>.json          -> paperclip_kb.py --plan-file (skips its own
                               planning call; the schema is validated against
                               that script's contract before it is written)
  run_literature.sh         -> the litkb chain (default handoff, typed
                               evidence), plus the paperclip_kb.py grep
                               commands as the no-LLM-quota alternative
  harvest_<slug>.md         -> the Paperclip agent's extraction contract
  proto_brief_<slug>.md     -> the Proto agent's runbook
  brief-<stamp>.json/.md    -> the full audit trail and the human read
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from .config import SETTINGS
from .models import DesignBrief
from .report import render_markdown

# Path from the repository root to the mining script, used in the emitted
# shell commands. The brief is written wherever the user asked, so commands are
# documented as run-from-repo-root rather than relative to the output dir.
KB_SCRIPT = "litterature_search_from_concept/paperclip_kb.py"

# litkb's --registry and --project defaults are relative to this directory, so
# the emitted script must `cd` there for the litkb stages.
LITKB_DIR = "litterature_search_from_concept"


def save_brief(brief: DesignBrief, out_dir: str) -> list[Path]:
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = brief.created_at.strftime("%Y%m%d-%H%M%S")
    slug = brief.slug

    paths: list[Path] = []

    def write(name: str, text: str) -> None:
        path = directory / name
        path.write_text(text, encoding="utf-8")
        paths.append(path)

    write(f"brief-{stamp}.json", brief.model_dump_json(indent=2))
    write(f"brief-{stamp}.md", render_markdown(brief))
    write(f"concept_{slug}.txt", _concept_file(brief))
    write(f"plan_{slug}.json", json.dumps(brief.literature.plan_payload(), indent=2) + "\n")
    write("run_literature.sh", _run_script(brief, directory))
    write(f"harvest_{slug}.md", render_harvest(brief))
    write(f"proto_brief_{slug}.md", render_proto_brief(brief))
    return paths


# --------------------------------------------------------------------------
# concept file
# --------------------------------------------------------------------------


def _concept_file(brief: DesignBrief) -> str:
    """The concept file `paperclip_kb.py` reads as its positional argument.

    Its planner is given free text and asked for phrases and patterns. We
    supply a reviewed plan alongside, so this file's real job is to be the
    human-auditable record of what was searched and why.
    """
    frame = brief.frame
    lines = [
        f"# design concept :: {brief.slug}",
        "",
        f"QUESTION: {brief.question}",
        "",
        brief.literature.concept_text.strip(),
        "",
        "SHARDS TO SOURCE FROM THE LITERATURE:",
    ]
    for shard in brief.shards:
        families = ", ".join(shard.candidate_families) or "unspecified"
        lines.append(f"- {shard.id} {shard.name}: {shard.role} Candidates: {families}.")
    lines += [
        "",
        "CONSTRAINT: every candidate design must be scoreable as discrete "
        "structural states using proto-tools. Routes requiring explicit "
        "molecular dynamics, field simulation, or quantum calculation are out "
        "of scope for this run.",
        "",
        f"NOT SIMULABLE HERE: {frame.simulability_note or 'unstated'}",
    ]
    if frame.excluded_pathways:
        lines += ["", "CONSIDERED AND EXCLUDED:"]
        for exc in frame.excluded_pathways:
            why = "unsimulable with available tools" if exc.unsimulable else "ruled out"
            lines.append(f"- {exc.name} ({why}): {exc.reason}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# runnable commands
# --------------------------------------------------------------------------


def _run_script(brief: DesignBrief, directory: Path) -> str:
    """Emit `run_literature.sh`.

    Every path handed to a command below is made absolute (`directory` is
    resolved up front) and every interpolation is quoted with `shlex.quote`
    (or built through `shlex.join`, which quotes each element). That is
    deliberate: the litkb stages must `cd` into `LITKB_DIR` because litkb's
    `--registry` and `--project` defaults are relative to that directory, and
    a `cd` silently breaks any path built by string-prefixing `../` onto a
    value that might already be absolute, might point outside the repo, or
    might contain a space. Absolute + quoted paths mean the `cd` cannot change
    what any argument means, for a relative output dir, an absolute one, or
    one with a space in it.
    """
    slug = brief.slug
    sources = ",".join(SETTINGS.source_list())
    directory = directory.resolve()
    concept = str(directory / f"concept_{slug}.txt")
    plan = str(directory / f"plan_{slug}.json")
    run_dir = str(directory / f"mining_{slug}")

    base = [
        "uv",
        "run",
        "--with",
        "anthropic",
        "python",
        KB_SCRIPT,
        concept,
        "--slug",
        slug,
        "--sources",
        sources,
        "-n",
        str(SETTINGS.papers_per_search),
        "--output-dir",
        run_dir,
    ]
    dry = shlex.join([*base, "--plan-file", plan, "--dry-run"])
    live = shlex.join([*base, "--plan-file", plan])

    run_path = Path(run_dir)
    plan_out = str(run_path / f"plan_{slug}.json")
    search_out = str(run_path / f"search_{slug}.json")
    screen_out = str(run_path / f"screen_{slug}.json")
    dig_out = str(run_path / f"dig_{slug}.json")
    artifacts_out = str(run_path / f"artifacts_{slug}.json")
    evidence_out = str(run_path / f"evidence_{slug}.json")

    def litkb(*args: str) -> str:
        return shlex.join(["uv", "run", "--project", ".", "python", "-m", "litkb", *args])

    litkb_plan_adopt = litkb(
        "plan-adopt", plan, "--objective", brief.question, "--slug", slug,
        "--output-dir", run_dir,
    )
    litkb_search = litkb("search", plan_out, "-n", "4", "--output-dir", run_dir)
    litkb_screen = litkb("screen", search_out, "-n", "1", "--output-dir", run_dir)
    litkb_dig = litkb("dig", screen_out, "--output-dir", run_dir)
    litkb_bind = litkb("bind", dig_out, "--output-dir", run_dir)
    litkb_evidence = litkb("evidence", screen_out, "--output-dir", run_dir)
    litkb_report = litkb(
        "report", evidence_out, "--search", search_out, "--artifacts", artifacts_out,
        "--output-dir", run_dir,
    )
    litkb_manifest = litkb("manifest", evidence_out, "--output-dir", run_dir)
    cd_litkb_dir = shlex.quote(LITKB_DIR)

    return f"""#!/usr/bin/env bash
# Literature mining for: {brief.question}
# Run from the repository root. Requires `paperclip` on PATH.
set -euo pipefail

# ---------------------------------------------------------------------------
# DEFAULT PATH -- litkb: typed evidence and tool-bound sequences.
#
# Reads full text with `paperclip map` and emits EvidenceItem / ProtoArtifact
# records rather than grep lines. Costs LLM reads, which are capped per day.
# `-n` caps papers per query and is the cost dial -- start small.
#
# Must run from {LITKB_DIR}/: litkb's --registry and --project
# defaults are relative to that directory.
# ---------------------------------------------------------------------------
cd {cd_litkb_dir}

{litkb_plan_adopt}
{litkb_search}
{litkb_screen}
{litkb_dig}
{litkb_bind}
{litkb_evidence}
{litkb_report}
{litkb_manifest}
cd -

# Every evidence item lands with testable_by.requires_new_evaluator =
# "unassessed". Run `litkb label` to assign vocabulary terms from
# registry/property_vocabulary.json; until then no claim is made about what
# can test it.

# ---------------------------------------------------------------------------
# ALTERNATIVE PATH -- paperclip_kb.py: regex grep, no LLM read quota.
#
# Cheaper reconnaissance over the same corpus. Emits a categorized knowledge
# base rather than typed records. Use when the daily read cap matters more
# than machine-consumable output.
# ---------------------------------------------------------------------------

# 1. Dry run. Validates plan_{slug}.json through the shared brief-plan
#    contract and prints every search command without issuing one.
{dry}

# 2. Real run, same reviewed plan. This one searches.
{live}

# Outputs land in {run_dir}/:
#   plan_{slug}.json            the phrases and patterns actually used
#   knowledge_base_{slug}.txt   categorized grep hits
#   manifest_{slug}.json        set id + evidence_status=discovery_only_unverified
"""


# --------------------------------------------------------------------------
# harvest contract
# --------------------------------------------------------------------------


def render_harvest(brief: DesignBrief) -> str:
    h = brief.harvest
    lines = [
        f"# Sequence harvest contract — {brief.slug}",
        "",
        f"**Question.** {brief.question}",
        "",
        "Read `knowledge_base_<slug>.txt` from the mining run. Every line in it is "
        "a **lead**, not evidence: it proves only that text matching a pattern was "
        "returned from the result set. Nothing becomes a shard candidate until the "
        "sequence has been opened and read in its source document.",
        "",
        "## Per-shard rules",
        "",
    ]
    for rule in h.per_shard:
        shard = brief.shard_by_id(rule.shard_id)
        title = f"{rule.shard_id} — {shard.name}" if shard else rule.shard_id
        lines += [f"### {title}", "", f"**Extract.** {rule.what_to_extract}", ""]
        if rule.expected_length_range:
            lines += [f"**Expected length.** {rule.expected_length_range}", ""]
        if rule.accept_if:
            lines.append("**Accept if all hold:**")
            lines += [f"- {item}" for item in rule.accept_if]
            lines.append("")
        if rule.reject_if:
            lines.append("**Reject if any holds:**")
            lines += [f"- {item}" for item in rule.reject_if]
            lines.append("")
        if shard and shard.search_handles:
            lines += [
                "**Literal search handles.** `" + "`, `".join(shard.search_handles) + "`",
                "",
            ]

    if h.record_fields:
        lines += ["## Record with every extracted sequence", ""]
        lines += [f"- `{field}`" for field in h.record_fields]
        lines.append("")
    if h.dedup_rules:
        lines += ["## Deduplication", ""]
        lines += [f"- {rule}" for rule in h.dedup_rules]
        lines.append("")
    if h.global_rules:
        lines += ["## Rules spanning all shards", ""]
        lines += [f"- {rule}" for rule in h.global_rules]
        lines.append("")

    lines += [
        "## Hand-off",
        "",
        "Emit one FASTA per shard, named `<shard_id>_candidates.fasta`, with the "
        "record fields above in the header line. Then follow "
        f"`proto_brief_{brief.slug}.md` for assembly and scoring.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# proto brief — the runbook for the downstream Modal agent
# --------------------------------------------------------------------------


def render_proto_brief(brief: DesignBrief) -> str:
    a = brief.assembly
    p = brief.proto
    order = " → ".join(a.construct_order) or "(unstated)"

    lines = [
        f"# Proto agent runbook — {brief.slug}",
        "",
        f"**Question.** {brief.question}",
        f"**Pathway.** {brief.frame.chosen_pathway}",
        "",
        "You are receiving per-shard FASTA files produced by the Paperclip "
        "harvest step. Assemble them, then run the cascade below in order. Follow "
        "`.claude/skills/proto-tools/SKILL.md` for every tool call: confirm the "
        "tool key with `search_tools` before use, call `get_tool_schema` before "
        "`run_tool`, and treat deployment and execution as billable actions "
        "needing explicit approval.",
        "",
        "> The tool keys below were chosen against a transcribed catalogue and",
        "> validated for spelling, not for availability. Confirm each one is",
        "> deployed before planning a run; if a key does not resolve, stop and",
        "> report it rather than substituting a different tool.",
        "",
        "## 1. Assemble",
        "",
        f"**Construct order (N→C).** {order}",
        "",
    ]

    if a.linkers:
        lines += [
            "**Linkers.**",
            "",
            "| between | sequence | type | why |",
            "|---|---|---|---|",
        ]
        for linker in a.linkers:
            kind = "rigid" if linker.rigid else "flexible"
            lines.append(
                f"| {linker.after_shard} → {linker.before_shard} | "
                f"`{linker.sequence}` | {kind} | {linker.rationale} |"
            )
        lines.append("")

    if a.trimming_rules:
        lines += ["**Trimming.**", ""] + [f"- {r}" for r in a.trimming_rules] + [""]
    if a.expression_tags:
        lines += ["**Tags.**", ""] + [f"- {t}" for t in a.expression_tags] + [""]
    if a.combinatorial_plan:
        lines += [f"**Variants.** {a.combinatorial_plan}", ""]
    if a.fasta_outputs:
        lines += ["**Produce these files before gate 1:**", ""]
        lines += [f"- `{f}`" for f in a.fasta_outputs]
        lines.append("")
    if a.notes:
        lines += ["**Notes.**", ""] + [f"- {n}" for n in a.notes] + [""]

    lines += [
        "## 2. Fitness cascade",
        "",
        "Run in order. Each gate is a hard filter: only survivors continue. "
        "Ordering is cheap-first by construction — do not reorder to \"get a "
        "better signal early\", it inverts the compute budget.",
        "",
        "| # | gate | tools | state | condition | cost | kill rule |",
        "|---|------|-------|-------|-----------|------|-----------|",
    ]
    for gate in p.ordered():
        tools = ", ".join(f"`{k}`" for k in gate.tool_keys)
        decisive = " **(decisive)**" if gate.decisive else ""
        lines.append(
            f"| {gate.order} | {gate.name}{decisive} | {tools} | "
            f"{gate.state.value} | `{gate.condition()}` | {gate.cost_tier} | "
            f"{gate.kill_rule} |"
        )
    lines.append("")

    for gate in p.ordered():
        lines += [
            f"### Gate {gate.order} — {gate.name}",
            "",
            f"**Purpose.** {gate.purpose}",
            "",
            f"**Input.** {gate.input_description}",
            "",
            f"**Pass condition.** `{gate.condition()}` on state `{gate.state.value}`",
            "",
            f"**Kill rule.** {gate.kill_rule}",
            "",
        ]
        if gate.on_failure:
            lines += [f"**If it fails.** {gate.on_failure}", ""]
        if gate.caveat:
            lines += [f"**Caveat.** {gate.caveat}", ""]

    lines += [
        "## 3. Rank the survivors",
        "",
        f"```\n{p.ranking_expression}\n```",
        "",
    ]
    if p.ranking_rationale:
        lines += [p.ranking_rationale, ""]

    lines += ["## 4. Operational rules", ""]
    for note in p.deployment_notes:
        lines.append(f"- {note}")
    lines += [
        "- Write outputs to `proto/outputs/<UTC-timestamp>-<tool-key>/` and pass "
        "that path as `output_dir`.",
        "- Deploy tools one at a time into `main`, never the full catalogue, and "
        "get explicit approval first — deployment and persistent storage cost money.",
        "- Save sanitized `request.json` and `result.json` beside generated "
        "artifacts. Never write credentials or gated-model tokens into them.",
        "- Report the tool key, the actual `ran_on` backend, and the citation from "
        "`get_tool_info` for every scientific run.",
        "",
        "## 5. What these numbers do not tell you",
        "",
    ]
    for limit in p.known_limitations:
        lines.append(f"- {limit}")
    lines += [
        "- An unvalidated computational score is not experimental evidence and not "
        "a calibrated ranking signal. The cascade orders candidates for synthesis; "
        "it does not predict that any of them work.",
        "- Sequences reaching this runbook came from literature mining whose "
        "manifest declares `evidence_status: discovery_only_unverified`. That "
        "status is inherited by everything built from them.",
    ]
    if brief.frame.simulability_note:
        lines.append(
            f"- **Unscoreable step in this pathway:** {brief.frame.simulability_note}"
        )
    lines.append("")
    if brief.validation_warnings:
        lines += ["## 6. Unresolved warnings from brief generation", ""]
        lines += [f"- {w}" for w in brief.validation_warnings]
        lines.append("")
    return "\n".join(lines)
