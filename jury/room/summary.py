"""Final node: tally the verdicts in code, then (optionally) a cheap-tier moderator summary.

If the model call fails or is turned off, the code-only tally is the summary.
"""

from collections import Counter
from pathlib import Path

from jury.agent import JsonModel, ask_structured
from jury.models import Persona, RoomSummary, Tier, VerdictValue
from jury.room.context import render
from jury.room.state import RoomState

NODE = "summary"
PROMPT = Path(__file__).resolve().parent.parent.parent / "prompts" / "summary.md"


def tally(verdicts: dict[str, dict]) -> dict[str, int]:
    counts = Counter(v["verdict"]["verdict"] for v in verdicts.values())
    return {v.value: counts.get(v.value, 0) for v in VerdictValue}


def tally_headline(t: dict[str, int]) -> str:
    if not any(t.values()):
        return "No verdicts were given."
    return ", ".join(f"{n} {label}" for label, n in t.items() if n)


def make_node(llm: JsonModel, personas: dict[str, Persona], use_model: bool = True):
    async def node(state: RoomState) -> dict:
        verdicts = state.get("verdicts") or {}
        t = tally(verdicts)
        summary = {"tally": t, "headline": tally_headline(t), "agreed": [], "split": [],
                   "top_changes": [], "generated_by": "code"}
        if not use_model or not verdicts:
            return {"summary": summary}

        lines = []
        for pid, v in verdicts.items():
            vd = v["verdict"]
            lines.append(f"- {personas[pid].name}: {vd['verdict']}. {vd['headline']}. "
                         f"Would change their mind: {'; '.join(vd['what_would_change_my_mind']) or 'nothing stated'}")
        messages = [
            {"role": "system", "content": PROMPT.read_text(encoding="utf-8").format(verdicts="\n".join(lines))},
            {"role": "user", "content": render(state, personas)},
        ]
        try:
            s = await ask_structured(llm, Tier.cheap, messages, RoomSummary, "moderator")
        except Exception as e:
            summary["error"] = f"{type(e).__name__}: {e}"[:300]
            return {"summary": summary}
        return {"summary": {**summary, **s.model_dump(), "generated_by": "model"}}

    return node
