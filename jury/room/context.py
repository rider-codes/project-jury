"""Render what has happened in the room so far, for the next model call.

Wrapped as data: it holds other agents' words and the user's answers.
"""

from jury.models import Persona
from jury.room.state import RoomState


def _claims(claims: list[dict], indent: str = "    ") -> list[str]:
    return [f'{indent}* {c["text"]} [{c["evidence"]["ref"]}: "{c["evidence"]["quote"]}"]' for c in claims]


def render(state: RoomState, personas: dict[str, Persona]) -> str:
    name = lambda pid: personas[pid].name if pid in personas else pid
    lines = ["Round 1 first impressions:"]
    for pid in state.get("persona_ids", []):
        imp = (state.get("impressions") or {}).get(pid)
        if imp:
            i = imp["impression"]
            lines.append(f"- {name(pid)} ({pid}): {i['stance']}. {i['headline']}")
            lines += _claims(i["claims"])
        elif pid in (state.get("failures") or {}):
            lines.append(f"- {name(pid)} ({pid}): did not respond, not in the debate")

    qa = state.get("qa_log") or []
    if qa:
        lines.append("\nQuestions to the builder and their answers:")
        for q in qa:
            lines.append(f"- [{q['id']}] {q['text']} (asked by {', '.join(name(p) for p in q['asked_by'])})")
            lines.append(f"    answer: {q['answer'] or '(skipped, no answer)'}")

    turns = state.get("turns") or []
    if turns:
        lines.append("\nDebate so far:")
        for n, t in enumerate(turns, 1):
            if t.get("user_text"):
                lines.append(f"- the builder said to the room: {t['user_text']}")
            if t.get("error"):
                lines.append(f"- turn {n}, {name(t['speaker'])}: (could not respond)")
                continue
            change = f", changed stance: {t['stance_change_reason']}" if t.get("stance_changed") else ""
            lines.append(f"- turn {n}, {name(t['speaker'])} [stance: {t['stance']}{change}]: {t['message']}")
            lines += _claims(t["claims"])

    return "<room_transcript>\n" + "\n".join(lines) + "\n</room_transcript>"
