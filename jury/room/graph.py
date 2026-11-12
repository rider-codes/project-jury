"""Wire the room graph.

START -> first_impression (x N, parallel) -> dedupe_questions -> [ask_user] -> debate_router
debate_router -> debate_turn -> debate_router          (speak)
debate_router -> ask_user -> debate_router             (open question)
debate_router -> final_verdict (x N, parallel) -> summary -> END   (end)
"""

from functools import partial

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from jury.agent import JsonModel
from jury.models import Persona
from jury.room import ask_user, debate_turn, dedupe, final_verdict, first_impression, router, summary
from jury.room.context import render
from jury.room.state import RoomState


def build_graph(
    llm: JsonModel,
    personas: dict[str, Persona],
    checkpointer: BaseCheckpointSaver | None = None,
    model_summary: bool = True,
):
    g = StateGraph(RoomState)
    g.add_node(first_impression.NODE, first_impression.make_node(llm, personas))
    g.add_node(dedupe.NODE, dedupe.node)
    g.add_node(ask_user.NODE, ask_user.node)
    g.add_node(router.NODE, router.make_node(llm))
    g.add_node(debate_turn.NODE, debate_turn.make_node(llm, personas))
    g.add_node(final_verdict.NODE, final_verdict.make_node(llm, personas))
    g.add_node(summary.NODE, summary.make_node(llm, personas, use_model=model_summary))

    # round 1
    g.add_conditional_edges(START, first_impression.fan_out, [first_impression.NODE])
    g.add_edge(first_impression.NODE, dedupe.NODE)  # join: waits for every branch
    g.add_conditional_edges(
        dedupe.NODE,
        lambda s: ask_user.NODE if dedupe.has_questions(s) else router.NODE,
        [ask_user.NODE, router.NODE],
    )
    g.add_edge(ask_user.NODE, router.NODE)

    # round 2 and the hand-off to round 3
    g.add_conditional_edges(
        router.NODE,
        partial(router.route, render_context=lambda s: render(s, personas)),
        [debate_turn.NODE, ask_user.NODE, final_verdict.NODE, summary.NODE],
    )
    g.add_edge(debate_turn.NODE, router.NODE)

    # round 3
    g.add_edge(final_verdict.NODE, summary.NODE)  # join
    g.add_edge(summary.NODE, END)
    return g.compile(checkpointer=checkpointer)


def initial_state(brief: dict, persona_ids: list[str]) -> RoomState:
    return RoomState(brief=brief, persona_ids=persona_ids)
