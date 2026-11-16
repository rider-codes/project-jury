"""FastAPI app.

GET  /api/personas
POST /api/reviews                  start a review (repo link + demo, or the sample)
GET  /api/reviews                  past reviews
GET  /api/reviews/{id}             one review and its status
GET  /api/reviews/{id}/events      Server-Sent Events, replayable (Last-Event-ID or ?after=)
POST /api/reviews/{id}/answers     answer the open questions and resume
POST /api/reviews/{id}/messages    say something to the room while it is still debating
POST /api/reviews/{id}/retry       run again only what failed (reviewers, verdicts, summary)
POST /api/chats                    start a one-on-one chat (clean, or with the room's history)
GET  /api/chats/{id}
POST /api/chats/{id}/messages      send one message, get the persona's reply
"""

import asyncio
import hmac
import json
import os
import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from jury.agent import JsonModel
from jury.api import access
from jury.api.runner import Busy, Runner
from jury.api.store import TERMINAL, ReviewStore
from jury.chat.room_history import load_room
from jury.chat.session import ChatSession
from jury.chat.store import ChatStore
from jury.ingest.site_log import vision_calls
from jury.personas import load_all
from jury.redact import redact
from jury.room.retry import needed
from jury.room.state import DEFAULT_ROOM

ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_BRIEF = ROOT / "examples" / "sample_brief.json"
WEB_OUT = ROOT / "web" / "out"
POLL_SECONDS = 0.3
PING_EVERY = 50  # polls (~15 s)


class NewReview(BaseModel):
    repo_url: str = ""
    site_url: str = Field("", max_length=500)  # the live site, captured with a headless browser
    demo: str = Field("", max_length=20_000)
    sample: bool = False  # use examples/sample_brief.json instead of a repo
    persona_ids: list[str] = Field(default_factory=lambda: list(DEFAULT_ROOM))


class Answers(BaseModel):
    answers: dict[str, str]


class RoomMessage(BaseModel):
    to: str = "everyone"  # "everyone" or one persona id
    text: str = Field(min_length=1, max_length=2_000)


class NewChat(BaseModel):
    persona_id: str
    review_id: str | None = None
    with_history: bool = False  # default is a clean start, per the plan
    sample: bool = False


class ChatMessage(BaseModel):
    text: str = Field(min_length=1, max_length=4_000)


class Login(BaseModel):
    code: str = Field(max_length=200)


def create_app(db_path: str, llm_factory: Callable[[], JsonModel], brief_builder=None, site_adder=None) -> FastAPI:
    """`db_path` holds the LangGraph checkpoints. Reviews, events and chats go in a
    separate `<name>_app.sqlite` beside it: sharing one file let the event log and
    the checkpointer lock each other out ("database is locked")."""
    personas = load_all()
    p = Path(db_path)
    app_db = str(p.with_name(f"{p.stem}_app{p.suffix or '.sqlite'}"))
    store = ReviewStore(app_db)
    chats = ChatStore(app_db)
    kwargs = {"brief_builder": brief_builder} if brief_builder else {}
    if site_adder:
        kwargs["site_adder"] = site_adder
    runner = Runner(db_path, store, personas, llm_factory, **kwargs)
    chat_llms: dict[str, JsonModel] = {}

    app = FastAPI(title="Project Jury")
    app.state.runner = runner
    app.middleware("http")(access.gate)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("JURY_WEB_ORIGIN", "http://localhost:3000").split(","),
        allow_credentials=True,  # the dev page on :3000 sends the access cookie to the API on :8000
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    def review_or_404(review_id: str) -> dict:
        r = store.get(review_id)
        if r is None:
            raise HTTPException(404, "no such review")
        return r

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/session")
    def session(request: Request):
        return {"needs_code": bool(access.access_code()), "ok": access.has_access(request)}

    @app.post("/api/login")
    def login(body: Login, request: Request):
        code = access.access_code()
        if code and not hmac.compare_digest(body.code.strip(), code):
            raise HTTPException(401, "wrong access code")
        response = JSONResponse({"ok": True})
        secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
        response.set_cookie(access.COOKIE, access.token_for(code), httponly=True, samesite="lax",
                            secure=secure, max_age=60 * 60 * 24 * 30)
        return response

    # the design canvas order: the default room first
    ORDER = [*DEFAULT_ROOM, "hiring_manager", "open_source_maintainer"]

    @app.get("/api/personas")
    def list_personas():
        ordered = sorted(personas.values(), key=lambda p: ORDER.index(p.id) if p.id in ORDER else len(ORDER))
        return [
            {"id": p.id, "name": p.name, "tagline": p.tagline, "tier": p.model.value,
             "verdict_question": p.verdict_question, "cares_about": p.cares_about,
             "default": p.id in DEFAULT_ROOM}
            for p in ordered
        ]

    @app.get("/api/quota")
    async def quota():
        """What a review will cost against today's free quota. The page shows it before starting."""
        llm = llm_factory()
        demo = type(llm).__name__ == "DemoLLM"
        q = None if demo or not hasattr(llm, "quota") else await llm.quota()
        # a live site adds up to this many vision calls (one per screenshot described)
        return {"demo_model": demo, "free_quota": q, "site_calls": vision_calls()}

    @app.post("/api/reviews", status_code=201)
    async def new_review(body: NewReview):
        ids = list(dict.fromkeys(body.persona_ids))
        unknown = [p for p in ids if p not in personas]
        if not ids or unknown:
            raise HTTPException(422, f"pick 1 to {len(personas)} known personas; unknown: {unknown}")
        if not body.sample and not body.repo_url.strip():
            raise HTTPException(422, "give a GitHub link, or use the sample project")
        review_id = uuid.uuid4().hex[:12]
        if body.sample:
            brief = json.loads(SAMPLE_BRIEF.read_text(encoding="utf-8"))
            store.create(review_id, brief["project_name"], brief["repo_url"], ids)
            runner.start(review_id, ids, brief=brief)
        else:
            from jury.ingest.github import IngestError, parse_repo_url
            try:
                ref = parse_repo_url(body.repo_url)
            except IngestError as e:
                raise HTTPException(422, str(e))
            site_url = body.site_url.strip()
            if site_url:
                from jury.ingest.site import SiteError, normalize_url
                try:
                    site_url = normalize_url(site_url)
                except SiteError as e:
                    raise HTTPException(422, str(e))
            store.create(review_id, ref.repo, ref.url, ids)
            runner.start(review_id, ids, repo_url=body.repo_url, demo_text=body.demo, site_url=site_url)
        return {"id": review_id}

    @app.get("/api/reviews")
    def list_reviews():
        return store.recent()

    @app.get("/api/reviews/{review_id}")
    def get_review(review_id: str):
        r = review_or_404(review_id)
        return {**r, "status": store.status(review_id), "running": runner.is_running(review_id)}

    @app.get("/api/reviews/{review_id}/events")
    async def review_events(review_id: str, request: Request, after: int = 0):
        review_or_404(review_id)
        last = int(request.headers.get("last-event-id") or after)

        async def stream():
            nonlocal last
            idle = 0
            finished = False  # kept across polls; a retry ("resumed") reopens a finished review
            while not await request.is_disconnected():
                rows = store.events_after(review_id, last)
                for seq, event in rows:
                    last = seq
                    yield f"id: {seq}\ndata: {json.dumps(event)}\n\n"
                    finished = event["type"] in TERMINAL or (finished and event["type"] != "resumed")
                if finished and not runner.is_running(review_id):
                    # let the trailing usage event through, then close
                    for seq, event in store.events_after(review_id, last):
                        last = seq
                        yield f"id: {seq}\ndata: {json.dumps(event)}\n\n"
                    yield "event: end\ndata: {}\n\n"
                    return
                idle = 0 if rows else idle + 1
                if idle and idle % PING_EVERY == 0:
                    yield ": ping\n\n"
                await asyncio.sleep(POLL_SECONDS)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/reviews/{review_id}/answers", status_code=202)
    async def answer(review_id: str, body: Answers):  # async: resume needs the running event loop
        review_or_404(review_id)
        if store.status(review_id) != "paused":
            raise HTTPException(409, "this review is not waiting for answers")
        try:
            runner.resume(review_id, body.answers)
        except Busy as e:
            raise HTTPException(409, str(e))
        return {"ok": True}

    @app.post("/api/reviews/{review_id}/messages", status_code=202)
    async def say(review_id: str, body: RoomMessage):
        r = review_or_404(review_id)
        if body.to != "everyone" and body.to not in r["persona_ids"]:
            raise HTTPException(422, "send it to everyone or to a reviewer in this room")
        events = [e["type"] for _, e in store.events_after(review_id)]
        ended = any(e["type"] == "router" and e.get("action") == "end" for _, e in store.events_after(review_id))
        if store.status(review_id) in TERMINAL or ended or "brief" not in events:
            raise HTTPException(409, "the debate is not running; when the review ends you can ask one reviewer directly")
        if not body.text.strip():
            raise HTTPException(422, "the message is empty")
        try:
            runner.say(review_id, body.to, body.text.strip())
        except Busy as e:
            raise HTTPException(409, str(e))
        return {"ok": True}

    @app.post("/api/reviews/{review_id}/retry", status_code=202)
    async def retry(review_id: str):
        review_or_404(review_id)
        if runner.is_running(review_id):
            raise HTTPException(409, "this review is still running")
        if store.status(review_id) == "paused":
            raise HTTPException(409, "this review is waiting for your answers")
        todo = await runner.retry_plan(review_id)
        if todo is None:
            raise HTTPException(409, "the project was never read, so start a new review instead")
        if not (todo["resume"] or needed(todo)):
            raise HTTPException(409, "nothing failed in this review")
        runner.retry(review_id)
        return todo

    @app.post("/api/chats", status_code=201)
    async def new_chat(body: NewChat):
        if body.persona_id not in personas:
            raise HTTPException(422, "unknown persona")
        if body.review_id:
            review_or_404(body.review_id)
            try:
                brief, context, _ = await load_room(db_path, body.review_id, personas)
            except LookupError:
                raise HTTPException(409, "this review has not read the project yet")
            session = ChatSession(persona_id=body.persona_id, brief=brief,
                                  room_thread=body.review_id if body.with_history else None,
                                  room_context=context if body.with_history else "")
        elif body.sample:
            session = ChatSession(persona_id=body.persona_id,
                                  brief=json.loads(SAMPLE_BRIEF.read_text(encoding="utf-8")))
        else:
            raise HTTPException(422, "give a review_id, or use the sample project")
        chats.save(session)
        return chat_view(session)

    def chat_view(s: ChatSession) -> dict:
        return {"id": s.id, "persona_id": s.persona_id, "project_name": s.brief["project_name"],
                "room_thread": s.room_thread, "with_history": bool(s.room_context), "messages": s.messages}

    @app.get("/api/chats/{chat_id}")
    def get_chat(chat_id: str):
        s = chats.load(chat_id)
        if s is None:
            raise HTTPException(404, "no such chat")
        return chat_view(s)

    @app.post("/api/chats/{chat_id}/messages")
    async def send(chat_id: str, body: ChatMessage):
        s = chats.load(chat_id)
        if s is None:
            raise HTTPException(404, "no such chat")
        llm = chat_llms.setdefault(chat_id, llm_factory())
        try:
            reply = await s.send(llm, personas[s.persona_id], body.text)
        except ValueError as e:
            raise HTTPException(422, str(e))
        except Exception as e:
            raise HTTPException(502, redact(f"the model did not answer: {e}")[:400])
        chats.save(s)
        return reply

    # In production the built page (web/out) is served from the same server. Mounted last,
    # so every /api route above wins.
    static_dir = Path(os.environ.get("JURY_STATIC_DIR", WEB_OUT))
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")

    return app
