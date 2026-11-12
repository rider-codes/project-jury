import asyncio
import json
from pathlib import Path

import pytest

from jury.agent import brief_message, final_verdict
from jury.models import Brief
from jury.personas import load_persona

BRIEF = Brief.model_validate(
    json.loads((Path(__file__).parent.parent / "examples" / "sample_brief.json").read_text(encoding="utf-8"))
)

GOOD = {
    "verdict": "not useful",
    "headline": "Crashes on bad input, tests are empty",
    "reasons": [
        {"text": "Tests are a placeholder.", "evidence": {"kind": "file", "ref": "tests/test_cli.py", "quote": "assert True"}},
        {"text": "Bad index crashes.", "evidence": {"kind": "demo", "ref": "step-3", "quote": "crashes with IndexError"}},
        {"text": "Has CI.", "evidence": {"kind": "file", "ref": ".github/workflows/ci.yml", "quote": "runs-on"}},
    ],
    "what_would_change_my_mind": ["Real tests"],
    "questions": [],
}


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def complete_json(self, tier, messages):
        self.calls.append((tier, messages))
        return self.replies.pop(0)


def test_verdict_drops_invented_claim():
    llm = FakeLLM([GOOD])
    out = asyncio.run(final_verdict(llm, load_persona("senior_engineer"), BRIEF))
    assert len(out.verdict.reasons) == 2
    assert out.rejected[0].problem.startswith("file not in brief")
    assert llm.calls[0][0].value == "mid"


def test_retries_once_on_bad_schema():
    llm = FakeLLM([{"verdict": "maybe"}, GOOD])
    out = asyncio.run(final_verdict(llm, load_persona("product_manager"), BRIEF))
    assert out.verdict.verdict.value == "not useful"
    assert len(llm.calls) == 2


def test_gives_up_after_max_attempts():
    llm = FakeLLM([{"verdict": "maybe"}, {"verdict": "maybe"}])
    with pytest.raises(ValueError):
        asyncio.run(final_verdict(llm, load_persona("general_user"), BRIEF))


def test_brief_is_wrapped_as_data():
    msg = brief_message(BRIEF)
    assert msg.startswith("<project_brief>") and msg.endswith("</project_brief>")
