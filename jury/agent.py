"""One engine for every persona: build the prompt, call the model, validate, verify."""

import json
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from jury.models import (
    Brief,
    ChatReply,
    ClaimCheck,
    DebateTurn,
    FirstImpression,
    Persona,
    Tier,
    Verdict,
    VerifiedImpression,
    VerifiedVerdict,
)
from jury.verifier import verify, verify_claims

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


class JsonModel(Protocol):
    async def complete_json(self, tier: Tier, messages: list[dict]) -> dict: ...


def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items)


def system_message(persona: Persona) -> str:
    persona_text = _prompt("persona.md").format(
        system_prompt=persona.system_prompt.strip(),
        voice=persona.voice.strip(),
        cares_about=_bullets(persona.cares_about),
        rubric=_bullets([f"{r.id}: check {r.check} Fails when {r.fail_when}" for r in persona.rubric]),
        question_triggers=_bullets(persona.question_triggers),
    )
    return persona_text + "\n\n" + _prompt("rules.md")


def brief_message(brief: Brief) -> str:
    """The brief is wrapped as data so text inside it is never read as instructions."""
    payload = json.dumps(brief.model_dump(), indent=1, ensure_ascii=False)
    return f"<project_brief>\n{payload}\n</project_brief>"


M = TypeVar("M", bound=BaseModel)


async def ask_structured(
    llm: JsonModel, tier: Tier, messages: list[dict], schema: type[M], label: str, max_attempts: int = 2
) -> M:
    """Call the model and validate against `schema`, asking once more if the JSON is wrong."""
    last_error = ""
    for _ in range(max_attempts):
        data = await llm.complete_json(tier, messages)
        try:
            return schema.model_validate(data)
        except ValidationError as e:
            last_error = str(e)[:500]
            messages = messages + [
                {"role": "assistant", "content": json.dumps(data)},
                {"role": "user", "content": f"That JSON did not match the schema: {last_error}. Reply again with valid JSON only."},
            ]
    raise ValueError(f"{label}: no valid reply after {max_attempts} attempts: {last_error}")


def base_messages(persona: Persona, brief: Brief) -> list[dict]:
    return [
        {"role": "system", "content": system_message(persona)},
        {"role": "user", "content": brief_message(brief)},
    ]


async def first_impression(llm: JsonModel, persona: Persona, brief: Brief) -> VerifiedImpression:
    """Round 1: always on the cheap tier, no tools."""
    messages = base_messages(persona, brief) + [
        {"role": "user", "content": _prompt("first_impression.md").format(verdict_question=persona.verdict_question)},
    ]
    imp = await ask_structured(llm, Tier.cheap, messages, FirstImpression, persona.id)
    kept, rejected = verify_claims(imp.claims, brief)
    return VerifiedImpression(
        persona_id=persona.id, impression=imp.model_copy(update={"claims": kept}), rejected=rejected
    )


async def debate_turn(
    llm: JsonModel,
    persona: Persona,
    brief: Brief,
    context: str,
    stance: str,
    others: dict[str, str],  # persona_id -> name
    user_message: str | None = None,
    contrarian: bool = False,
    answers: dict[str, str] | None = None,  # the builder's answers by question id, citable as evidence
) -> tuple[DebateTurn, list[ClaimCheck]]:
    """Round 2: one turn on the persona's own tier. Claims are verified like any other."""
    um = f"\nThe builder said to the room: <user_message>{user_message}</user_message>\nRespond to it.\n" if user_message else ""
    prompt = _prompt("debate_turn.md").format(
        stance=stance,
        verdict_question=persona.verdict_question,
        others=_bullets([f"{pid}: {name}" for pid, name in others.items()]),
        user_message=um + (_prompt("contrarian.md") if contrarian else ""),
    )
    messages = base_messages(persona, brief) + [
        {"role": "user", "content": context},
        {"role": "user", "content": prompt},
    ]
    turn = await ask_structured(llm, persona.model, messages, DebateTurn, persona.id)
    kept, rejected = verify_claims(turn.claims, brief, answers)
    challenges = [c for c in dict.fromkeys(turn.challenges) if c in others]
    return turn.model_copy(update={"claims": kept, "challenges": challenges}), rejected


async def chat_reply(
    llm: JsonModel,
    persona: Persona,
    brief: Brief,
    history: list[dict],  # [{"role": "user" | "agent", "text": ...}], oldest first
    user_text: str,
    room_context: str = "",
) -> tuple[ChatReply, list[ClaimCheck]]:
    """One-on-one mode: no room, no router. Claims are verified like everywhere else."""
    messages = base_messages(persona, brief)
    if room_context:
        messages.append({"role": "user", "content": "Earlier, you sat on a review panel for this project:\n" + room_context})
    messages.append({"role": "user", "content": _prompt("chat_turn.md").format(verdict_question=persona.verdict_question)})
    for m in history:
        messages.append({"role": "assistant" if m["role"] == "agent" else "user", "content": m["text"]})
    messages.append({"role": "user", "content": user_text})
    reply = await ask_structured(llm, persona.model, messages, ChatReply, persona.id)
    kept, rejected = verify_claims(reply.claims, brief)
    return reply.model_copy(update={"claims": kept}), rejected


async def final_verdict(
    llm: JsonModel, persona: Persona, brief: Brief, max_attempts: int = 2, context: str = "",
    answers: dict[str, str] | None = None,
) -> VerifiedVerdict:
    messages = base_messages(persona, brief)
    if context:
        messages.append({"role": "user", "content": context})
    messages.append(
        {"role": "user", "content": _prompt("verdict.md").format(verdict_question=persona.verdict_question)}
    )
    verdict = await ask_structured(llm, persona.model, messages, Verdict, persona.id, max_attempts)
    return verify(persona.id, verdict, brief, answers)
