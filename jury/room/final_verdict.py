"""Round 3 node: one persona's structured final verdict. Runs once per persona in parallel."""

from jury.agent import JsonModel, final_verdict
from jury.models import Brief, Persona
from jury.redact import redact
from jury.room.state import VerdictTask

NODE = "final_verdict"


def make_node(llm: JsonModel, personas: dict[str, Persona]):
    async def node(task: VerdictTask) -> dict:
        pid = task["persona_id"]
        try:
            result = await final_verdict(
                llm, personas[pid], Brief.model_validate(task["brief"]), context=task["context"],
                answers=task.get("answers"),
            )
        except Exception as e:
            return {"verdict_failures": {pid: redact(f"{type(e).__name__}: {e}")[:500]}}
        return {"verdicts": {pid: result.model_dump(mode="json")}}

    return node
