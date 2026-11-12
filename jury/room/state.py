"""Graph state. Values are plain dicts (pydantic `model_dump()`), so the SQLite
checkpoint only ever holds JSON-like data. Validate with the models in
`jury.models` when reading."""

import operator
from typing import Annotated, TypedDict

DEFAULT_ROOM = ["senior_engineer", "product_manager", "ux_designer", "general_user"]
MAX_QUESTIONS_SHOWN = 6


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}


class RoomState(TypedDict, total=False):
    brief: dict  # Brief
    persona_ids: list[str]
    impressions: Annotated[dict[str, dict], merge_dicts]  # persona_id -> VerifiedImpression
    failures: Annotated[dict[str, str], merge_dicts]  # persona_id -> error text
    questions: list[dict]  # MergedQuestion: the batch currently shown to the user
    answers: Annotated[dict[str, str], merge_dicts]  # question id -> answer
    qa_log: Annotated[list[dict], operator.add]  # every question asked, with its answer

    # round 2
    turns: Annotated[list[dict], operator.add]  # debate turns in order
    next_action: dict  # RouterDecision
    asked_turns: Annotated[list[int], operator.add]  # turns whose open_question went to the user
    user_message: dict | None  # {"to": persona_id | "everyone", "text": ...}, injected by the UI

    # round 3
    verdicts: Annotated[dict[str, dict], merge_dicts]  # persona_id -> VerifiedVerdict
    verdict_failures: Annotated[dict[str, str], merge_dicts]
    summary: dict


class ImpressionTask(TypedDict):
    """Input sent to one parallel first-impression branch."""

    persona_id: str
    brief: dict


class VerdictTask(TypedDict):
    persona_id: str
    brief: dict
    context: str  # rendered room transcript


def active_personas(state: RoomState) -> list[str]:
    """Personas that gave a round 1 impression. The ones that failed sit out."""
    imps = state.get("impressions") or {}
    return [p for p in state.get("persona_ids", []) if p in imps]


def current_stances(state: RoomState) -> dict[str, str]:
    stances = {p: imp["impression"]["stance"] for p, imp in (state.get("impressions") or {}).items()}
    for t in state.get("turns") or []:
        if not t.get("error"):
            stances[t["speaker"]] = t["stance"]
    return stances
