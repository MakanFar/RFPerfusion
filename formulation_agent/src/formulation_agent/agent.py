"""The formulation agent.

Takes an open scientific question and returns a ranked set of directions, each
decomposed into claims that have been checked against the literature.

The prompt design matters as much as the code here. Two properties are enforced
by the system prompt and then re-checked downstream:

1. The agent proposes *claims*, not conclusions. Anything load-bearing has to
   be phrased as a single checkable proposition so that `grounding.py` can go
   and test it. "Use a thermal switch" is not a claim; "TlpA's coiled-coil
   uncoils above ~42 °C" is.
2. The agent is required to include directions that attack the premise of the
   question. An agent that only ever elaborates the user's framing is a
   sycophancy engine, and the most valuable output of a formulation step is
   often "the thing you asked for cannot work, here is why, here is the
   adjacent thing that can."

Proposal runs in **two stages**. `propose_outline()` returns just the
directions — title, one-liner, mechanism — from a small schema that comes back
in seconds, so the interface has real content to show immediately.
`expand_idea()` then decomposes each direction into claims, in parallel. A
single call producing everything at once took minutes, during which there was
nothing to display.

Note the absence of `max_length` on any response model. Anthropic's structured
outputs do not support string `maxLength`, so the SDK strips it from the schema
and validates client-side afterwards — meaning the model never learns the limit
and a completed, expensive generation gets discarded for exceeding it. Length
guidance belongs in the prompt, where the model can act on it.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from .config import SETTINGS
from .grounding import Grounder
from .llm import LLM
from .models import Claim, Idea, IdeaStatus, Session, Turn
from .paperclip import Paperclip
from .scoring import JUDGE_SYSTEM, JudgedAxes, assemble, evidence_digest

# --------------------------------------------------------------------------
# stage 1 — outline
# --------------------------------------------------------------------------


class OutlineIdea(BaseModel):
    title: str
    one_liner: str
    mechanism_chain: list[str] = Field(default_factory=list)
    rationale: str = ""


class Outline(BaseModel):
    reading_of_question: str
    ideas: list[OutlineIdea] = Field(default_factory=list)


# --------------------------------------------------------------------------
# stage 2 — expansion
# --------------------------------------------------------------------------


class ProposedClaim(BaseModel):
    text: str
    load_bearing: bool = True
    search_queries: list[str] = Field(default_factory=list)
    exact_terms: list[str] = Field(default_factory=list)


class ExpandedIdea(BaseModel):
    claims: list[ProposedClaim] = Field(default_factory=list)
    key_risk: str = ""
    testability_note: str = ""
    novelty_note: str = ""


class ChatReply(BaseModel):
    reply: str


# --------------------------------------------------------------------------
# prompts
# --------------------------------------------------------------------------

OUTLINE_SYSTEM = """You are a formulation agent for a protein-engineering group. \
A scientist gives you an open, underspecified design question. Your job is to turn \
it into concrete, checkable research directions — NOT to answer the question.

Propose {n} directions that are genuinely different from each other. Different \
means a different physical mechanism or a different reframing of the problem, not \
the same idea with a different protein swapped in.

At least one direction must CHALLENGE THE PREMISE. If the thing literally asked \
for is physically impossible or thermodynamically ruled out, say so as a direction \
in its own right, and state what the nearest achievable reframing is. Do not \
quietly substitute the reframing and present it as though it were what was asked.

For each direction give:
  title            — a specific noun phrase, under about 10 words
  one_liner        — one sentence a scientist could disagree with
  mechanism_chain  — 3-6 short steps from stimulus to biological effect
  rationale        — two or three sentences on why this is worth considering

Keep `reading_of_question` to two or three sentences: how you are interpreting \
the question, and any ambiguity that changes what counts as success.

Be concise throughout. Each direction is expanded separately afterwards, so this \
is not the place to elaborate."""


EXPAND_SYSTEM = """You are decomposing one proposed research direction into \
factual claims that a literature search can confirm or refute.

A claim is ONE factual proposition, specific enough that a paper could contradict \
it. State numbers wherever you can — a claim with a quantity in it is checkable, a \
qualitative claim usually is not.

  good:  "Water's absorption coefficient at 1550 nm is approximately 10 cm^-1"
  good:  "No known biological chromophore has an electronic transition below 1.2 eV"
  bad:   "Thermal switches are useful"           (not checkable)
  bad:   "We should use a coiled-coil scaffold"  (a decision, not a fact)

Give 2-4 claims. For each:

  load_bearing   — true if the direction collapses when the claim is false. Be
                   honest: marking everything load-bearing makes the ranking
                   meaningless, and so does marking nothing.
  search_queries — 1-2 queries for a biomedical search engine. Topical noun
                   phrases carrying the specific quantities or entity names.
                   Not questions, not full sentences.
  exact_terms    — the literal names a relevant paper would contain: protein,
                   gene, reagent or technique names such as "TlpA",
                   "bacteriophytochrome", "infrared neural stimulation". These
                   are matched verbatim against full text, so give the exact
                   string with no description. Omit if the claim names no
                   distinctive entity.

Also give `key_risk`, `testability_note` and `novelty_note` — one or two sentences \
each, no more.

Your claims will be checked against full text by an independent process. Claims \
you are unsure about are fine and expected — mark them and let the search settle \
it. Inventing a plausible number is the one unrecoverable mistake, because it will \
be checked and it will fail."""


CHAT_SYSTEM = """You are a formulation agent in conversation with a scientist about \
research directions you proposed. You have the current state of every idea, \
including which of its claims survived independent verification against the \
literature and which did not.

Be direct and specific. Reference ideas by their id. When the scientist pushes \
back, engage with the substance rather than immediately conceding — but if they \
are right, say so plainly and say what it changes.

Keep replies short: a few sentences, or a brief list when comparing directions. \
This is a conversation panel beside the ideas, not a report — the evidence is \
already on screen and does not need restating.

Never assert a fact as established unless it appears in the verified evidence you \
have been given. If you are reasoning past the evidence, say that you are."""


class FormulationAgent:
    def __init__(self, llm: LLM, pc: Paperclip, settings=SETTINGS):
        self.llm = llm
        self.pc = pc
        self.s = settings
        self.grounder = Grounder(pc, llm, settings)

    # --------------------------------------------------------------- stage 1

    async def propose_outline(
        self, session: Session, extra_context: str = "", n: int | None = None
    ) -> tuple[list[Idea], str]:
        """Directions only — no claims yet.

        Runs at the highest effort of any call in the system: choosing *which*
        directions to pursue is the highest-judgement step, and everything else
        in the session is built on it.
        """
        n = n or self.s.n_ideas
        user = f"SCIENTIST'S QUESTION:\n{session.question}\n"
        history = self._history(session)
        if history:
            user += f"\nCONVERSATION SO FAR:\n{history}\n"
        existing = self._existing_titles(session)
        if existing:
            user += (
                f"\nDIRECTIONS ALREADY ON THE TABLE (propose genuinely different "
                f"ones):\n{existing}\n"
            )
        if extra_context:
            user += f"\nADDITIONAL CONTEXT:\n{extra_context}\n"

        result = await self.llm.structured(
            schema=Outline,
            system=OUTLINE_SYSTEM.format(n=n),
            user=user,
            effort=self.s.propose_effort,
        )

        ideas: list[Idea] = []
        for outlined in result.ideas:
            idea_id = f"I{len(session.ideas) + len(ideas) + 1}"
            ideas.append(
                Idea(
                    id=idea_id,
                    title=outlined.title,
                    one_liner=outlined.one_liner,
                    mechanism_chain=outlined.mechanism_chain,
                    rationale=outlined.rationale,
                )
            )
        return ideas, result.reading_of_question

    # --------------------------------------------------------------- stage 2

    async def expand_idea(self, session: Session, idea: Idea) -> Idea:
        """Decompose one direction into checkable claims. Mutates in place."""
        user = (
            f"SCIENTIST'S QUESTION:\n{session.question}\n\n"
            f"DIRECTION: {idea.title}\n"
            f"{idea.one_liner}\n"
            f"MECHANISM: {' -> '.join(idea.mechanism_chain) or 'n/a'}\n"
            f"RATIONALE: {idea.rationale}"
        )
        try:
            expanded = await self.llm.structured(
                schema=ExpandedIdea,
                system=EXPAND_SYSTEM,
                user=user,
                effort=self.s.expand_effort,
            )
        except Exception:  # noqa: BLE001 — one failed expansion must not kill the run
            idea.key_risk = idea.key_risk or "could not decompose this direction"
            return idea

        idea.key_risk = expanded.key_risk or idea.key_risk
        idea.testability_note = expanded.testability_note
        idea.novelty_note = expanded.novelty_note
        idea.claims = [
            Claim(
                id=f"{idea.id}.C{ci + 1}",
                text=c.text,
                load_bearing=c.load_bearing,
                search_queries=c.search_queries or [c.text],
                exact_terms=c.exact_terms,
            )
            for ci, c in enumerate(expanded.claims[: self.s.max_claims_per_idea])
        ]
        return idea

    async def expand_all(self, session: Session, ideas: list[Idea]) -> None:
        """Expand every direction concurrently."""
        await asyncio.gather(*(self.expand_idea(session, i) for i in ideas))

    async def propose(
        self, session: Session, extra_context: str = "", n: int | None = None
    ) -> tuple[list[Idea], str]:
        """Both stages. For callers that don't render intermediate state."""
        ideas, reading = await self.propose_outline(session, extra_context, n)
        await self.expand_all(session, ideas)
        return ideas, reading

    # ----------------------------------------------------------- ground+score

    async def ground_and_score(self, ideas: list[Idea], progress=None) -> None:
        """Verify every claim, then score every idea. Mutates in place."""
        claims = [c for idea in ideas for c in idea.claims]
        await self.grounder.ground_claims(claims, progress)
        await asyncio.gather(*(self.score(idea) for idea in ideas))

    async def score(self, idea: Idea) -> Idea:
        digest = evidence_digest(idea)
        user = (
            f"IDEA: {idea.title}\n"
            f"{idea.one_liner}\n\n"
            f"MECHANISM: {' -> '.join(idea.mechanism_chain) or 'n/a'}\n\n"
            f"RATIONALE (do not let this move your score):\n{idea.rationale}\n\n"
            f"VERIFIED EVIDENCE:\n{digest or '(none)'}\n"
        )
        try:
            axes = await self.llm.structured(
                schema=JudgedAxes,
                system=JUDGE_SYSTEM,
                user=user,
                model=self.s.judge_model,
                max_tokens=4_000,
                effort="medium",
            )
        except Exception:  # noqa: BLE001 — an unscored idea still ranks, at zero
            axes = JudgedAxes(
                mechanistic_plausibility=0.0,
                novelty=0.0,
                testability=0.0,
                rationale="scoring call failed; only computed axes are meaningful",
            )
        idea.score = assemble(idea, axes, self.s)
        return idea

    # ------------------------------------------------------------------- chat

    async def chat(self, session: Session, message: str) -> str:
        user = (
            f"QUESTION UNDER DISCUSSION:\n{session.question}\n\n"
            f"CURRENT IDEAS:\n{self._state_digest(session)}\n\n"
            f"CONVERSATION:\n{self._history(session)}\n\n"
            f"SCIENTIST SAYS:\n{message}"
        )
        reply = await self.llm.structured(
            schema=ChatReply, system=CHAT_SYSTEM, user=user, max_tokens=6_000
        )
        return reply.reply

    # -------------------------------------------------------------- internals

    @staticmethod
    def _history(session: Session, limit: int = 12) -> str:
        turns = session.transcript[-limit:]
        return "\n".join(f"{t.role}: {t.text}" for t in turns)

    @staticmethod
    def _existing_titles(session: Session) -> str:
        return "\n".join(
            f"- [{i.id}] {i.title}"
            + (" (dropped)" if i.status is IdeaStatus.DROPPED else "")
            for i in session.ideas
        )

    @staticmethod
    def _state_digest(session: Session) -> str:
        rows: list[str] = []
        for idea in session.ranked():
            score = idea.score
            head = f"[{idea.id}] {idea.title}"
            if score:
                head += (
                    f" — overall {score.overall:.2f}"
                    f", grounding {score.grounding:.0%}"
                    f", {score.recommendation.value}"
                )
            elif not idea.claims:
                head += " — still being decomposed, no claims yet"
            else:
                head += " — claims not yet verified"
            rows.append(head)
            for claim in idea.claims:
                mark = {
                    "verified": "OK",
                    "partial": "~",
                    "unsupported": "X",
                    "quote_mismatch": "X",
                    "no_evidence": "-",
                    "error": "?",
                }.get(claim.status.value, "?")
                rows.append(f"    [{mark}] {claim.text[:110]}")
        dropped = [i for i in session.ideas if i.status is IdeaStatus.DROPPED]
        if dropped:
            rows.append("\nDropped: " + ", ".join(f"{i.id} ({i.drop_reason})" for i in dropped))
        return "\n".join(rows) or "(none yet)"


def turn(session: Session, role: str, text: str) -> None:
    session.transcript.append(Turn(role=role, text=text))  # type: ignore[arg-type]
