"""Turn an asserted claim into verified, line-pinned evidence.

Pipeline per claim:

    search  ->  structured extraction  ->  quote check  ->  entailment check

The last two steps are the point of the module, and they are deliberately
independent of the model that proposed the claim:

* **Quote check** is not a model call at all. We search the paper for the
  quoted text; if it isn't there, the evidence is discarded as a fabrication
  regardless of how plausible it reads. The line number is taken from the
  search result, so a correct quote with a wrong line number is *repaired*
  rather than rejected.

* **Entailment check** is a separate model call that sees only the claim and
  the retrieved passage — never the idea, its rationale, or why we went
  looking. It cannot be talked into agreeing by a persuasive framing it never
  sees.

Only evidence that clears both is allowed to raise an idea's score.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import BaseModel, Field

from .config import SETTINGS
from .llm import LLM, LLMError
from .models import (
    Citation,
    Claim,
    Evidence,
    EvidenceKind,
    LineRef,
    SupportLevel,
    Verification,
)
from .paperclip import Paperclip

# --------------------------------------------------------------------------
# extraction schema handed to `paperclip map --output-schema`
# --------------------------------------------------------------------------

# Deliberately does NOT ask for line numbers. `locate_quote` re-derives the true
# line by searching for the quote, precisely because a model-supplied line number
# can't be trusted — so any line number the reader produced was discarded unread.
#
# This is a correctness/clarity change, not a speed one: an A/B on a fixed
# six-paper set showed no reliable difference, and run-to-run variance on the
# same call (4.5s-14.5s) swamps any schema effect. The 62s map that prompted the
# investigation was slow from *contention*, not from the schema.
EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["assessment", "findings"],
    "properties": {
        "assessment": {
            "type": "string",
            "enum": ["supports", "partially_supports", "contradicts", "irrelevant"],
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "verbatim_quote",
                    "support_level",
                    "evidence_kind",
                    "stance",
                ],
                "properties": {
                    "verbatim_quote": {"type": "string"},
                    "support_level": {
                        "type": "string",
                        "enum": ["established", "contested", "speculative"],
                    },
                    "evidence_kind": {
                        "type": "string",
                        "enum": ["experimental", "computational", "review", "theoretical"],
                    },
                    "stance": {"type": "string", "enum": ["supports", "refutes"]},
                },
            },
        },
    },
}


def extraction_prompt(claim: str) -> str:
    return (
        f"CLAIM UNDER TEST:\n{claim}\n\n"
        "Decide whether THIS paper bears on the claim above.\n\n"
        "Rules:\n"
        "- `verbatim_quote` must be copied EXACTLY from the paper's text, "
        "character for character. Do not paraphrase, summarise, join separated "
        "sentences, or fix typography. A quote that cannot be found verbatim in "
        "the paper will be discarded and counted as a failure.\n"
        "- Do not report line numbers. Quote the text and nothing else; the "
        "location is resolved separately.\n"
        "- Include a finding with stance='refutes' if the paper contradicts the "
        "claim. Contradicting evidence is as valuable as supporting evidence.\n"
        "- `support_level` describes how settled the finding is *in this paper*: "
        "'established' for a directly measured/replicated result, 'contested' if "
        "the paper notes disagreement, 'speculative' for a proposal or hypothesis.\n"
        "- At most 2 findings per paper — the strongest ones.\n"
        "- If the paper does not bear on the claim, return assessment='irrelevant' "
        "and an empty findings array. Returning nothing is correct and expected; "
        "do not manufacture marginal support."
    )


# --------------------------------------------------------------------------
# entailment judge
# --------------------------------------------------------------------------


class EntailmentVerdict(BaseModel):
    entails: Literal["yes", "partial", "no"]
    contradicts: bool = False
    reason: str = ""


JUDGE_SYSTEM = (
    "You verify whether a passage from a scientific paper supports a specific claim.\n\n"
    "You are shown ONLY the claim and the passage. You have no other context, and "
    "you must not speculate about any. Judge strictly on what the passage states.\n\n"
    "  yes     — the passage states or directly entails the claim\n"
    "  partial — the passage supports part of the claim, or supports it only under "
    "conditions the claim does not state\n"
    "  no      — the passage does not support the claim\n\n"
    "Set contradicts=true only if the passage asserts something incompatible with "
    "the claim. Adjacent topic, similar vocabulary, or plausible-sounding overlap "
    "is NOT support: answer 'no'. Being strict here is the entire purpose of this "
    "check; a false 'yes' is far more damaging than a false 'no'."
)


class Grounder:
    """Grounds claims against the literature."""

    def __init__(self, pc: Paperclip, llm: LLM, settings=SETTINGS):
        self.pc = pc
        self.llm = llm
        self.s = settings

    # ------------------------------------------------------------------ api

    async def ground_claims(self, claims: list[Claim], progress=None) -> None:
        """Ground many claims, in place, a few at a time.

        Bounded rather than an unbounded gather: with every claim in flight at
        once they all contend for the same subprocess slots and advance in
        lockstep, so none *completes* until nearly all the work is done. That
        left the progress bar reading 0/24 for twenty minutes and then jumping
        to done. A small pool means claims finish steadily and their evidence
        reaches the page during the run.
        """
        sem = asyncio.Semaphore(self.s.claim_concurrency)

        async def one(claim: Claim) -> None:
            async with sem:
                await self.ground_claim(claim, progress)

        await asyncio.gather(*(one(c) for c in claims))

    async def ground_claim(self, claim: Claim, progress=None) -> Claim:
        try:
            evidence = await self._collect(claim)
        except Exception as exc:  # noqa: BLE001 — a failed claim must not kill the run
            claim.searched = True
            claim.evidence = []
            if progress:
                progress(claim, f"error: {type(exc).__name__}")
            return claim

        claim.evidence = evidence
        claim.searched = True
        if progress:
            progress(claim, claim.status.value)
        return claim

    # -------------------------------------------------------------- internals

    async def _collect(self, claim: Claim) -> list[Evidence]:
        """Retrieve with two complementary strategies, then verify everything.

        Semantic search finds topically-relevant work; boolean full-text search
        finds the papers that literally name the entity in the claim. Using only
        the first produces false "unverified" verdicts on claims the literature
        does in fact settle — the failure mode that would quietly make this whole
        tool useless.

        Searches are cheap (<1s) and run together; **reading** is what costs — a
        map over six papers is ~60s — so result sets are consumed one at a time,
        already-read documents are skipped, and the claim stops once it is
        settled. Mapping every set of every query was ~1,150 paper-reads a run.
        """
        queries = [q for q in (claim.search_queries or [claim.text]) if q.strip()]
        sources = self.s.source_list()

        jobs = [self.pc.search(queries[0], src, self.s.papers_per_claim) for src in sources]
        if claim.exact_terms:
            jobs.append(
                self.pc.search_exact(
                    claim.exact_terms[0], sources[0], self.s.papers_per_claim
                )
            )
        searches = await asyncio.gather(*jobs, return_exceptions=True)

        out: list[Evidence] = []
        seen_docs: set[str] = set()

        for result in searches:
            if isinstance(result, BaseException) or not result:
                continue

            # Nothing new to read in this set — skip the expensive part entirely.
            fresh = [h.doc_id for h in result.hits if h.doc_id not in seen_docs]
            if not fresh:
                continue
            seen_docs.update(fresh[: self.s.papers_per_map])

            try:
                per_doc = await self.pc.map_schema(
                    result.result_id,
                    extraction_prompt(claim.text),
                    EXTRACTION_SCHEMA,
                    known_ids=[h.doc_id for h in result.hits],
                    limit=self.s.papers_per_map,
                )
            except Exception:  # noqa: BLE001
                continue

            candidates = [
                (doc_id, finding)
                for doc_id, payload in per_doc.items()
                if payload.get("assessment") != "irrelevant"
                for finding in (payload.get("findings") or [])
                if finding.get("verbatim_quote")
            ]
            if not candidates:
                continue

            verified = await asyncio.gather(
                *(self._verify(claim, doc_id, f) for doc_id, f in candidates),
                return_exceptions=True,
            )
            out.extend(e for e in verified if isinstance(e, Evidence))

            # Settled: enough confirmed support to stand on. Every set is read
            # in full before this fires, so a refutation in the current set is
            # never skipped — and a claim that finds nothing still exhausts all
            # sets, keeping "not retrieved" as well-supported as before.
            if sum(1 for e in out if e.is_grounding) >= self.s.evidence_target:
                break

        if not out:
            return []

        # strongest first: verified supports, then partials, then refutations
        def rank(e: Evidence) -> tuple[int, int]:
            tier = 0 if e.is_grounding else (1 if e.verification is Verification.PARTIAL else 2)
            strength = {
                SupportLevel.ESTABLISHED: 0,
                SupportLevel.CONTESTED: 1,
                SupportLevel.SPECULATIVE: 2,
            }[e.support_level]
            return tier, strength

        out.sort(key=rank)
        return out[:6]

    async def _verify(self, claim: Claim, doc_id: str, finding: dict) -> Evidence:
        quote = (finding.get("verbatim_quote") or "").strip()

        ev = Evidence(
            quote=quote,
            # Placeholder: the real line comes from locating the quote below.
            ref=LineRef(doc_id=doc_id, start_line=0, end_line=0),
            citation=Citation(doc_id=doc_id),
            support_level=_enum(SupportLevel, finding.get("support_level"), SupportLevel.SPECULATIVE),
            evidence_kind=_enum(
                EvidenceKind, finding.get("evidence_kind"), EvidenceKind.EXPERIMENTAL
            ),
        )

        # --- layer 1: does this text actually exist in this paper? -----------
        check = await self.pc.locate_quote(doc_id, quote)
        ev.quote_found = check.found
        if not check.found:
            # Fabricated or altered — don't spend a subprocess on its citation.
            ev.verification = Verification.QUOTE_MISMATCH
            ev.entailment_note = check.reason
            return ev

        ev.ref = LineRef(doc_id=doc_id, start_line=check.line or 0, end_line=check.line or 0)
        ev.citation = await self.pc.citation(doc_id)

        # --- layer 2: does the real passage support the claim? ---------------
        # judge against the source text, never the model-supplied quote
        passage = check.line_text or quote
        try:
            verdict = await self.llm.structured(
                schema=EntailmentVerdict,
                system=JUDGE_SYSTEM,
                user=f"CLAIM:\n{claim.text}\n\nPASSAGE:\n{passage}",
                model=self.s.judge_model,
                max_tokens=self.s.judge_max_tokens,
                effort=self.s.judge_effort,
            )
        except LLMError as exc:
            ev.verification = Verification.ERROR
            ev.entailment_note = f"entailment check failed: {exc}"
            return ev

        ev.entailment = verdict.entails
        ev.entailment_note = verdict.reason
        ev.refutes = bool(verdict.contradicts) or finding.get("stance") == "refutes"

        if verdict.contradicts:
            # A verified contradiction is a real, reportable result.
            ev.verification = Verification.VERIFIED
        elif verdict.entails == "yes":
            ev.verification = Verification.VERIFIED
        elif verdict.entails == "partial":
            ev.verification = Verification.PARTIAL
        else:
            ev.verification = Verification.UNSUPPORTED
        return ev


def _enum(cls, value, default):
    try:
        return cls(value)
    except (ValueError, TypeError):
        return default
