"""Bring your own key: a visitor's key is used for their run only, and never stored."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jury.api.app import POOL_EMPTY, create_app
from jury.api.demo_llm import DemoLLM
from jury.llm import LLM, LLMError, clean_key
from jury.redact import HIDDEN, forget, redact, watch

# not in the shape of any provider's key, so only the "watched key" rule can hide it
KEY = "visitor-secret-0123456789abcdef"
KEYH = {"X-Jury-Key": KEY}


class Recorder:
    """Stands in for the two factories and remembers what was built and with which key."""

    def __init__(self, quota_left: int | None = None, fail_with_key: bool = False):
        self.server_made = 0
        self.keys: list[str] = []
        self.llms: list[DemoLLM] = []
        self.quota_left = quota_left
        self.fail_with_key = fail_with_key

    def server(self) -> DemoLLM:
        self.server_made += 1
        return DemoLLM(delay=0, quota_left=self.quota_left)

    def byok(self, key: str) -> DemoLLM:
        self.keys.append(key)
        llm = DemoLLM(delay=0, own_key=key, quota_left=-1)
        if self.fail_with_key:
            async def boom(*a, **k):
                raise RuntimeError(f"Illegal header value b'Bearer {llm.api_key}'")
            llm.complete_json = boom
        self.llms.append(llm)
        return llm


def make_client(tmp_path, rec: Recorder, with_byok: bool = True):
    app = create_app(str(tmp_path / "j.sqlite"), rec.server, byok_factory=rec.byok if with_byok else None)
    return TestClient(app)


def wait_done(client, review_id, headers=None, timeout=30):
    """Wait for the review to end, answering any questions it pauses on (with the same headers)."""
    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/api/reviews/{review_id}").json()
        if not r["running"] and r["status"] in {"done", "error"}:
            return r["status"]
        if not r["running"] and r["status"] == "paused":
            events = [e for _, e in client.app.state.runner.store.events_after(review_id)]
            qs = [e for e in events if e["type"] == "needs_answers"][-1]["questions"]
            resp = client.post(f"/api/reviews/{review_id}/answers", json={"answers": {q["id"]: "" for q in qs}},
                               headers=headers or {})
            assert resp.status_code == 202
        time.sleep(0.05)
    raise AssertionError("review did not finish")


def everything_on_disk(tmp_path: Path) -> bytes:
    return b"".join(p.read_bytes() for p in tmp_path.glob("j*.sqlite*"))


def test_a_review_with_a_key_uses_that_key(tmp_path):
    rec = Recorder()
    with make_client(tmp_path, rec) as c:
        r = c.post("/api/reviews", json={"sample": True, "persona_ids": ["senior_engineer"]}, headers={"X-Jury-Key": KEY})
        assert r.status_code == 201
        wait_done(c, r.json()["id"], KEYH)
    assert rec.keys == [KEY]
    assert rec.server_made == 0  # the shared key was never touched


def test_a_review_without_a_key_uses_the_server_key(tmp_path):
    rec = Recorder()
    with make_client(tmp_path, rec) as c:
        r = c.post("/api/reviews", json={"sample": True, "persona_ids": ["senior_engineer"]})
        wait_done(c, r.json()["id"])
    assert rec.keys == [] and rec.server_made >= 1


def test_the_key_is_dropped_when_the_run_ends(tmp_path):
    rec = Recorder()
    with make_client(tmp_path, rec) as c:
        r = c.post("/api/reviews", json={"sample": True, "persona_ids": ["senior_engineer"]}, headers={"X-Jury-Key": KEY})
        wait_done(c, r.json()["id"], KEYH)
    assert [llm.api_key for llm in rec.llms] == [""]
    assert redact(f"oops {KEY}") == f"oops {KEY}"  # no longer watched: the runner forgot it


def test_the_key_is_never_written_to_disk(tmp_path):
    rec = Recorder()
    with make_client(tmp_path, rec) as c:
        r = c.post("/api/reviews", json={"sample": True, "persona_ids": ["senior_engineer", "product_manager"]},
                   headers={"X-Jury-Key": KEY})
        wait_done(c, r.json()["id"], KEYH)
    assert KEY.encode() not in everything_on_disk(tmp_path)


def test_a_key_in_an_error_is_hidden_everywhere(tmp_path):
    rec = Recorder(fail_with_key=True)
    with make_client(tmp_path, rec) as c:
        r = c.post("/api/reviews", json={"sample": True, "persona_ids": ["senior_engineer"]}, headers={"X-Jury-Key": KEY})
        wait_done(c, r.json()["id"], KEYH)
        events = c.app.state.runner.store.events_after(r.json()["id"])
    assert any(HIDDEN in str(e) for _, e in events)  # the failure was recorded, with the key hidden
    assert KEY.encode() not in everything_on_disk(tmp_path)


def test_a_one_on_one_with_a_key_uses_it_and_drops_it(tmp_path):
    rec = Recorder()
    with make_client(tmp_path, rec) as c:
        chat = c.post("/api/chats", json={"persona_id": "senior_engineer", "sample": True}).json()
        r = c.post(f"/api/chats/{chat['id']}/messages", json={"text": "what is it?"}, headers={"X-Jury-Key": KEY})
        assert r.status_code == 200
        c.post(f"/api/chats/{chat['id']}/messages", json={"text": "and again?"}, headers={"X-Jury-Key": KEY})
    assert rec.keys == [KEY]  # one wrapper per chat, so one budget across its messages
    assert rec.llms[0].api_key == ""
    assert KEY.encode() not in everything_on_disk(tmp_path)


def test_a_badly_shaped_key_is_refused(tmp_path):
    rec = Recorder()
    with make_client(tmp_path, rec) as c:
        for bad in ["short", "has a space in it 1234567890", "tab\tseparated-key-1234567890"]:
            r = c.post("/api/reviews", json={"sample": True, "persona_ids": ["senior_engineer"]}, headers={"X-Jury-Key": bad})
            assert r.status_code == 422, bad
    assert rec.keys == []


def test_without_byok_support_the_header_is_ignored(tmp_path):
    rec = Recorder()
    with make_client(tmp_path, rec, with_byok=False) as c:
        r = c.post("/api/reviews", json={"sample": True, "persona_ids": ["senior_engineer"]}, headers={"X-Jury-Key": KEY})
        wait_done(c, r.json()["id"], KEYH)
        assert c.get("/api/quota").json()["byok"] is False
    assert rec.keys == []


def test_a_real_review_is_refused_when_the_free_quota_is_gone(tmp_path):
    rec = Recorder(quota_left=0)
    with make_client(tmp_path, rec) as c:
        body = {"repo_url": "https://github.com/o/widget", "persona_ids": ["senior_engineer", "product_manager"]}
        r = c.post("/api/reviews", json=body)
        assert r.status_code == 429 and r.json()["detail"] == POOL_EMPTY
        # one reviewer is a one-on-one, which is refused the same way
        r = c.post("/api/chats", json={"persona_id": "senior_engineer", "repo_url": "https://github.com/o/widget"})
        assert r.status_code == 429
        # the sample project is free of any model quota check, as before
        assert c.post("/api/reviews", json={"sample": True, "persona_ids": ["senior_engineer"]}).status_code == 201


def test_the_quota_endpoint_says_when_to_ask_for_a_key(tmp_path):
    rec = Recorder(quota_left=0)
    with make_client(tmp_path, rec) as c:
        q = c.get("/api/quota").json()
        assert q["exhausted"] is True and q["byok"] is True and q["own_key"] is False
        q = c.get("/api/quota", headers={"X-Jury-Key": KEY}).json()
        assert q["exhausted"] is False and q["own_key"] is True


def test_the_quota_endpoint_does_not_ask_while_there_is_quota(tmp_path):
    rec = Recorder(quota_left=30)
    with make_client(tmp_path, rec) as c:
        assert c.get("/api/quota").json()["exhausted"] is False


def test_clean_key_trims_and_checks_the_shape():
    assert clean_key(f"  {KEY}\n") == KEY
    for bad in ["", "short", "a b " * 8, "café-" * 4, "x" * 400]:
        with pytest.raises(LLMError):
            clean_key(bad)


def test_llm_for_key_prefers_byok_models(monkeypatch):
    monkeypatch.setenv("JURY_MODEL_CHEAP", "free-model:free")
    monkeypatch.setenv("JURY_MODEL_MID", "free-mid:free")
    monkeypatch.setenv("JURY_BYOK_MODEL_CHEAP", "paid-model")
    llm = LLM.for_key(KEY)
    assert llm.byok and llm.api_key == KEY
    from jury.models import Tier
    assert llm.model_for(Tier.cheap) == "paid-model"  # set for visitors
    assert llm.model_for(Tier.mid) == "free-mid:free"  # not set for visitors: the usual one


def test_watched_keys_are_hidden_until_forgotten():
    watch(KEY)
    watch(KEY)  # two runs on the same key
    assert redact(f"x {KEY} y") == f"x {HIDDEN} y"
    forget(KEY)
    assert HIDDEN in redact(f"x {KEY} y")  # still in use by the other run
    forget(KEY)
    assert redact(f"x {KEY} y") == f"x {KEY} y"
