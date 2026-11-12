import asyncio
import json
from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from jury.chat.room_history import load_room
from jury.chat.session import MAX_HISTORY_MESSAGES, ChatSession
from jury.chat.store import ChatStore
from jury.personas import load_all
from jury.room.events import stream_events
from jury.room.graph import build_graph, initial_state

BRIEF = json.loads((Path(__file__).parent.parent / "examples" / "sample_brief.json").read_text(encoding="utf-8"))
PERSONAS = load_all()
SE = PERSONAS["senior_engineer"]
REAL = {"text": "tests are fake", "evidence": {"kind": "file", "ref": "tests/test_cli.py", "quote": "assert True"}}
FAKE = {"text": "has CI", "evidence": {"kind": "file", "ref": ".github/ci.yml", "quote": "runs-on"}}


class ChatLLM:
    def __init__(self, stances=("not useful",), fail=False):
        self.stances = list(stances)
        self.fail = fail
        self.seen: list[list[dict]] = []

    async def complete_json(self, tier, messages):
        self.seen.append(messages)
        if self.fail:
            raise RuntimeError("provider down")
        stance = self.stances.pop(0) if len(self.stances) > 1 else self.stances[0]
        return {"message": f"reply to: {messages[-1]['content'][:20]}", "claims": [REAL, FAKE],
                "stance": stance, "question": "Is CI elsewhere?"}


def test_clean_start_has_no_room_history_and_verifies_claims():
    s = ChatSession(persona_id="senior_engineer", brief=BRIEF)
    llm = ChatLLM()
    reply = asyncio.run(s.send(llm, SE, "  What do   you think?  "))
    prompt = "\n".join(m["content"] for m in llm.seen[0])
    assert "review panel" not in prompt and "<room_transcript>" not in prompt
    assert llm.seen[0][-1] == {"role": "user", "content": "What do you think?"}
    assert len(reply["claims"]) == 1 and reply["rejected"][0]["problem"].startswith("file not in brief")
    assert reply["question"] == "Is CI elsewhere?"
    assert [m["role"] for m in s.messages] == ["user", "agent"]


def test_history_is_sent_in_order_and_trimmed():
    s = ChatSession(persona_id="senior_engineer", brief=BRIEF)
    llm = ChatLLM()
    for i in range(10):
        asyncio.run(s.send(llm, SE, f"message {i}"))
    assert len(s.messages) == 20  # everything kept in the session
    last = llm.seen[-1]
    history = last[3:-1]  # after system, brief, chat prompt; before the new message
    assert len(history) == MAX_HISTORY_MESSAGES
    assert [m["role"] for m in history[:2]] == ["user", "assistant"]
    assert history[-1]["content"].startswith("reply to: message 8")


def test_failed_send_leaves_history_unchanged():
    s = ChatSession(persona_id="senior_engineer", brief=BRIEF)
    with pytest.raises(RuntimeError):
        asyncio.run(s.send(ChatLLM(fail=True), SE, "hi"))
    assert s.messages == []


def test_stance_change_is_flagged():
    s = ChatSession(persona_id="senior_engineer", brief=BRIEF)
    llm = ChatLLM(stances=["not useful", "unsure"])
    assert not asyncio.run(s.send(llm, SE, "a"))["stance_changed"]
    assert asyncio.run(s.send(llm, SE, "b"))["stance_changed"]
    assert s.stance() == "unsure"


def test_rejects_wrong_persona_and_empty_message():
    s = ChatSession(persona_id="senior_engineer", brief=BRIEF)
    with pytest.raises(ValueError):
        asyncio.run(s.send(ChatLLM(), PERSONAS["ux_designer"], "hi"))
    with pytest.raises(ValueError):
        asyncio.run(s.send(ChatLLM(), SE, "   "))


def test_store_round_trip_and_list(tmp_path):
    store = ChatStore(tmp_path / "j.sqlite")
    s = ChatSession(persona_id="senior_engineer", brief=BRIEF)
    store.save(s)
    asyncio.run(s.send(ChatLLM(), SE, "hi"))
    store.save(s)
    loaded = store.load(s.id)
    assert loaded.messages == s.messages and loaded.brief == BRIEF and loaded.room_context == ""
    assert store.list()[0] == {**store.list()[0], "id": s.id, "messages": 2, "room_thread": None}
    assert store.load("missing") is None


def test_start_from_a_finished_room(tmp_path):
    from tests.test_room import scripted

    db = str(tmp_path / "j.sqlite")
    config = {"configurable": {"thread_id": "room-1"}}

    async def run_room():
        llm = scripted()
        async with AsyncSqliteSaver.from_conn_string(db) as saver:
            g = build_graph(llm, PERSONAS, saver)
            inp = initial_state(BRIEF, ["senior_engineer", "product_manager", "ux_designer"])
            for answers in ({"q1": "Real data", "q2": "Solo devs"}, {"d1": "No CI"}, None):
                async for _ in stream_events(g, inp, config):
                    pass
                if answers is None:
                    break
                inp = Command(resume=answers)

    asyncio.run(run_room())
    brief, context, values = asyncio.run(load_room(db, "room-1", PERSONAS))  # no model is called
    assert brief == BRIEF and values["summary"]
    assert "answer: Real data" in context and "Final verdicts:" in context

    s = ChatSession(persona_id="senior_engineer", brief=brief, room_thread="room-1", room_context=context)
    llm = ChatLLM()
    asyncio.run(s.send(llm, SE, "Why not useful?"))
    prompt = "\n".join(m["content"] for m in llm.seen[0])
    assert "Earlier, you sat on a review panel" in prompt and "Final verdicts:" in prompt

    ChatStore(db).save(s)  # chats live next to room checkpoints in the same file
    assert ChatStore(db).load(s.id).room_thread == "room-1"


def test_unknown_room_raises(tmp_path):
    with pytest.raises(LookupError):
        asyncio.run(load_room(str(tmp_path / "j.sqlite"), "nope", PERSONAS))
