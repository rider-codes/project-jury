"""Run again only what failed in a finished review: reviewers who never answered in
round 1, verdicts that failed, and a summary the model did not write.

Nothing that succeeded is asked again. A reviewer who missed round 1 gives a late
first impression, then a verdict that reads the whole debate.
"""

import asyncio
from collections.abc import AsyncIterator

from jury.agent import JsonModel
from jury.models import Persona
from jury.room import final_verdict, first_impression, summary
from jury.room.context import render
from jury.room.events import to_events
from jury.room.state import ImpressionTask, VerdictTask, builder_answers


def plan(values: dict) -> dict:
    """What a retry would run. Empty lists and False mean there is nothing to do."""
    ids = values.get("persona_ids") or []
    impressions = values.get("impressions") or {}
    verdicts = values.get("verdicts") or {}
    s = values.get("summary") or {}
    return {
        "impressions": [p for p in ids if p not in impressions],
        "verdicts": [p for p in ids if p not in verdicts],
        "summary": bool(s.get("error")) or (bool(verdicts) and not s),
    }


def needed(p: dict) -> bool:
    return bool(p["impressions"] or p["verdicts"] or p["summary"])


async def redo(graph, config: dict, llm: JsonModel, personas: dict[str, Persona]) -> AsyncIterator[dict]:
    values = dict((await graph.aget_state(config)).values)
    todo = plan(values)
    brief = values["brief"]
    update: dict = {}

    async def run_all(node, name: str, tasks: list) -> list[dict]:
        events = []
        for result in await asyncio.gather(*(node(t) for t in tasks)):
            for key, part in result.items():
                update[key] = {**update.get(key, {}), **part}
                values[key] = {**(values.get(key) or {}), **part}
            events += to_events({name: result})
        return events

    impress = first_impression.make_node(llm, personas)
    for event in await run_all(impress, first_impression.NODE,
                               [ImpressionTask(persona_id=p, brief=brief) for p in todo["impressions"]]):
        yield event

    # a reviewer whose late impression failed again still sits out
    judges = [p for p in todo["verdicts"] if p in (values.get("impressions") or {})]
    context = render(values, personas)
    judge = final_verdict.make_node(llm, personas)
    for event in await run_all(judge, final_verdict.NODE,
                               [VerdictTask(persona_id=p, brief=brief, context=context, answers=builder_answers(values))
                                for p in judges]):
        yield event

    if values.get("verdicts"):
        result = await summary.make_node(llm, personas)(values)
        update["summary"] = result["summary"]
        for event in to_events({summary.NODE: result}):
            yield event

    if update:
        await graph.aupdate_state(config, update, as_node=summary.NODE)
    yield {"type": "done"}
