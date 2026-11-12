"""Moderator, implemented as code. Picks the next speaker, routes open questions to
the user, and ends the debate. No model call is ever made here.

Order of rules:
0. The budget can no longer cover the verdicts and summary -> end now.
1. The latest turn has an open question not yet asked -> ask the user, at most
   2 times per debate, and never a question the user was already asked.
2. Turn cap reached (2 per agent, 12 total at most) -> end.
3. A full round passed with no new point and no stance change -> end.
4. The user addressed one persona that still has turns -> that persona speaks.
5. Nobody but the last speaker has turns left -> end (nobody speaks twice in a row).
6. Otherwise the most challenged persona speaks (not the one who just spoke, and
   only among those who have not spoken yet until everyone has had a turn):
   explicit challenges since they last spoke, then how many others disagree
   with their stance, then fewest turns, then room order.
"""

from collections import Counter
from dataclasses import dataclass

from langgraph.types import Send

from jury.models import RouterDecision
from jury.room.dedupe import _tokens, contained
from jury.room.state import RoomState, VerdictTask, active_personas, current_stances

NODE = "debate_router"


@dataclass(frozen=True)
class Caps:
    per_agent: int = 2
    max_total: int = 12
    max_debate_questions: int = 2  # pauses after round 1; more and the room nags the user

    def total_for(self, n_agents: int) -> int:
        return min(self.max_total, self.per_agent * n_agents)


def decide(
    active: list[str],
    stances: dict[str, str],
    turns: list[dict],
    asked_turns: set[int],
    user_message: dict | None = None,
    caps: Caps = Caps(),
    asked_texts: list[str] = (),
    budget_ok: bool = True,
) -> RouterDecision:
    if not active:
        return RouterDecision(action="end", reason="nobody is left to debate")

    if not budget_ok:  # the verdicts matter more than one more debate turn
        return RouterDecision(action="end", reason="stopping to keep enough budget for the final verdicts")

    if turns:
        last_i = len(turns) - 1
        q = turns[last_i].get("open_question")
        if (
            q
            and last_i not in asked_turns
            and len(asked_turns) < caps.max_debate_questions
            and not is_repeat(q, asked_texts)
        ):
            return RouterDecision(action="ask_user", speaker=turns[last_i]["speaker"],
                                  reason="an agent has an open question")

    total = caps.total_for(len(active))
    if len(turns) >= total:
        return RouterDecision(action="end", reason=f"turn cap reached ({total} turns)")

    k = len(active)
    if len(turns) >= k and all(not t.get("new_point") and not t.get("stance_changed") for t in turns[-k:]):
        return RouterDecision(action="end", reason="a full round with no new points or stance changes")

    counts = Counter(t["speaker"] for t in turns)
    eligible = [p for p in active if counts[p] < caps.per_agent]
    if not eligible:
        return RouterDecision(action="end", reason="every agent has used its turns")

    to = (user_message or {}).get("to")
    if to in eligible:
        return RouterDecision(action="speak", speaker=to, reason="the user addressed them")

    last = turns[-1]["speaker"] if turns else None
    candidates = [p for p in eligible if p != last]
    if not candidates:  # only the last speaker has turns left; they would be answering themselves
        return RouterDecision(action="end", reason="only the last speaker has turns left")
    # everyone speaks once before anyone speaks twice, so two agents cannot hog the room
    unheard = [p for p in candidates if counts[p] == 0]
    if unheard:
        candidates = unheard

    def challenged_since_spoke(p: str) -> int:
        since = max((i for i, t in enumerate(turns) if t["speaker"] == p), default=-1) + 1
        return sum(1 for t in turns[since:] if t["speaker"] != p and p in (t.get("challenges") or []))

    def disagreement(p: str) -> int:
        return sum(1 for q in active if q != p and stances.get(q) != stances.get(p))

    def score(p: str) -> tuple:
        return (challenged_since_spoke(p), disagreement(p), -counts[p], -active.index(p))

    best = max(candidates, key=score)
    c, d = challenged_since_spoke(best), disagreement(best)
    if c:
        reason = f"most challenged ({c} challenge{'s' if c > 1 else ''} since they last spoke)"
    elif d:
        reason = f"their stance is disputed by {d} other agent{'s' if d > 1 else ''}"
    else:
        reason = "has spoken least"
    return RouterDecision(action="speak", speaker=best, reason=reason)


def is_repeat(question: str, asked_texts) -> bool:
    """True if the user was already asked this, in other words."""
    toks = _tokens(question)
    return any(contained(toks, _tokens(t)) for t in asked_texts)


def reserve_ok(llm, n_active: int) -> bool:
    """Can the budget still pay for one more debate turn, then every verdict and the summary?"""
    budget = getattr(llm, "budget", None)
    if budget is None or not hasattr(budget, "can_afford"):
        return True
    return budget.can_afford(1 + n_active + 1)


def make_node(llm):
    def node(state: RoomState) -> dict:
        return _node(state, reserve_ok(llm, len(active_personas(state))))

    return node


def node(state: RoomState) -> dict:  # budget-blind variant, kept for tests and callers without a model
    return _node(state, True)


def _node(state: RoomState, budget_ok: bool) -> dict:
    turns = state.get("turns") or []
    decision = decide(
        active_personas(state),
        current_stances(state),
        turns,
        set(state.get("asked_turns") or []),
        state.get("user_message"),
        asked_texts=[q["text"] for q in state.get("qa_log") or []],
        budget_ok=budget_ok,
    )
    update: dict = {"next_action": decision.model_dump()}
    if decision.action == "ask_user":
        i = len(turns) - 1
        update["questions"] = [{"id": f"d{i + 1}", "text": turns[i]["open_question"], "asked_by": [turns[i]["speaker"]]}]
        update["asked_turns"] = [i]
    return update


def route(state: RoomState, render_context) -> str | list[Send]:
    """Edge after the router: next node, or the round 3 fan-out."""
    action = state["next_action"]["action"]
    if action == "speak":
        return "debate_turn"
    if action == "ask_user":
        return "ask_user"
    active = active_personas(state)
    if not active:
        return "summary"
    context = render_context(state)
    return [Send("final_verdict", VerdictTask(persona_id=p, brief=state["brief"], context=context)) for p in active]
