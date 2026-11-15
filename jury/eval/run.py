"""Run the eval cases through the real room graph and score each one.

Questions to the builder are skipped (nobody is there to answer), which is also the
harder test: the panel has to judge from the evidence alone.
"""

import json
import os
from pathlib import Path

import yaml
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pydantic import BaseModel

from jury.agent import JsonModel
from jury.eval.score import Check, Expect, score
from jury.ingest.brief import build_brief
from jury.models import Brief, Persona
from jury.room.events import stream_events
from jury.room.graph import build_graph, initial_state

ROOT = Path(__file__).resolve().parent.parent.parent
CASES = ROOT / "evals" / "cases.yaml"


class Case(BaseModel):
    id: str
    about: str = ""
    brief: str | None = None  # path to a brief JSON, relative to the cases file
    repo_url: str | None = None
    demo: str = ""
    personas: list[str] | None = None
    expect: Expect


class CaseSet(BaseModel):
    personas: list[str]
    cases: list[Case]


class CaseResult(BaseModel):
    id: str
    passed: bool
    checks: list[Check]
    verdicts: dict[str, str]
    calls: int
    tokens: int
    error: str | None = None


def load_cases(path: Path = CASES) -> CaseSet:
    return CaseSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_brief(case: Case, base: Path) -> Brief:
    if case.brief:
        return Brief.model_validate(json.loads((base / case.brief).read_text(encoding="utf-8")))
    if not case.repo_url:
        raise ValueError(f"case {case.id}: give a brief or a repo_url")
    return build_brief(case.repo_url, case.demo, os.environ.get("GITHUB_TOKEN") or None)


async def run_review(llm: JsonModel, personas: dict[str, Persona], brief: Brief, persona_ids: list[str]) -> list[dict]:
    """One whole review, skipping every question. Returns the event stream."""
    graph = build_graph(llm, personas, MemorySaver())
    config = {"configurable": {"thread_id": "eval"}}
    events: list[dict] = []
    graph_input = initial_state(brief.model_dump(), persona_ids)
    for _ in range(10):  # round 1 questions plus at most 2 debate questions; 10 cannot be reached
        pending = None
        async for event in stream_events(graph, graph_input, config):
            events.append(event)
            if event["type"] == "needs_answers":
                pending = event["questions"]
        if pending is None:
            break
        graph_input = Command(resume={q["id"]: "" for q in pending})
    return events


async def run_case(case: Case, default_personas: list[str], personas: dict[str, Persona],
                   llm: JsonModel, base: Path = CASES.parent) -> tuple[CaseResult, list[dict]]:
    ids = case.personas or default_personas
    budget = getattr(llm, "budget", None)
    calls0, tokens0 = (budget.calls, budget.tokens) if budget else (0, 0)
    events: list[dict] = []
    error = None
    try:
        events = await run_review(llm, personas, load_brief(case, base), ids)
    except Exception as e:  # one broken case must not stop the others
        error = f"{type(e).__name__}: {e}"[:300]
    checks = score(events, case.expect, ids)
    result = CaseResult(
        id=case.id,
        passed=error is None and all(c.ok for c in checks),
        checks=checks,
        verdicts={e["persona_id"]: e["verdict"] for e in events if e["type"] == "verdict"},
        calls=(budget.calls - calls0) if budget else 0,
        tokens=(budget.tokens - tokens0) if budget else 0,
        error=error,
    )
    return result, events
