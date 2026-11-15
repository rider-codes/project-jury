"""Round 2 node: the speaker the router picked takes one turn."""

from jury.agent import JsonModel, debate_turn
from jury.models import Brief, Persona
from jury.room.context import render
from jury.room.state import RoomState, active_personas, builder_answers, current_stances

NODE = "debate_turn"


def make_node(llm: JsonModel, personas: dict[str, Persona]):
    async def node(state: RoomState) -> dict:
        pid = state["next_action"]["speaker"]
        before = current_stances(state).get(pid, "unsure")
        um = state.get("user_message")
        addressed = bool(um)  # the router picked this speaker to answer the builder
        others = {p: personas[p].name for p in active_personas(state) if p != pid}
        contrarian = bool(state["next_action"].get("contrarian"))
        base = {"speaker": pid, "addressed_by_user": addressed, "contrarian": contrarian,
                "user_text": um["text"] if addressed else None}
        update: dict = {"user_message": None} if addressed else {}

        try:
            turn, rejected = await debate_turn(
                llm, personas[pid], Brief.model_validate(state["brief"]), render(state, personas),
                before, others, um["text"] if addressed else None, contrarian=contrarian,
                answers=builder_answers(state),
            )
        except Exception as e:  # a failed turn still counts, so the debate cannot loop
            update["turns"] = [{**base, "error": f"{type(e).__name__}: {e}"[:500], "message": "", "claims": [],
                                "rejected": [], "stance": before, "stance_changed": False,
                                "stance_change_reason": None, "new_point": False, "challenges": [],
                                "open_question": None}]
            return update

        changed = turn.stance.value != before and bool((turn.stance_change_reason or "").strip())
        update["turns"] = [{
            **base,
            "message": turn.message,
            "claims": [c.model_dump(mode="json") for c in turn.claims],
            "rejected": [{"text": r.claim.text, "problem": r.problem} for r in rejected],
            # a stance change without a stated reason is ignored
            "stance": turn.stance.value if changed else before,
            "stance_changed": changed,
            "stance_change_reason": turn.stance_change_reason if changed else None,
            "ignored_stance_change": turn.stance.value != before and not changed,
            "new_point": turn.new_point,
            "challenges": turn.challenges,
            "open_question": (turn.open_question or "").strip() or None,
        }]
        return update

    return node
