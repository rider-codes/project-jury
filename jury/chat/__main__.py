"""Chat one-on-one with a single persona.

Clean start:        python -m jury.chat --persona senior_engineer --brief brief.json
From a past room:   python -m jury.chat --persona senior_engineer --room <review id>
Resume a chat:      python -m jury.chat --chat <chat id>
List chats:         python -m jury.chat --list

Type your message and press Enter. Type /quit to leave (the chat is saved).
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from jury.chat.room_history import load_room
from jury.chat.session import ChatSession
from jury.chat.store import ChatStore
from jury.llm import LLM, LLMError
from jury.models import Brief
from jury.personas import load_all


def print_reply(name: str, m: dict) -> None:
    change = "  (changed stance)" if m["stance_changed"] else ""
    print(f"\n[{name} | {m['stance']}{change}] {m['text']}")
    for c in m["claims"]:
        ev = c["evidence"]
        print(f"      ({ev['kind']}: {ev['ref']}) \"{ev['quote']}\"")
    for r in m["rejected"]:
        print(f"      x dropped: {r['text']} ({r['problem']})")
    if m["question"]:
        print(f"      asks you: {m['question']}")


async def run(args) -> None:
    personas = load_all()
    store = ChatStore(args.db)

    if args.list:
        for c in store.list():
            src = f"from room {c['room_thread']}" if c["room_thread"] else "clean start"
            print(f"{c['id']}  {c['persona_id']:24} {c['messages']:3} messages  {src}  {c['updated_at']}")
        return

    if args.chat:
        session = store.load(args.chat)
        if session is None:
            sys.exit(f"no chat with id {args.chat}")
    else:
        if not args.persona or args.persona not in personas:
            sys.exit(f"--persona is required, one of: {', '.join(personas)}")
        if args.room:
            brief, context, _ = await load_room(str(args.db), args.room, personas)
            session = ChatSession(persona_id=args.persona, brief=brief, room_thread=args.room, room_context=context)
        elif args.brief:
            brief = Brief.model_validate(json.loads(args.brief.read_text(encoding="utf-8")))
            session = ChatSession(persona_id=args.persona, brief=brief.model_dump())
        else:
            sys.exit("give --brief for a clean start, or --room to start from a past review")
        store.save(session)

    persona = personas[session.persona_id]
    llm = LLM.from_env()
    start = f"with room {session.room_thread}'s history" if session.room_thread else "clean start"
    print(f"Chat {session.id} with {persona.name} about {session.brief['project_name']} ({start}).")
    print(f"Their question: {persona.verdict_question}  Type /quit to leave.")
    for m in session.messages[-6:]:
        print(f"\n{'you' if m['role'] == 'user' else persona.name}: {m['text']}")

    while True:
        try:
            text = input("\nyou > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text in ("/quit", "/exit"):
            break
        if not text:
            continue
        try:
            reply = await session.send(llm, persona, text)
        except Exception as e:  # keep the chat alive; nothing was added to history
            print(f"  could not get a reply: {e}")
            continue
        store.save(session)
        print_reply(persona.name, reply)

    print(f"\nSaved. Resume with: python -m jury.chat --chat {session.id}")
    print(f"Model use this run: {llm.budget.calls} call(s), {llm.budget.tokens} tokens")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat one-on-one with one persona.")
    parser.add_argument("--persona")
    parser.add_argument("--brief", type=Path, help="clean start from this brief")
    parser.add_argument("--room", help="start from this past room review id")
    parser.add_argument("--chat", help="resume this chat id")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--db", type=Path, default=Path("jury.sqlite"))
    args = parser.parse_args()
    load_dotenv()
    try:
        asyncio.run(run(args))
    except (LLMError, LookupError) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
