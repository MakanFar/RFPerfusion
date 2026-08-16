"""Regression tests for the verification guarantee.

The claim this project makes to a scientist is: *if it is shown as a verified
quote, that text really is in that paper and really does support the claim.*
These tests are what backs that claim, so they exercise the adversarial cases
directly — fabricated quotes, altered quantities, and quotes lifted from the
wrong paper.

The quote tests hit the live Paperclip corpus. Run with:

    uv run pytest tests/ -v
"""

from __future__ import annotations

import asyncio

import pytest

from formulation_agent.models import (
    Citation,
    Claim,
    Evidence,
    Idea,
    LineRef,
    SupportLevel,
    Verification,
)
from formulation_agent.paperclip import Paperclip, verify_against_line
from formulation_agent.scoring import JudgedAxes, assemble, compute_grounding, grounding_cap

# A paragraph that exists verbatim in this bioRxiv preprint (line L18).
DOC = "bio_f12fb9b76c4b"
REAL = (
    "The coiled-coil domain of TlpA undimerizes and uncoils above a temperature "
    "of ~42°C, causing unbinding from the operator"
)


# --------------------------------------------------------------------------
# pure unit tests — no network
# --------------------------------------------------------------------------


class TestVerifyAgainstLine:
    SOURCE = (
        "The coiled-coil domain of TlpA undimerizes and uncoils above a "
        "temperature of ~42°C, causing unbinding from the operator and "
        "transcriptional de-repression."
    )

    def test_exact_quote_accepted(self):
        ok, _ = verify_against_line(REAL, self.SOURCE)
        assert ok

    def test_typographic_drift_accepted(self):
        """Em-dash and a space before the degree sign are cosmetic."""
        ok, _ = verify_against_line(
            "The coiled—coil domain of TlpA undimerizes and uncoils above a "
            "temperature of ~42 °C",
            self.SOURCE,
        )
        assert ok

    def test_altered_quantity_rejected(self):
        """The single most damaging failure mode: a changed number."""
        ok, reason = verify_against_line(REAL.replace("42", "55"), self.SOURCE)
        assert not ok
        assert "55" in reason

    def test_added_quantity_rejected(self):
        ok, reason = verify_against_line(
            "uncoils above a temperature of ~42°C over a 3.5 °C window", self.SOURCE
        )
        assert not ok
        assert "3.5" in reason

    def test_altered_meaning_rejected(self):
        ok, _ = verify_against_line(
            "The coiled-coil domain of TlpA undimerizes and uncoils above a "
            "temperature of ~42°C, causing irreversible covalent denaturation",
            self.SOURCE,
        )
        assert not ok

    def test_unrelated_text_rejected(self):
        ok, _ = verify_against_line("TlpA absorbs 1550 nm light directly", self.SOURCE)
        assert not ok


class TestGroundingCap:
    """An ungrounded idea must not be able to outrank a grounded one."""

    @staticmethod
    def _idea(idea_id: str, verified: bool) -> Idea:
        ev = Evidence(
            quote="x" * 40,
            ref=LineRef(doc_id="PMC1", start_line=1, end_line=1),
            citation=Citation(doc_id="PMC1"),
            support_level=SupportLevel.ESTABLISHED,
        )
        ev.verification = Verification.VERIFIED if verified else Verification.UNSUPPORTED
        return Idea(
            id=idea_id,
            title=idea_id,
            claims=[Claim(id=f"{idea_id}.C1", text="t", evidence=[ev], searched=True)],
        )

    def test_grounded_modest_beats_ungrounded_brilliant(self):
        grounded = assemble(
            self._idea("A", True),
            JudgedAxes(
                mechanistic_plausibility=0.5, novelty=0.5, testability=0.5, rationale=""
            ),
        )
        ungrounded = assemble(
            self._idea("B", False),
            JudgedAxes(
                mechanistic_plausibility=1.0, novelty=1.0, testability=1.0, rationale=""
            ),
        )
        assert grounded.overall > ungrounded.overall

    def test_ungrounded_is_capped(self):
        assert grounding_cap(0.0, refuted=False) < 0.5

    def test_refuted_is_capped_hardest(self):
        assert grounding_cap(1.0, refuted=True) < grounding_cap(0.0, refuted=False)

    def test_partial_counts_half(self):
        ev = Evidence(
            quote="x" * 40,
            ref=LineRef(doc_id="PMC1", start_line=1, end_line=1),
            citation=Citation(doc_id="PMC1"),
        )
        ev.verification = Verification.PARTIAL
        claim = Claim(id="c", text="t", evidence=[ev], searched=True)
        assert compute_grounding([claim]) == 0.5

    def test_supporting_claims_do_not_count_toward_grounding(self):
        claim = Claim(id="c", text="t", load_bearing=False, searched=True)
        assert compute_grounding([claim]) == 0.0


# --------------------------------------------------------------------------
# live corpus — the adversarial suite
# --------------------------------------------------------------------------


@pytest.mark.live
class TestLiveQuoteCheck:
    @staticmethod
    def _check(quote: str):
        return asyncio.run(Paperclip(concurrency=2).locate_quote(DOC, quote))

    def test_real_quote_found_with_correct_line(self):
        result = self._check(REAL)
        assert result.found
        assert result.line == 18  # located, not taken on trust

    def test_fabricated_quote_rejected(self):
        result = self._check(
            "TlpA absorbs 1550 nm infrared light directly via an engineered "
            "biliverdin chromophore"
        )
        assert not result.found

    def test_quote_from_a_different_paper_rejected(self):
        result = self._check(
            "Metadynamics simulations with restraints were used to study "
            "coiled-coil protein topology"
        )
        assert not result.found

    def test_altered_quantity_rejected_live(self):
        result = self._check(REAL.replace("42", "55"))
        assert not result.found
        assert "55" in result.reason


# --------------------------------------------------------------------------
# schema hygiene — the failure that discarded a completed 6-minute generation
# --------------------------------------------------------------------------


class TestNoUnsupportedConstraints:
    """Response models must not carry constraints the API cannot enforce.

    Anthropic structured outputs do not support string `maxLength` or array
    `maxItems`. The SDK strips them from the schema sent to the model and then
    validates client-side, so the model never learns the limit, writes past it,
    and a finished — already paid for — generation is thrown away.

    This cost a real session (`ChatReply.reply` capped at 2000 chars), so it is
    checked mechanically rather than left to review.
    """

    @staticmethod
    def _models():
        from formulation_agent.agent import (
            ChatReply,
            ExpandedIdea,
            Outline,
            OutlineIdea,
            ProposedClaim,
        )
        from formulation_agent.followup import SubClaim, SubQuestions, Synthesis
        from formulation_agent.grounding import EntailmentVerdict
        from formulation_agent.scoring import JudgedAxes

        return [
            ChatReply, ExpandedIdea, Outline, OutlineIdea, ProposedClaim,
            SubClaim, SubQuestions, Synthesis, EntailmentVerdict, JudgedAxes,
        ]

    def test_no_length_constraints_anywhere(self):
        offenders = []
        for model in self._models():
            for name, field in model.model_fields.items():
                for meta in field.metadata:
                    if any(
                        hasattr(meta, attr)
                        for attr in ("max_length", "max_items", "max_inclusive")
                    ):
                        offenders.append(f"{model.__name__}.{name}: {meta!r}")
        assert not offenders, (
            "These carry API-unenforceable length limits that silently discard "
            "valid model output:\n  " + "\n  ".join(offenders)
        )

    def test_numeric_bounds_are_kept(self):
        """`ge`/`le` on scores ARE supported and are correctness-critical."""
        from formulation_agent.scoring import JudgedAxes

        assert JudgedAxes.model_fields["novelty"].metadata, (
            "numeric bounds on scoring axes were removed — scores could exceed 1.0"
        )

    def test_long_chat_reply_validates(self):
        """The exact payload shape that failed in production."""
        from formulation_agent.agent import ChatReply

        assert len(ChatReply(reply="x" * 20_000).reply) == 20_000
