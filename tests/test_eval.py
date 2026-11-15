import asyncio
import json

from jury.api.demo_llm import DemoLLM
from jury.eval.run import CASES, load_brief, load_cases, run_case
from jury.eval.score import Expect, Notice, score
from jury.personas import load_all
from jury.verifier import check_claim
from jury.models import Claim, Evidence


def claim(kind, ref, quote, text="a point"):
    return {"text": text, "evidence": {"kind": kind, "ref": ref, "quote": quote}}


def verdict(pid, value, reasons=(), rejected=0):
    return {"type": "verdict", "persona_id": pid, "verdict": value, "reasons": list(reasons),
            "rejected": [{"text": "x", "problem": "p"}] * rejected}


def by_name(checks):
    return {c.name: c.ok for c in checks}


def test_verdict_bounds():
    events = [verdict("a", "useful"), verdict("b", "not useful")]
    got = by_name(score(events, Expect(min_useful=1, max_useful=0, min_not_useful=2, max_not_useful=1), ["a", "b"]))
    assert got == {"every reviewer gave a verdict": True, "at least 1 useful": True, "at most 0 useful": False,
                   "at least 2 not useful": False, "at most 1 not useful": True}


def test_missing_verdict_fails_the_case():
    assert not score([verdict("a", "unsure")], Expect(), ["a", "b"])[0].ok


def test_must_notice_needs_a_verified_claim_of_the_right_kind():
    tree = Notice(name="tree", kind="tree", ref="absent", any=["test"])
    events = [{"type": "impression", "claims": [claim("file", "README.md", "100% test coverage")], "rejected": []}]
    assert not by_name(score(events, Expect(must_notice=[tree]), []))["tree"]  # a file quote is not tree evidence
    events.append({"type": "debate_turn", "claims": [claim("tree", "absent", "tests/")], "rejected": []})
    assert by_name(score(events, Expect(must_notice=[tree]), []))["tree"]


def test_dropped_share():
    events = [verdict("a", "unsure", [claim("file", "a", "bbbb")], rejected=3)]
    (check,) = [c for c in score(events, Expect(max_dropped_share=0.5), ["a"]) if "dropped" in c.name]
    assert not check.ok and "3 of 4" in check.detail


def test_every_case_loads_and_its_expectations_can_be_met():
    """The brief must hold the evidence a `must_notice` asks for, or no model could ever pass."""
    case_set = load_cases()
    assert {c.id for c in case_set.cases} >= {"good", "weak", "misleading"}
    assert all(p in load_all() for p in case_set.personas)
    for case in case_set.cases:
        brief = load_brief(case, CASES.parent)
        hay = json.dumps(brief.model_dump()).lower()
        for n in case.expect.must_notice:
            if n.kind == "tree" and n.ref == "absent":
                absent = [w for w in n.any if check_claim(
                    Claim(text="t", evidence=Evidence(kind="tree", ref="absent", quote=w)), brief).ok]
                assert absent, f"{case.id}: nothing in {n.any} is absent from the tree"
            else:
                assert any(w.lower() in hay for w in n.any), f"{case.id}: {n.name}"


def test_a_case_runs_end_to_end_with_the_demo_model():
    case_set = load_cases()
    case = next(c for c in case_set.cases if c.id == "good")
    result, events = asyncio.run(run_case(case, case_set.personas, load_all(), DemoLLM(delay=0)))
    assert result.error is None and set(result.verdicts) == set(case_set.personas)
    assert events[-1]["type"] == "done" and result.calls > 0
