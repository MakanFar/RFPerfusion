"""Local web GUI for the formulation agent.

A different driver over the same engine as `cli.py` — no agent logic lives here.
The browser gets a live event stream (SSE) so verification progress and
background follow-ups appear as they happen rather than at a prompt.

Runs on localhost only. The API key can be supplied by the environment or
pasted into the UI, in which case it is held in memory for the process
lifetime and never written to disk.
"""

from __future__ import annotations

import asyncio
import json
import os
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from .agent import FormulationAgent, turn
from .config import SETTINGS
from .followup import FollowupManager
from .llm import LLM
from .models import Claim, FollowupStatus, IdeaStatus, Session, Verification
from .paperclip import Paperclip
from .report import save_session

STATIC = Path(__file__).parent / "static"


# --------------------------------------------------------------------------
# serialisation for the browser
# --------------------------------------------------------------------------


def claim_json(claim: Claim) -> dict[str, Any]:
    return {
        "id": claim.id,
        "text": claim.text,
        "load_bearing": claim.load_bearing,
        "status": claim.status.value,
        "evidence": [
            {
                "quote": ev.quote,
                "url": ev.ref.citation_url,
                "span": ev.ref.span,
                "citation": ev.citation.formatted(),
                "doc_id": ev.citation.doc_id,
                "support_level": ev.support_level.value,
                "kind": ev.evidence_kind.value,
                "refutes": ev.refutes,
                "verification": ev.verification.value,
                "note": ev.entailment_note,
            }
            for ev in claim.evidence
        ],
    }


def idea_json(idea, rank: int | None = None) -> dict[str, Any]:
    s = idea.score
    lb = idea.load_bearing_claims
    return {
        "rank": rank,
        "id": idea.id,
        "title": idea.title,
        "one_liner": idea.one_liner,
        "mechanism_chain": idea.mechanism_chain,
        "rationale": idea.rationale,
        "key_risk": idea.key_risk,
        "testability_note": idea.testability_note,
        "novelty_note": idea.novelty_note,
        "status": idea.status.value,
        "drop_reason": idea.drop_reason,
        "claims": [claim_json(c) for c in idea.claims],
        "verified_count": sum(1 for c in lb if c.status is Verification.VERIFIED),
        "load_bearing_count": len(lb),
        "score": None
        if not s
        else {
            "overall": s.overall,
            "grounding": s.grounding,
            "evidence_strength": s.evidence_strength,
            "mechanistic_plausibility": s.mechanistic_plausibility,
            "novelty": s.novelty,
            "testability": s.testability,
            "cap_applied": s.cap_applied,
            "grounding_cap": s.grounding_cap,
            "recommendation": s.recommendation.value,
            "rationale": s.rationale,
        },
    }


# --------------------------------------------------------------------------
# app state
# --------------------------------------------------------------------------


class Hub:
    """Single in-memory session plus a fan-out event bus for the browser."""

    def __init__(self) -> None:
        self.session = Session()
        self.pc = Paperclip(concurrency=SETTINGS.paperclip_concurrency)
        self.llm: LLM | None = None
        self.agent: FormulationAgent | None = None
        self.followups: FollowupManager | None = None
        self.subscribers: set[asyncio.Queue] = set()
        self.busy = False
        self.phase: str | None = None
        self._try_env_key()

    # ---------------------------------------------------------------- auth

    def _try_env_key(self) -> None:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if key:
            self.set_key(key)

    def set_key(self, key: str) -> None:
        self.llm = LLM(api_key=key)
        self.agent = FormulationAgent(self.llm, self.pc)
        self.followups = FollowupManager(self.agent)

    @property
    def ready(self) -> bool:
        return self.agent is not None

    # --------------------------------------------------------------- events

    async def emit(self, kind: str, **data: Any) -> None:
        payload = json.dumps({"kind": kind, **data})
        for queue in list(self.subscribers):
            await queue.put(payload)

    async def set_phase(self, label: str | None) -> None:
        """Name the current stage so the browser can show it with a timer.

        The proposal stage is a single opaque model call with no sub-progress to
        report, so the label plus a client-side elapsed clock is the only honest
        signal that work is happening.
        """
        self.phase = label
        await self.emit("phase", label=label)

    async def push_state(self) -> None:
        await self.emit("state", **self.state())

    def state(self) -> dict[str, Any]:
        ranked = self.session.ranked()
        return {
            "question": self.session.question,
            "busy": self.busy,
            "phase": self.phase,
            "ready": self.ready,
            "ideas": [idea_json(i, n) for n, i in enumerate(ranked, 1)],
            "dropped": [
                idea_json(i)
                for i in self.session.ideas
                if i.status is IdeaStatus.DROPPED
            ],
            "jobs": [
                {
                    "job_id": r.job_id,
                    "idea_id": r.idea_id,
                    "question": r.question,
                    "status": r.status.value,
                    "verdict": r.verdict,
                    "answer": r.answer,
                    "error": r.error,
                    "elapsed": round(r.elapsed_s),
                    "claims": [claim_json(c) for c in r.claims],
                }
                for r in self.session.followups
            ],
            "transcript": [
                {"role": t.role, "text": t.text} for t in self.session.transcript
            ],
        }

    # ------------------------------------------------------------ workflows

    async def run_proposal(self, n: int | None = None, first: bool = False) -> None:
        """Outline → expand → verify, publishing state after each stage.

        Ideas are added to the session as soon as the outline returns, so the
        browser can render them (unscored, visibly provisional) while their
        claims are still being written and checked.
        """
        assert self.agent
        self.busy = True
        await self.emit("busy", busy=True)
        try:
            # --- stage 1: directions only, seconds not minutes ---------------
            await self.set_phase("Proposing directions")
            ideas, reading = await self.agent.propose_outline(self.session, n=n)
            if first and reading:
                await self.emit("reading", text=reading)
            self.session.ideas.extend(ideas)
            await self.emit("log", text=f"{len(ideas)} directions proposed.")
            await self.push_state()

            # --- stage 2: decompose each into claims, in parallel ------------
            await self.set_phase(f"Decomposing {len(ideas)} directions into claims")
            await self.agent.expand_all(self.session, ideas)
            total = sum(len(i.claims) for i in ideas)
            await self.emit("log", text=f"{total} claims to verify.")
            await self.push_state()

            # --- stage 3: verify every claim against the literature ----------
            await self.set_phase(f"Verifying claims — 0/{total}")
            done = 0

            def progress(claim: Claim, status: str) -> None:
                nonlocal done
                done += 1
                # Count in the label too: the bar is easy to miss, and this is
                # the stage where the user most needs to see movement.
                asyncio.create_task(
                    self.emit("phase", label=f"Verifying claims — {done}/{total}")
                )
                asyncio.create_task(
                    self.emit(
                        "progress", done=done, total=total, status=status, text=claim.text
                    )
                )
                # Republish periodically so confirmed quotes appear on the cards
                # during the run rather than all at once at the end.
                if done % 3 == 0:
                    asyncio.create_task(self.push_state())

            await self.agent.ground_and_score(ideas, progress)
            await self.emit("log", text="Done.")
        except Exception as exc:  # noqa: BLE001 — surfaced in the UI
            await self.emit("error", text=f"{type(exc).__name__}: {exc}")
        finally:
            self.busy = False
            await self.set_phase(None)
            await self.emit("busy", busy=False)
            await self.push_state()

    async def watch_followups(self) -> None:
        """Push completed background investigations to the browser."""
        while True:
            await asyncio.sleep(1.0)
            if not self.followups:
                continue
            for report in self.followups.collect():
                idea = self.session.by_id(report.idea_id)
                if idea and idea.status is IdeaStatus.UNDER_FOLLOWUP:
                    idea.status = IdeaStatus.REFINED
                await self.emit(
                    "followup_done",
                    job_id=report.job_id,
                    idea_id=report.idea_id,
                    status=report.status.value,
                    verdict=report.verdict,
                    answer=report.answer,
                    error=report.error,
                )
                await self.push_state()


hub = Hub()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(hub.watch_followups())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/state")
async def get_state() -> JSONResponse:
    return JSONResponse(hub.state())


@app.get("/api/events")
async def events(request: Request) -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue()
    hub.subscribers.add(queue)

    async def stream():
        try:
            yield f"data: {json.dumps({'kind': 'state', **hub.state()})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # keep proxies and the browser happy
                    continue
                yield f"data: {payload}\n\n"
        finally:
            hub.subscribers.discard(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/key")
async def set_key(body: dict) -> JSONResponse:
    key = (body.get("key") or "").strip()
    if not key.startswith("sk-"):
        return JSONResponse({"error": "That doesn't look like an API key."}, status_code=400)
    hub.set_key(key)
    ok, msg = await hub.llm.healthcheck()  # type: ignore[union-attr]
    if not ok:
        hub.llm = hub.agent = hub.followups = None
        return JSONResponse({"error": f"Key rejected: {msg}"}, status_code=400)
    await hub.push_state()
    return JSONResponse({"ok": True})


@app.post("/api/ask")
async def ask(body: dict) -> JSONResponse:
    if not hub.ready:
        return JSONResponse({"error": "No API key set."}, status_code=400)
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "empty"}, status_code=400)

    if hub.busy and (not hub.session.question or text == hub.session.question):
        # Without this a second click while the first run is in flight falls
        # through to the chat branch and spawns a redundant model call.
        return JSONResponse(
            {"error": "Already working on this — watch the Activity panel."},
            status_code=409,
        )

    turn(hub.session, "scientist", text)
    if not hub.session.question:
        hub.session.question = text
        # Publish immediately: the browser only swaps the hero for the workspace
        # on a state event, and the next one would otherwise not arrive until
        # the whole run finished — leaving the page looking dead for minutes.
        hub.busy = True
        await hub.push_state()
        asyncio.create_task(hub.run_proposal(first=True))
        return JSONResponse({"ok": True, "mode": "propose"})

    async def chat() -> None:
        try:
            reply = await hub.agent.chat(hub.session, text)  # type: ignore[union-attr]
            turn(hub.session, "agent", reply)
            await hub.emit("chat", text=reply)
        except Exception as exc:  # noqa: BLE001
            await hub.emit("error", text=str(exc))
        await hub.push_state()

    asyncio.create_task(chat())
    return JSONResponse({"ok": True, "mode": "chat"})


@app.post("/api/more")
async def more(body: dict) -> JSONResponse:
    if not hub.ready or not hub.session.question:
        return JSONResponse({"error": "Ask a question first."}, status_code=400)
    if hub.busy:
        return JSONResponse({"error": "Still working — wait for this run."}, status_code=409)
    hub.busy = True
    await hub.push_state()
    asyncio.create_task(hub.run_proposal(n=int(body.get("n") or 3)))
    return JSONResponse({"ok": True})


@app.post("/api/drop")
async def drop(body: dict) -> JSONResponse:
    idea = hub.session.by_id(body.get("idea_id") or "")
    if not idea:
        return JSONResponse({"error": "unknown idea"}, status_code=404)
    idea.status = IdeaStatus.DROPPED
    idea.drop_reason = (body.get("reason") or "").strip() or "dropped by scientist"
    turn(hub.session, "scientist", f"dropped {idea.id}: {idea.drop_reason}")
    await hub.push_state()
    return JSONResponse({"ok": True})


@app.post("/api/restore")
async def restore(body: dict) -> JSONResponse:
    idea = hub.session.by_id(body.get("idea_id") or "")
    if not idea:
        return JSONResponse({"error": "unknown idea"}, status_code=404)
    idea.status = IdeaStatus.PROPOSED
    idea.drop_reason = ""
    await hub.push_state()
    return JSONResponse({"ok": True})


@app.post("/api/followup")
async def followup(body: dict) -> JSONResponse:
    if not hub.ready:
        return JSONResponse({"error": "No API key set."}, status_code=400)
    idea = hub.session.by_id(body.get("idea_id") or "")
    question = (body.get("question") or "").strip()
    if not idea or not question:
        return JSONResponse({"error": "need an idea and a question"}, status_code=400)

    report = hub.followups.spawn(idea, question)  # type: ignore[union-attr]
    idea.status = IdeaStatus.UNDER_FOLLOWUP
    hub.session.followups.append(report)
    turn(hub.session, "scientist", f"follow-up on {idea.id}: {question}")
    await hub.push_state()
    return JSONResponse({"ok": True, "job_id": report.job_id})


@app.post("/api/save")
async def save() -> JSONResponse:
    paths = save_session(hub.session, SETTINGS.session_dir)
    return JSONResponse({"paths": [str(p) for p in paths]})


def main() -> None:
    import uvicorn

    port = int(os.environ.get("FA_PORT", "8765"))
    url = f"http://127.0.0.1:{port}"
    print(f"\n  Formulation Agent — open {url}\n")
    if os.environ.get("FA_NO_BROWSER") != "1":
        threading_timer(1.0, lambda: webbrowser.open(url))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def threading_timer(delay: float, fn) -> None:
    import threading

    threading.Timer(delay, fn).start()


if __name__ == "__main__":
    main()
