"""Round 1 node: one persona's first impression. Runs once per persona in parallel."""

from langgraph.types import Send

from jury.agent import JsonModel, first_impression
from jury.models import Brief, Persona
from jury.redact import redact
from jury.room.state import ImpressionTask, RoomState

NODE = "first_impression"


def fan_out(state: RoomState) -> list[Send]:
    return [Send(NODE, ImpressionTask(persona_id=pid, brief=state["brief"])) for pid in state["persona_ids"]]


def make_node(llm: JsonModel, personas: dict[str, Persona]):
    async def node(task: ImpressionTask) -> dict:
        pid = task["persona_id"]
        try:
            result = await first_impression(llm, personas[pid], Brief.model_validate(task["brief"]))
        except Exception as e:  # one failing persona must not sink the room
            return {"failures": {pid: redact(f"{type(e).__name__}: {e}")[:500]}}
        return {"impressions": {pid: result.model_dump(mode="json")}}

    return node
