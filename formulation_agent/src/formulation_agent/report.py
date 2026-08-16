"""Session persistence: machine-readable JSON + a citable markdown report.

The markdown report is the artifact a scientist actually reads or pastes into a
write-up, so it follows Paperclip's citation conventions: numbered `[N]` inline
markers and a REFERENCES block with line-pinned URLs.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .models import Citation, Idea, Session, Verification


def save_session(session: Session, out_dir: str) -> list[Path]:
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = session.created_at.strftime("%Y%m%d-%H%M%S")

    json_path = directory / f"session-{stamp}.json"
    json_path.write_text(session.model_dump_json(indent=2), encoding="utf-8")

    md_path = directory / f"report-{stamp}.md"
    md_path.write_text(render_markdown(session), encoding="utf-8")
    return [json_path, md_path]


class _Refs:
    """Assigns [N] numbers in order of first appearance."""

    def __init__(self) -> None:
        self._order: list[Citation] = []
        self._index: dict[str, int] = {}

    def cite(self, citation: Citation) -> int:
        if citation.doc_id not in self._index:
            self._order.append(citation)
            self._index[citation.doc_id] = len(self._order)
        return self._index[citation.doc_id]

    def block(self, session: Session) -> str:
        if not self._order:
            return ""
        lines = ["", "--------", "REFERENCES", ""]
        anchors = _anchors(session)
        for n, citation in enumerate(self._order, 1):
            url = anchors.get(citation.doc_id, "")
            lines.append(f"[{n}] {citation.formatted()}")
            if url:
                lines.append(f"    {url}")
        return "\n".join(lines)


def _anchors(session: Session) -> dict[str, str]:
    """First verified line-pin seen for each document."""
    out: dict[str, str] = {}
    for idea in session.ideas:
        for ev in idea.all_evidence:
            if ev.quote_found and ev.citation.doc_id not in out:
                out[ev.citation.doc_id] = ev.ref.citation_url
    return out


def render_markdown(session: Session) -> str:
    refs = _Refs()
    lines: list[str] = [
        "# Formulation report",
        "",
        f"**Question.** {session.question or '(none)'}",
        "",
        f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}. "
        "Every quoted claim below was checked twice: the quote was located "
        "verbatim in the cited paper, and a separate model — shown only the "
        "claim and the passage — judged whether the passage supports it. "
        "Claims that failed either check are listed as failures rather than "
        "silently dropped.*",
        "",
        "## Ranked directions",
        "",
        "| # | id | direction | confidence | grounded | verdict |",
        "|---|----|-----------|-----------|----------|---------|",
    ]

    ranked = session.ranked()
    for rank, idea in enumerate(ranked, 1):
        s = idea.score
        lb = idea.load_bearing_claims
        ok = sum(1 for c in lb if c.status is Verification.VERIFIED)
        lines.append(
            f"| {rank} | {idea.id} | {idea.title} | "
            f"{s.overall:.2f}{' (capped)' if s and s.cap_applied else ''} | "
            f"{ok}/{len(lb)} | {s.recommendation.value if s else '—'} |"
        )

    for idea in ranked:
        lines += _render_idea(idea, refs)

    dropped = [i for i in session.ideas if i.status.value == "dropped"]
    if dropped:
        lines += ["", "## Dropped", ""]
        for idea in dropped:
            lines.append(f"- **{idea.id}** {idea.title} — _{idea.drop_reason}_")

    if session.followups:
        lines += ["", "## Follow-up investigations", ""]
        for r in session.followups:
            lines += [
                f"### {r.job_id} · {r.idea_id} — {r.verdict or r.status.value}",
                "",
                f"**Question.** {r.question}",
                "",
                r.answer or f"_{r.error or 'no answer'}_",
                "",
            ]

    lines.append(refs.block(session))
    return "\n".join(lines) + "\n"


def _render_idea(idea: Idea, refs: _Refs) -> list[str]:
    s = idea.score
    out = ["", f"## {idea.id} — {idea.title}", ""]
    if idea.one_liner:
        out += [idea.one_liner, ""]
    if idea.mechanism_chain:
        out += [f"**Mechanism.** {' → '.join(idea.mechanism_chain)}", ""]
    if s:
        out += [
            f"**Confidence {s.overall:.2f}** · {s.recommendation.value}  ",
            f"grounding {s.grounding:.0%} · evidence {s.evidence_strength:.2f} · "
            f"plausibility {s.mechanistic_plausibility:.2f} · "
            f"novelty {s.novelty:.2f} · testability {s.testability:.2f}",
            "",
        ]
        if s.cap_applied:
            out += [
                f"> Score capped at {s.grounding_cap:.2f}: load-bearing claims are "
                "not verified.",
                "",
            ]
        if s.rationale:
            out += [s.rationale, ""]

    out += ["**Claims.**", ""]
    for claim in idea.claims:
        badge = {
            Verification.VERIFIED: "VERIFIED",
            Verification.PARTIAL: "PARTIAL",
            Verification.UNSUPPORTED: "UNSUPPORTED",
            Verification.QUOTE_MISMATCH: "QUOTE NOT FOUND",
            Verification.NO_EVIDENCE: "NOT RETRIEVED",
            Verification.ERROR: "RETRIEVAL FAILED",
        }[claim.status]
        role = "" if claim.load_bearing else " _(supporting)_"
        out.append(f"- **[{badge}]** {claim.text}{role}")
        for ev in claim.evidence:
            if not (ev.is_grounding or ev.refutes):
                continue
            n = refs.cite(ev.citation)
            prefix = "**Refutes.** " if ev.refutes else ""
            out.append(f'    - {prefix}> "{ev.quote}" [{n}]')
        if claim.status in {Verification.QUOTE_MISMATCH, Verification.UNSUPPORTED}:
            out.append(
                "    - _no citation survived verification — treat as unsupported_"
            )
    out.append("")

    if idea.key_risk:
        out += [f"**Key risk.** {idea.key_risk}", ""]
    if idea.testability_note:
        out += [f"**Testability.** {idea.testability_note}", ""]
    return out
