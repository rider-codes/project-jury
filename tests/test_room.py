"""Full room runs with a scripted fake model: round 1 in parallel, the question
pause, resume after restart, debate under the code router, verdicts, summary."""

import asyncio
import json
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from jury.models import Tier
from jury.personas import load_all
from jury.room.events import stream_events
from jury.room.graph import build_graph, initial_state
from jury.room.router import Caps

BRIEF = json.loads((Path(__file__).parent.parent / "examples" / "sample_brief.json").read_text(encoding="utf-8"))
PERSONAS = load_all()
REAL = {"text": "real claim", "evidence": {"kind": "file", "ref": "tests/test_cli.py", "quote": "assert True"}}
FAKE = {"text": "invented claim", "evidence": {"kind": "file", "ref": "nope.py", "quote": "not here"}}


def impression(stance, questions=()):
    return {"stance": stance, "headline": f"{stance} headline", "claims": [REAL, FAKE], "questions": list(questions)}


def debate(stance, challenges=(), new_point=True, reason=None, question=None):
    return {"message": "I disagree, and here is why.", "claims": [REAL, FAKE], "stance": stance,
            "stance_change_reason": reason, "new_point": new_point, "challenges": list(challenges),
            "open_question": question}


def verdict(v):
    return {"verdict": v, "headline": f"{v} final", "reasons": [REAL, FAKE],
            "what_would_change_my_mind": ["real tests"], "questions": []}


SUMMARY = {"headline": "Mostly not useful yet", "agreed": ["Tests are placeholders"], "split": [], "top_changes": ["Add tests"]}


class ScriptedLLM:
    """Replies by persona and prompt kind. `debates[pid]` is consumed in order, then repeats its last item."""

    def __init__(self, impressions, debates, verdicts, summary=SUMMARY):
        self.impressions, self.debates, self.verdicts, self.summary = impressions, debates, verdicts, summary
        self.log: list[tuple[str, str, Tier]] = []
        self.in_flight = self.max_in_flight = 0

    async def complete_json(self, tier, messages):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        last, system = messages[-1]["content"], messages[0]["content"]
        if "moderator of a review panel" in system:
            self.log.append(("summary", "moderator", tier))
            return self.summary
        pid = next(p for p, persona in PERSONAS.items() if persona.system_prompt.strip()[:80] in system)
        if "first impression" in last:
            kind, reply = "impression", self.impressions[pid]
        elif "your turn in the debate" in last:
            kind, queue = "debate", self.debates[pid]
            reply = queue.pop(0) if len(queue) > 1 else queue[0]
        else:
            kind, reply = "verdict", self.verdicts[pid]
        self.log.append((kind, pid, tier))
        if reply == "boom":
            raise RuntimeError("provider down")
        return reply


ROOM = ["senior_engineer", "product_manager", "ux_designer", "general_user"]


def scripted():
    return ScriptedLLM(
        impressions={
            "senior_engineer": impression("not useful", ["Does the demo run against real data or a fixture?"]),
            "product_manager": impression("unsure", ["Is the demo using real data or fixture data?", "Who is the target user?"]),
            "ux_designer": impression("useful"),
            "general_user": "boom",  # fails round 1, sits out the rest
        },
        debates={
            "senior_engineer": [debate("not useful", ["ux_designer"], question="Is there CI in another repo?"),
                                debate("not useful", ["ux_designer"])],
            "product_manager": [debate("useful"), debate("not useful", ["ux_designer"], reason="the tests are fake")],
            "ux_designer": [debate("useful", ["senior_engineer"])],
        },
        verdicts={"senior_engineer": verdict("not useful"), "product_manager": verdict("not useful"),
                  "ux_designer": verdict("unsure")},
    )


async def collect(graph, graph_input, config):
    return [e async for e in stream_events(graph, graph_input, config)]


def test_full_review_with_pauses_restart_debate_and_verdicts(tmp_path):
    db = str(tmp_path / "room.sqlite")
    config = {"configurable": {"thread_id": "t1"}}
    llm = scripted()

    async def run(graph_input):
        async with AsyncSqliteSaver.from_conn_string(db) as saver:  # new connection and graph each time
            graph = build_graph(llm, PERSONAS, saver)
            events = await collect(graph, graph_input, config)
            return events, (await graph.aget_state(config)).values

    # --- round 1, pause for merged questions
    events, _ = asyncio.run(run(initial_state(BRIEF, ROOM)))
    assert {e["persona_id"] for e in events if e["type"] == "impression"} == {"senior_engineer", "product_manager", "ux_designer"}
    assert [e["persona_id"] for e in events if e["type"] == "agent_error"] == ["general_user"]
    assert llm.max_in_flight > 1
    assert all(t == Tier.cheap for k, _, t in llm.log if k == "impression")
    se = next(e for e in events if e["type"] == "impression" and e["persona_id"] == "senior_engineer")
    assert len(se["claims"]) == 1 and se["rejected"][0]["problem"].startswith("file not in brief")
    asked = next(e for e in events if e["type"] == "needs_answers")["questions"]
    assert len(asked) == 2 and asked[0]["asked_by"] == ["senior_engineer", "product_manager"]
    assert events[-1]["type"] == "paused"

    # --- resume after "restart": debate starts, senior engineer's open question pauses again
    calls_before = len(llm.log)
    events, _ = asyncio.run(run(Command(resume={"q1": "Real data", "q2": "", "bogus": "x"})))
    first = next(e for e in events if e["type"] == "router")
    assert first["speaker"] == "senior_engineer"  # the only 'not useful' stance in round 1
    assert events[-2]["type"] == "needs_answers" and events[-2]["questions"][0]["id"] == "d1"
    assert events[-1]["type"] == "paused"
    assert len(llm.log) == calls_before + 1  # resuming re-ran nothing from round 1

    # --- answer the debate question, debate runs to the end, verdicts and summary
    events, values = asyncio.run(run(Command(resume={"d1": "No CI anywhere"})))
    types = [e["type"] for e in events]
    assert types[-1] == "done" and "summary" in types

    turns = values["turns"]
    active = 3
    assert len(turns) <= Caps().total_for(active)  # ended within the cap
    assert all(sum(t["speaker"] == p for t in turns) <= Caps().per_agent for p in values["impressions"])
    assert all(a["speaker"] != b["speaker"] for a, b in zip(turns, turns[1:]))
    assert "general_user" not in {t["speaker"] for t in turns}
    assert all(t == PERSONAS[p].model for k, p, t in llm.log if k == "debate")  # persona's own tier

    # stance changes need a reason
    assert {t["speaker"] for t in turns[:3]} == {"senior_engineer", "product_manager", "ux_designer"}
    pm = [t for t in turns if t["speaker"] == "product_manager"]
    assert len(pm) == 2
    assert pm[0]["stance"] == "unsure" and pm[0]["ignored_stance_change"]  # 'useful' with no reason: ignored
    assert pm[1]["stance_changed"] and pm[1]["stance"] == "not useful"

    # every answer reached the transcript the verdict agents read
    assert {q["id"]: q["answer"] for q in values["qa_log"]} == {"q1": "Real data", "q2": "", "d1": "No CI anywhere"}

    # round 3: one verified verdict per active persona, then a model summary with a code tally
    assert set(values["verdicts"]) == {"senior_engineer", "product_manager", "ux_designer"}
    assert all(len(v["verdict"]["reasons"]) == 1 for v in values["verdicts"].values())
    s = values["summary"]
    assert s["tally"] == {"useful": 0, "unsure": 1, "not useful": 2}
    assert s["generated_by"] == "model" and s["headline"] == "Mostly not useful yet"
    json.dumps(values)  # checkpoint holds plain data only


def test_stale_debate_ends_after_one_full_round():
    llm = ScriptedLLM(
        impressions={p: impression("unsure") for p in ROOM[:3]},
        debates={p: [debate("unsure", new_point=False)] for p in ROOM[:3]},
        verdicts={p: verdict("unsure") for p in ROOM[:3]},
    )

    async def go():
        from langgraph.checkpoint.memory import InMemorySaver
        graph = build_graph(llm, PERSONAS, InMemorySaver())
        config = {"configurable": {"thread_id": "s"}}
        events = await collect(graph, initial_state(BRIEF, ROOM[:3]), config)
        return events, (await graph.aget_state(config)).values

    events, values = asyncio.run(go())
    assert len(values["turns"]) == 3
    end = next(e for e in events if e["type"] == "router" and e["action"] == "end")
    assert "no new points" in end["reason"]
    assert events[-1]["type"] == "done"


def test_tight_budget_cuts_the_debate_not_the_verdicts():
    """Regression for the ledgerline run: the cap ran out mid-review and all 4 verdicts were lost."""
    from langgraph.checkpoint.memory import InMemorySaver
    from jury.llm import Budget

    class BudgetedLLM(ScriptedLLM):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.budget = Budget(max_calls=60, max_tokens=400_000)

        async def complete_json(self, tier, messages):
            self.budget.reserve()
            self.budget.record(45_000)
            return await super().complete_json(tier, messages)

    ids = ROOM[:4]
    llm = BudgetedLLM(
        impressions={p: impression("unsure") for p in ids},
        debates={p: [debate("unsure", [q for q in ids if q != p][:1])] for p in ids},
        verdicts={p: verdict("unsure") for p in ids},
    )

    async def go():
        graph = build_graph(llm, PERSONAS, InMemorySaver())
        config = {"configurable": {"thread_id": "b"}}
        events = await collect(graph, initial_state(BRIEF, ids), config)
        return events, (await graph.aget_state(config)).values

    events, values = asyncio.run(go())
    end = next(e for e in events if e["type"] == "router" and e["action"] == "end")
    assert "budget" in end["reason"]
    assert len(values["turns"]) < Caps().total_for(4)  # debate was cut short
    assert set(values["verdicts"]) == set(ids)  # but every verdict arrived
    assert not values.get("verdict_failures")
    # the cap is checked before each call, so the last parallel calls may overshoot by less than one call
    assert llm.budget.tokens < llm.budget.max_tokens + 45_000


def test_summary_falls_back_to_code_when_model_fails():
    llm = ScriptedLLM(
        impressions={p: impression("useful") for p in ROOM[:2]},
        debates={p: [debate("useful", new_point=False)] for p in ROOM[:2]},
        verdicts={"senior_engineer": verdict("useful"), "product_manager": "boom"},
        summary="boom",
    )

    async def go():
        from langgraph.checkpoint.memory import InMemorySaver
        graph = build_graph(llm, PERSONAS, InMemorySaver())
        config = {"configurable": {"thread_id": "f"}}
        events = await collect(graph, initial_state(BRIEF, ROOM[:2]), config)
        return events, (await graph.aget_state(config)).values

    events, values = asyncio.run(go())
    assert [e["persona_id"] for e in events if e["type"] == "agent_error"] == ["product_manager"]
    assert values["summary"]["generated_by"] == "code"
    assert values["summary"]["headline"] == "1 useful"
    assert events[-1]["type"] == "done"
