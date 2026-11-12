import pytest

from jury.llm import LLM, Budget, BudgetExceeded, LLMError, parse_json_reply
from jury.models import Tier


def test_budget_call_cap():
    b = Budget(max_calls=2)
    b.reserve()
    b.reserve()
    with pytest.raises(BudgetExceeded):
        b.reserve()


def test_budget_token_cap():
    b = Budget(max_tokens=100)
    b.reserve()
    b.record(150)
    with pytest.raises(BudgetExceeded):
        b.reserve()


def test_parse_plain_json():
    assert parse_json_reply('{"a": 1}') == {"a": 1}


def test_parse_fenced_json():
    assert parse_json_reply('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_with_preamble():
    assert parse_json_reply('Here you go: {"a": 1} hope it helps') == {"a": 1}


def test_parse_non_json_raises():
    with pytest.raises(LLMError):
        parse_json_reply("no json here")


def test_tier_falls_back_to_cheap():
    llm = LLM(provider="openrouter", api_key="k", models={Tier.cheap: "c", Tier.mid: "", Tier.strong: ""})
    assert llm.model_for(Tier.mid) == "c"


def test_missing_key_raises(monkeypatch):
    monkeypatch.setenv("JURY_PROVIDER", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMError):
        LLM.from_env()
