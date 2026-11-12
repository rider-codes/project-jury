"""Run a room from the terminal and print the live event stream.

New review:   python -m jury.room --brief brief.json [--personas senior_engineer,product_manager]
Resume later: python -m jury.room --thread <id>
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from jury.llm import LLM, LLMError
from jury.models import Brief
from jury.personas import load_all
from jury.room.events import stream_events
from jury.room.graph import build_graph, initial_state
from jury.room.state import DEFAULT_ROOM


def print_event(e: dict, names: dict[str, str]) -> None:
    t = e["type"]
    if t == "impression":
        print(f"\n[{names.get(e['persona_id'], e['persona_id'])}]  {e['stance'].upper()}  {e['headline']}")
        for c in e["claims"]:
            ev = c["evidence"]
            print(f"  - {c['text']}\n      ({ev['kind']}: {ev['ref']}) \"{ev['quote']}\"")
        for r in e["rejected"]:
            print(f"  x dropped: {r['text']}  ({r['problem']})")
    elif t == "agent_error":
        print(f"\n[{names.get(e['persona_id'], e['persona_id'])}]  could not answer: {e['error']}")
    elif t == "questions_merged":
        print(f"\n{len(e['questions'])} question(s) for you after merging duplicates.")
    elif t == "answers_received":
        print(f"\nGot {sum(1 for a in e['answers'].values() if a)} answer(s).")
    elif t == "router":
        if e["action"] == "speak":
            print(f"\n  moderator: {names.get(e['speaker'], e['speaker'])} speaks next ({e['reason']})")
        elif e["action"] == "end":
            print(f"\n  moderator: debate over ({e['reason']}). Final verdicts:")
    elif t == "debate_turn":
        who = names.get(e["speaker"], e["speaker"])
        if e.get("error"):
            print(f"[{who}] could not respond: {e['error']}")
            return
        tag = f"  changed stance to {e['stance'].upper()}: {e['stance_change_reason']}" if e["stance_changed"] else ""
        print(f"[{who}] {e['message']}{tag}")
        for c in e["claims"]:
            ev = c["evidence"]
            print(f"      ({ev['kind']}: {ev['ref']}) \"{ev['quote']}\"")
        if e["challenges"]:
            print(f"      challenges: {', '.join(names.get(p, p) for p in e['challenges'])}")
    elif t == "verdict":
        print(f"\n[{names.get(e['persona_id'], e['persona_id'])}]  {e['verdict'].upper()}  {e['headline']}")
        for c in e["reasons"]:
            print(f"  - {c['text']}  ({c['evidence']['ref']})")
        for w in e["what_would_change_my_mind"]:
            print(f"  would change my mind: {w}")
    elif t == "summary":
        print(f"\n=== Summary: {e['headline']} ===")
        for label in ("agreed", "split", "top_changes"):
            for item in e.get(label, []):
                print(f"  {label.replace('_', ' ')}: {item}")
    elif t == "done":
        print("\nReview complete.")


def ask_in_terminal(questions: list[dict], names: dict[str, str]) -> dict[str, str]:
    print("\nThe room has questions (press Enter to skip one):")
    answers = {}
    for q in questions:
        who = ", ".join(names.get(p, p) for p in q["asked_by"])
        print(f"\n{q['id']}. {q['text']}\n   asked by: {who}")
        answers[q["id"]] = input("   > ")
    return answers


async def run(args) -> None:
    personas = load_all()
    names = {pid: p.name for pid, p in personas.items()}
    llm = LLM.from_env()
    thread = args.thread or uuid.uuid4().hex[:12]
    config = {"configurable": {"thread_id": thread}}

    async with AsyncSqliteSaver.from_conn_string(str(args.db)) as saver:
        graph = build_graph(llm, personas, saver)
        existing = await graph.aget_state(config)

        if args.thread and existing.values:
            if not existing.next:
                print(f"Review {thread} is already complete.")
                return
            graph_input = Command(resume=ask_in_terminal(existing.interrupts[0].value["questions"], names))
        else:
            if not args.brief:
                sys.exit("--brief is required for a new review")
            ids = [p.strip() for p in args.personas.split(",") if p.strip()]
            unknown = [p for p in ids if p not in personas]
            if unknown:
                sys.exit(f"unknown persona(s): {', '.join(unknown)}. Available: {', '.join(personas)}")
            brief = Brief.model_validate(json.loads(args.brief.read_text(encoding="utf-8")))
            graph_input = initial_state(brief.model_dump(), ids)
            print(f"Review {thread}: {brief.project_name} with {', '.join(names[i] for i in ids)}")

        while True:
            pending = None
            async for event in stream_events(graph, graph_input, config):
                print_event(event, names)
                if event["type"] == "needs_answers":
                    pending = event["questions"]
            if pending is None:
                break
            if args.no_wait:
                print(f"\nPaused. Resume with: python -m jury.room --thread {thread}")
                break
            graph_input = Command(resume=ask_in_terminal(pending, names))

    print(f"\nModel use: {llm.budget.calls} call(s), {llm.budget.tokens} tokens")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a review room.")
    parser.add_argument("--brief", type=Path)
    parser.add_argument("--personas", default=",".join(DEFAULT_ROOM))
    parser.add_argument("--thread", help="resume this review id")
    parser.add_argument("--db", type=Path, default=Path("jury.sqlite"))
    parser.add_argument("--no-wait", action="store_true", help="stop at questions instead of asking now")
    args = parser.parse_args()
    load_dotenv()
    try:
        asyncio.run(run(args))
    except LLMError as e:
        sys.exit(f"Model setup problem: {e}")


if __name__ == "__main__":
    main()
