"""Load an earlier room review so a one-on-one chat can start from it (optional)."""

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from jury.models import Persona
from jury.room.context import render
from jury.room.graph import build_graph


class _NoModel:
    async def complete_json(self, tier, messages):  # never called: we only read state
        raise RuntimeError("reading room history must not call a model")


async def load_room(db_path: str, thread_id: str, personas: dict[str, Persona]) -> tuple[dict, str, dict]:
    """Return (brief, rendered transcript including verdicts, raw state) for a past room."""
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
        graph = build_graph(_NoModel(), personas, saver)
        state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    values = state.values
    if not values or "brief" not in values:
        raise LookupError(f"no room review with id {thread_id}")

    transcript = render(values, personas)
    verdicts = values.get("verdicts") or {}
    if verdicts:
        lines = ["\nFinal verdicts:"]
        for pid, v in verdicts.items():
            vd = v["verdict"]
            name = personas[pid].name if pid in personas else pid
            lines.append(f"- {name}: {vd['verdict']}. {vd['headline']}")
        transcript = transcript.replace("</room_transcript>", "\n".join(lines) + "\n</room_transcript>")
    elif state.next:
        transcript = transcript.replace("</room_transcript>", "(This review was not finished.)\n</room_transcript>")
    return values["brief"], transcript, values
