"""Merge near-duplicate questions from all personas before the user sees them. Plain code."""

import re

from jury.models import MergedQuestion, VerifiedImpression
from jury.room.state import MAX_QUESTIONS_SHOWN, RoomState

NODE = "dedupe_questions"
SIMILARITY = 0.5

_STOP = {
    "the", "a", "an", "is", "are", "was", "do", "does", "did", "you", "your", "this", "that",
    "it", "its", "of", "to", "in", "on", "for", "and", "or", "with", "how", "what", "who",
    "why", "when", "which", "there", "any", "can", "will", "would", "be", "have", "has",
    "project", "app", "tool", "repo",
}


def _tokens(text: str) -> set[str]:
    """Key words, cut to a 4-letter stem so build/built and deploy/deployed match."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w[:4] for w in words if w not in _STOP and len(w) > 2}


def contained(a: set[str], b: set[str], threshold: float = 0.6) -> bool:
    """Most of the smaller question's key words appear in the other one."""
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= threshold


def _similar(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= SIMILARITY


def dedupe_questions(asked: list[tuple[str, str]], limit: int = MAX_QUESTIONS_SHOWN) -> list[MergedQuestion]:
    """`asked` is [(persona_id, question)] in ask order.

    Questions with overlapping key words merge into one, keeping the first wording
    and every persona that asked. Most-asked first, then ask order; capped at `limit`.
    """
    groups: list[tuple[str, set[str], list[str]]] = []  # text, tokens, askers
    for persona_id, question in asked:
        q = " ".join(question.split())
        if not q:
            continue
        toks = _tokens(q)
        for text, gtoks, askers in groups:
            if _similar(toks, gtoks) or q.lower() == text.lower():
                gtoks |= toks
                if persona_id not in askers:
                    askers.append(persona_id)
                break
        else:
            groups.append((q, toks, [persona_id]))

    ranked = sorted(enumerate(groups), key=lambda ig: (-len(ig[1][2]), ig[0]))[:limit]
    return [MergedQuestion(id=f"q{i}", text=g[0], asked_by=g[2]) for i, (_, g) in enumerate(ranked, 1)]


def node(state: RoomState) -> dict:
    asked: list[tuple[str, str]] = []
    for pid in state["persona_ids"]:  # stable persona order, not completion order
        raw = state.get("impressions", {}).get(pid)
        if raw:
            asked += [(pid, q) for q in VerifiedImpression.model_validate(raw).impression.questions]
    return {"questions": [q.model_dump() for q in dedupe_questions(asked)]}


def has_questions(state: RoomState) -> bool:
    return bool(state.get("questions"))
