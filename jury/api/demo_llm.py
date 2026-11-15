"""A free, offline stand-in model for working on the UI (JURY_DEMO_MODEL=1).

It quotes real lines from the brief, so its claims pass the verifier, and it
follows the same JSON shapes as a real model. Its opinions are canned: never
use it to judge a project.
"""

import asyncio
import hashlib
import json
import re

from jury.llm import Budget
from jury.models import Tier

STANCES = ["not useful", "unsure", "useful"]


class DemoLLM:
    def __init__(self, delay: float = 0.6):
        self.delay = delay
        self.budget = Budget(max_calls=200)
        self.turns_by_persona: dict[str, int] = {}

    async def complete_json(self, tier: Tier, messages: list[dict], vision: bool = False) -> dict:
        self.budget.reserve()
        await asyncio.sleep(self.delay)
        self.budget.record(1000)
        if vision:
            return {"on_screen": "(Demo model, not a real reading.) A page with a heading and some buttons.",
                    "what_it_is": "not clear (demo model)", "main_action": "none visible",
                    "next_step": "(demo model) scroll down", "problems": []}
        system = messages[0]["content"]
        everything = "\n".join(m["content"] for m in messages)
        last = messages[-1]["content"]
        evidence = _evidence(messages)
        who = hashlib.md5(system[:200].encode()).hexdigest()
        stance = STANCES[int(who, 16) % 3]

        if "moderator of a review panel" in system:
            return {"headline": "Demo summary: the panel is split", "agreed": ["(demo model) a shared point"],
                    "split": ["(demo model) a disagreement"], "top_changes": ["(demo model) the top fix"]}
        if "one-on-one conversation" in everything:
            return {"message": f"(Demo model, not a real opinion.) You said: \"{last[:80]}\". "
                               "Here is a canned reply that cites the brief.",
                    "claims": evidence[:1], "stance": stance, "question": None}
        if "first impression" in last:
            q = ["Who is this project for?"] if int(who, 16) % 2 else []
            return {"stance": stance, "headline": f"(demo) first take: {stance}", "claims": evidence[:2], "questions": q}
        if "your turn in the debate" in last:
            n = self.turns_by_persona.get(who, 0)
            self.turns_by_persona[who] = n + 1
            ids = re.findall(r"^- ([a-z_]+): ", last, flags=re.M)
            return {"message": "(Demo model, not a real opinion.) I push back on another reviewer, "
                               "citing the brief.", "claims": evidence[:1], "stance": stance,
                    "stance_change_reason": None, "new_point": n == 0, "challenges": ids[:1],
                    "open_question": "Is there a deployed version?" if n == 0 and int(who, 16) % 3 == 0 else None}
        return {"verdict": stance, "headline": f"(demo) final: {stance}", "reasons": evidence[:2],
                "what_would_change_my_mind": ["(demo model) a concrete change"], "questions": []}


def _evidence(messages: list[dict]) -> list[dict]:
    """Quote real lines from the brief so claims verify."""
    for m in messages:
        c = m["content"]
        if isinstance(c, str) and c.startswith("<project_brief>"):
            brief = json.loads(c[len("<project_brief>"):-len("</project_brief>")])
            out = []
            for path, text in brief["files"].items():
                line = next((l.strip() for l in text.splitlines() if len(l.strip()) >= 12), None)
                if line:
                    out.append({"text": f"(demo) a point about {path}",
                                "evidence": {"kind": "file", "ref": path, "quote": line[:80]}})
                if len(out) == 2:
                    break
            return out
    return []
