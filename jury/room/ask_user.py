"""The single interrupt node: show every open question at once and wait for answers.

LangGraph re-runs this node from the top on resume, so it has no side effects
before `interrupt()`.
"""

from langgraph.types import interrupt

from jury.room.state import RoomState

NODE = "ask_user"


def node(state: RoomState) -> dict:
    questions = state.get("questions") or []
    if not questions:
        return {}
    reply = interrupt({"questions": questions})
    known = {q["id"] for q in questions}
    answers = reply if isinstance(reply, dict) else {}
    # keep only answers to questions we asked; blank means "skipped"
    clean = {qid: str(a).strip() for qid, a in answers.items() if qid in known}
    log = [{**q, "answer": clean.get(q["id"], "")} for q in questions]
    return {"answers": clean, "qa_log": log}
