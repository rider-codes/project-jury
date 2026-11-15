"""Run reviews in the background and record every event.

One model wrapper (and so one budget) per review, shared across its pauses.
"""

import asyncio
import os
from collections.abc import Callable

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from jury.agent import JsonModel
from jury.api.store import ReviewStore
from jury.ingest.brief import build_brief
from jury.ingest.site_log import add_site
from jury.models import Persona
from jury.room.events import stream_events
from jury.room.graph import build_graph, initial_state


class Busy(RuntimeError):
    pass


class Runner:
    def __init__(
        self,
        db_path: str,
        store: ReviewStore,
        personas: dict[str, Persona],
        llm_factory: Callable[[], JsonModel],
        brief_builder: Callable[..., object] = build_brief,
        site_adder: Callable[..., object] = add_site,
    ):
        self.db_path, self.store, self.personas = db_path, store, personas
        self.llm_factory, self.brief_builder, self.site_adder = llm_factory, brief_builder, site_adder
        self.tasks: dict[str, asyncio.Task] = {}
        self.llms: dict[str, JsonModel] = {}

    def is_running(self, review_id: str) -> bool:
        t = self.tasks.get(review_id)
        return t is not None and not t.done()

    def _spawn(self, review_id: str, coro) -> None:
        if self.is_running(review_id):
            coro.close()
            raise Busy("this review is still running")
        self.tasks[review_id] = asyncio.create_task(coro)

    def _llm(self, review_id: str) -> JsonModel:
        if review_id not in self.llms:
            self.llms[review_id] = self.llm_factory()
        return self.llms[review_id]

    def start(self, review_id: str, persona_ids: list[str], brief: dict | None = None,
              repo_url: str = "", demo_text: str = "", site_url: str = "") -> None:
        self._spawn(review_id, self._start(review_id, persona_ids, brief, repo_url, demo_text, site_url))

    def resume(self, review_id: str, answers: dict[str, str]) -> None:
        self._spawn(review_id, self._run(review_id, Command(resume=answers), resumed=True))

    async def _start(self, review_id, persona_ids, brief, repo_url, demo_text, site_url="") -> None:
        try:
            if brief is None:
                self.store.add_event(review_id, {"type": "status", "stage": "ingesting", "repo_url": repo_url})
                b = await asyncio.to_thread(self.brief_builder, repo_url, demo_text,
                                            os.environ.get("GITHUB_TOKEN") or None)
                if site_url:
                    # the screenshot log's vision calls go on this review's budget
                    self.store.add_event(review_id, {"type": "status", "stage": "site", "site_url": site_url})
                    b = await self.site_adder(self._llm(review_id), b, site_url)
                brief = b.model_dump()
            self.store.rename(review_id, brief["project_name"], brief["repo_url"])
            self.store.add_event(review_id, {
                "type": "brief",
                "project_name": brief["project_name"],
                "repo_url": brief["repo_url"],
                "summary": brief["summary"],
                "files": len(brief["files"]),
                "tree": len(brief.get("tree") or []),
                "demo_steps": len(brief.get("demo") or []),
                "site_url": brief.get("site_url") or "",
                "site_views": len(brief.get("site") or []),
                "site_logs": sum(1 for v in brief.get("site") or [] if v.get("log")),
                "notes": brief.get("notes") or [],
                "persona_ids": persona_ids,
            })
        except Exception as e:
            self.store.add_event(review_id, {"type": "error", "message": f"Could not read the project: {e}"})
            return
        await self._run(review_id, initial_state(brief, persona_ids))

    async def _run(self, review_id: str, graph_input, resumed: bool = False) -> None:
        if resumed:
            self.store.add_event(review_id, {"type": "resumed"})
        llm = self._llm(review_id)
        config = {"configurable": {"thread_id": review_id}}
        try:
            async with AsyncSqliteSaver.from_conn_string(self.db_path) as saver:
                graph = build_graph(llm, self.personas, saver)
                async for event in stream_events(graph, graph_input, config):
                    self.store.add_event(review_id, event)
        except Exception as e:
            self.store.add_event(review_id, {"type": "error", "message": f"{type(e).__name__}: {e}"[:500]})
        budget = getattr(llm, "budget", None)
        if budget is not None:
            self.store.add_event(review_id, {"type": "usage", "calls": budget.calls, "tokens": budget.tokens})
