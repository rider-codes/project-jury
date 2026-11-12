"""Turn LangGraph stream updates into small UI events. The CLI prints them now;
the SSE endpoint will send the same dicts later."""

from collections.abc import AsyncIterator
from typing import Any

from langgraph.types import Command

from jury.room import ask_user, debate_turn, dedupe, final_verdict, first_impression, router, summary


def to_events(chunk: dict[str, Any]) -> list[dict]:
    events: list[dict] = []
    for node, update in chunk.items():
        if node == "__interrupt__":
            for intr in update:
                events.append({"type": "needs_answers", "questions": intr.value.get("questions", [])})
            continue
        update = update or {}
        if node == first_impression.NODE:
            for pid, imp in (update.get("impressions") or {}).items():
                i = imp["impression"]
                events.append({
                    "type": "impression",
                    "persona_id": pid,
                    "stance": i["stance"],
                    "headline": i["headline"],
                    "claims": i["claims"],
                    "questions": i["questions"],
                    "rejected": [{"text": r["claim"]["text"], "problem": r["problem"]} for r in imp["rejected"]],
                })
            for pid, err in (update.get("failures") or {}).items():
                events.append({"type": "agent_error", "persona_id": pid, "error": err})
        elif node == dedupe.NODE:
            events.append({"type": "questions_merged", "questions": update.get("questions", [])})
        elif node == ask_user.NODE and update.get("answers") is not None:
            events.append({"type": "answers_received", "answers": update["answers"]})
        elif node == router.NODE and update.get("next_action"):
            events.append({"type": "router", **update["next_action"]})
        elif node == debate_turn.NODE:
            for t in update.get("turns") or []:
                events.append({"type": "debate_turn", **t})
        elif node == final_verdict.NODE:
            for pid, v in (update.get("verdicts") or {}).items():
                vd = v["verdict"]
                events.append({
                    "type": "verdict",
                    "persona_id": pid,
                    **vd,
                    "rejected": [{"text": r["claim"]["text"], "problem": r["problem"]} for r in v["rejected"]],
                })
            for pid, err in (update.get("verdict_failures") or {}).items():
                events.append({"type": "agent_error", "persona_id": pid, "error": err, "phase": "verdict"})
        elif node == summary.NODE and update.get("summary"):
            events.append({"type": "summary", **update["summary"]})
    return events


async def stream_events(graph, graph_input: dict | Command, config: dict) -> AsyncIterator[dict]:
    """Run (or resume) the graph and yield events, ending with `paused` or `done`."""
    async for chunk in graph.astream(graph_input, config, stream_mode="updates"):
        for event in to_events(chunk):
            yield event
    state = await graph.aget_state(config)
    yield {"type": "paused"} if state.next else {"type": "done"}
