import asyncio
import json

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


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.headers = status, body, {}
        self.text = json.dumps(body)

    def json(self):
        return self._body


def _llm_with(responses_by_model, models="a:free,b:free"):
    """An LLM whose HTTP client answers from a script, per model."""
    import jury.llm as llm_mod

    calls = []

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, url, json, headers):
            calls.append(json["model"])
            return responses_by_model[json["model"]].pop(0)

    llm = LLM(provider="openrouter", api_key="k", models={Tier.cheap: models, Tier.mid: "", Tier.strong: ""})
    llm.max_retries = 2
    return llm, calls, FakeClient, llm_mod


OK = _Resp(200, {"choices": [{"message": {"content": '{"ok": true}'}}], "usage": {"total_tokens": 10}})
UPSTREAM = _Resp(429, {"error": {"message": "Provider returned error",
                                 "metadata": {"raw": "a:free is temporarily rate-limited upstream."}}})
DAILY = _Resp(429, {"error": {"message": "Rate limit exceeded: free-models-per-day"}})


def test_falls_back_to_next_model_when_upstream_limited(monkeypatch):
    llm, calls, FakeClient, mod = _llm_with({"a:free": [UPSTREAM], "b:free": [OK]})
    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)
    assert asyncio.run(llm.complete_json(Tier.cheap, [{"role": "user", "content": "x"}])) == {"ok": True}
    assert calls == ["a:free", "b:free"]  # no slow retries on the overloaded model
    assert llm.last_model == "b:free" and llm.budget.calls == 1


def test_daily_quota_does_not_fall_back(monkeypatch):
    llm, calls, FakeClient, mod = _llm_with({"a:free": [DAILY], "b:free": [OK]})
    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)
    with pytest.raises(LLMError, match="quota"):
        asyncio.run(llm.complete_json(Tier.cheap, [{"role": "user", "content": "x"}]))
    assert calls == ["a:free"]


def test_last_model_failing_raises(monkeypatch):
    llm, calls, FakeClient, mod = _llm_with({"a:free": [UPSTREAM], "b:free": [UPSTREAM, UPSTREAM, UPSTREAM]})
    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)
    real_sleep = asyncio.sleep
    monkeypatch.setattr(mod.asyncio, "sleep", lambda *_: real_sleep(0))
    with pytest.raises(LLMError, match="gave up on b:free"):
        asyncio.run(llm.complete_json(Tier.cheap, [{"role": "user", "content": "x"}]))


def test_missing_key_raises(monkeypatch):
    monkeypatch.setenv("JURY_PROVIDER", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMError):
        LLM.from_env()
