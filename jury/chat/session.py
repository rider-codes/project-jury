"""A one-on-one chat with one persona about one project."""

import uuid
from dataclasses import dataclass, field

from jury.agent import JsonModel, chat_reply
from jury.models import Brief, Persona

MAX_HISTORY_MESSAGES = 12  # older messages are dropped from the prompt (kept in the store)
MAX_USER_CHARS = 4_000


@dataclass
class ChatSession:
    persona_id: str
    brief: dict  # Brief
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    room_thread: str | None = None  # the room this chat was started from, if any
    room_context: str = ""  # snapshot of that room's transcript; empty = clean start
    messages: list[dict] = field(default_factory=list)  # [{"role": "user"|"agent", "text", ...}]

    def prompt_history(self) -> list[dict]:
        return self.messages[-MAX_HISTORY_MESSAGES:]

    def stance(self) -> str | None:
        return next((m["stance"] for m in reversed(self.messages) if m["role"] == "agent"), None)

    async def send(self, llm: JsonModel, persona: Persona, user_text: str) -> dict:
        """Ask the persona; returns the agent message (also appended to `messages`)."""
        if persona.id != self.persona_id:
            raise ValueError(f"this chat is with {self.persona_id}, not {persona.id}")
        text = " ".join(user_text.split())[:MAX_USER_CHARS]
        if not text:
            raise ValueError("empty message")
        reply, rejected = await chat_reply(
            llm, persona, Brief.model_validate(self.brief), self.prompt_history(), text, self.room_context
        )
        before = self.stance()
        agent = {
            "role": "agent",
            "text": reply.message,
            "claims": [c.model_dump(mode="json") for c in reply.claims],
            "rejected": [{"text": r.claim.text, "problem": r.problem} for r in rejected],
            "stance": reply.stance.value,
            "stance_changed": before is not None and before != reply.stance.value,
            "question": (reply.question or "").strip() or None,
        }
        # only append once the model call succeeded, so a failed send leaves history intact
        self.messages += [{"role": "user", "text": text}, agent]
        return agent
