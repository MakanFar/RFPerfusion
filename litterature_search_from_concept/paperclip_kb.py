#!/usr/bin/env python3
"""
paperclip_kb.py -- concept -> corpus -> knowledge base

Pipeline:
  1. Domain expert writes a protein-design concept (free text).
  2. Claude turns it into (a) phrase-search shards, (b) mechanism grep patterns.
  3. paperclip search  -> accumulating tagged set, ID scraped from stdout.
  4. paperclip grep    -> categorized hits into knowledge_base_<slug>.txt

Structural patterns (sequences, accessions, PDB, mutations) are hardcoded --
they do not vary by concept and an LLM only degrades them.

Usage:
    python paperclip_kb.py concept.txt --slug rfp --dry-run
    python paperclip_kb.py concept.txt --slug rfp
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MODEL = os.environ.get("LIT_MODEL", "claude-sonnet-4-6")
SET_ID_RE = re.compile(r"\bs_[0-9a-f]{6,}\b")
SAFE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


# ----------------------------------------------------------------------
# Stage 2: Claude plans the queries
# ----------------------------------------------------------------------

PLANNER_SYSTEM = """You plan literature-mining queries for protein engineering.

Given a design concept, return ONLY a JSON object, no preamble, no markdown
fences, with exactly these keys:

  "search_phrases":     8-14 strings. Each is a multi-word noun phrase that
                        would appear VERBATIM in the title or abstract of a
                        relevant paper. These are used with exact phrase
                        matching, so they must be phrases real authors write --
                        not question forms, not conjunctions of concepts.
                        Span the concept's sub-problems rather than restating
                        it 12 ways.

  "mechanism_patterns": 12-20 strings. Case-insensitive substrings that flag a
                        sentence as carrying MECHANISTIC content: the physical
                        or chemical basis of the behavior, structure-function
                        links, rate-limiting steps, failure modes. Prefer
                        distinctive multi-word fragments over single words.
                        "excited-state proton transfer" is useful;
                        "protein" is not.

  "notes":              one or two sentences on what you deliberately excluded
                        and why, for the human to sanity-check.
"""


def validate_plan(plan: object) -> dict:
    if not isinstance(plan, dict):
        raise TypeError("plan must be a JSON object")
    required = {"search_phrases", "mechanism_patterns", "notes"}
    missing = required - plan.keys()
    if missing:
        raise ValueError(f"plan is missing keys: {', '.join(sorted(missing))}")
    for key in ("search_phrases", "mechanism_patterns"):
        values = plan[key]
        if not isinstance(values, list) or not values:
            raise ValueError(f"{key} must be a non-empty list")
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise ValueError(f"{key} must contain non-empty strings")
    if not isinstance(plan["notes"], str):
        raise TypeError("notes must be a string")
    return plan


def plan_queries(concept: str) -> dict:
    try:
        import anthropic
    except ImportError:
        sys.exit("pip install anthropic")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=PLANNER_SYSTEM,
        messages=[{"role": "user", "content": concept}],
    )
    raw = "".join(b.text for b in resp.content if b.type == "text")
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    return validate_plan(json.loads(raw))


# ----------------------------------------------------------------------
# Fixed structural patterns -- concept-independent
# ----------------------------------------------------------------------
# NOTE: verify your grep engine before trusting these. Run:
#   paperclip grep --from <id> -e "[ACDEFGHIKLMNPQRSTVWY]{25,}"
# If that returns nothing but the literal-string patterns work, the engine is
# BRE or fixed-string; switch to the BRE column or add -E if supported.

STRUCTURAL = {
    "sequence": [
        r"[ACDEFGHIKLMNPQRSTVWY]{25,}",  # raw AA runs in body text
        "amino acid sequence",
        "sequence is available",
        "Supplementary Sequence",
        "codon-optimized",
        "synthesized as a gBlock",
    ],
    "database_id": [
        r"[OPQ][0-9][A-Z0-9]{3}[0-9]",  # UniProt, one form
        r"[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9]",  # UniProt, other form
        r"[NX][MPR]_[0-9]{6,}",  # RefSeq
        r"PDB[ :]?[0-9][A-Za-z0-9]{3}",
        r"EC [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+",
        "Addgene",
        "accession",
        "deposited in the Protein Data Bank",
    ],
    "mutation": [
        r"\b[ACDEFGHIKLMNPQRSTVWY][0-9]{1,4}[ACDEFGHIKLMNPQRSTVWY]\b",
        "site-directed mutagenesis",
        "saturation mutagenesis",
        "single point mutation",
    ],
    "quantitative": [
        "quantum yield",
        "extinction coefficient",
        "dissociation constant",
        "catalytic efficiency",
        "melting temperature",
        r"[Kk]cat",
        r"K[dDmM] of",
    ],
}


# ----------------------------------------------------------------------
# Stage 3: search, scraping the set ID
# ----------------------------------------------------------------------


def host_env() -> dict[str, str]:
    """Keep Paperclip's launcher outside an active project virtualenv."""
    env = dict(os.environ)
    venv = env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    if venv:
        venv_bin = str(Path(venv) / "bin")
        env["PATH"] = os.pathsep.join(
            part
            for part in env.get("PATH", "").split(os.pathsep)
            if part and part != venv_bin
        )
    return env


def run(cmd: list, dry: bool) -> str:
    print(f"  $ {' '.join(cmd)}", file=sys.stderr)
    if dry:
        return ""
    p = subprocess.run(
        cmd, capture_output=True, text=True, env=host_env(), timeout=420, check=False
    )
    if p.returncode != 0:
        sys.exit(f"FAILED ({p.returncode}):\n{p.stderr}")
    return p.stdout


def search_all(
    phrases: list[str], tag: str, n: int, sources: list[str], dry: bool
) -> str | None:
    set_id = None
    for source in sources:
        for phrase in phrases:
            out = run(
                [
                    "paperclip",
                    "search",
                    "-s",
                    source,
                    "--tag",
                    tag,
                    "-n",
                    str(n),
                    "-e",
                    phrase,
                ],
                dry,
            )
            found = SET_ID_RE.findall(out)
            if found:
                set_id = found[-1]  # last mention = accumulating tagged set
    return set_id


# ----------------------------------------------------------------------
# Stage 4: categorized grep
# ----------------------------------------------------------------------


def build_kb(set_id: str, mechanism: list, outpath: Path, dry: bool) -> None:
    categories = {"mechanism": mechanism, **STRUCTURAL}
    seen_global = set()

    with outpath.open("w") as fh:
        fh.write(
            f"# knowledge base :: set {set_id} :: "
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n"
        )

        for cat, patterns in categories.items():
            cmd = ["paperclip", "grep", "--from", set_id, "-i", "-n"]
            for p in patterns:
                cmd += ["-e", p]
            out = run(cmd, dry)

            fh.write(
                f"\n\n{'=' * 70}\n## {cat.upper()}  "
                f"({len(patterns)} patterns)\n{'=' * 70}\n"
            )
            kept = 0
            for line in out.splitlines():
                line = line.rstrip()
                if not line or line in seen_global:
                    continue  # a sentence can hit several categories
                seen_global.add(line)
                fh.write(line + "\n")
                kept += 1
            fh.write(f"\n[{kept} unique lines]\n")
            print(f"  {cat:<14} {kept} lines", file=sys.stderr)


# ----------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("concept", type=Path, help="text file with the design task")
    ap.add_argument("--slug", required=True, help="short name; drives tag + outfile")
    ap.add_argument("-n", type=int, default=500)
    ap.add_argument(
        "--sources",
        default="pmc,biorxiv",
        help="comma-separated Paperclip sources; queried separately",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="directory for the plan, knowledge base, and manifest",
    )
    ap.add_argument(
        "--plan-file",
        type=Path,
        help="reuse a reviewed plan JSON instead of asking Claude to plan again",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="print commands, run only the Claude planning step",
    )
    ap.add_argument("--set-id", help="skip search, grep an existing set")
    args = ap.parse_args()

    if not SAFE_SLUG_RE.fullmatch(args.slug):
        ap.error("--slug must contain only lowercase letters, digits, and hyphens")
    sources = [source.strip() for source in args.sources.split(",") if source.strip()]
    if not sources:
        ap.error("--sources must contain at least one source")

    concept = args.concept.read_text()
    tag = f"{args.slug}_literature"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = args.output_dir / f"plan_{args.slug}.json"

    print("[1/3] planning queries", file=sys.stderr)
    if args.plan_file:
        plan = validate_plan(json.loads(args.plan_file.read_text(encoding="utf-8")))
    else:
        plan = plan_queries(concept)
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(
        f"      {len(plan['search_phrases'])} phrases, "
        f"{len(plan['mechanism_patterns'])} mechanism patterns",
        file=sys.stderr,
    )
    print(f"      note: {plan.get('notes', '')}", file=sys.stderr)

    print("[2/3] searching", file=sys.stderr)
    set_id = args.set_id or search_all(
        plan["search_phrases"], tag, args.n, sources, args.dry_run
    )

    if not set_id:
        if args.dry_run:
            print(
                f"\ndry run: inspect {plan_path}, then rerun with "
                f"--plan-file {plan_path}",
                file=sys.stderr,
            )
            return
        sys.exit(
            "no set ID found in search output -- check SET_ID_RE against "
            "what `paperclip search` actually prints"
        )
    print(f"      set: {set_id}", file=sys.stderr)

    print("[3/3] building knowledge base", file=sys.stderr)
    out = args.output_dir / f"knowledge_base_{args.slug}.txt"
    build_kb(set_id, plan["mechanism_patterns"], out, args.dry_run)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "concept_file": str(args.concept),
        "slug": args.slug,
        "model": MODEL,
        "sources": sources,
        "paper_limit_per_search": args.n,
        "set_id": set_id,
        "plan_file": str(plan_path),
        "knowledge_base_file": str(out),
        "evidence_status": "discovery_only_unverified",
    }
    manifest_path = args.output_dir / f"manifest_{args.slug}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\n-> {out}", file=sys.stderr)
    print(f"-> {manifest_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
