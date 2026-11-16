import json
import time

import pytest
from fastapi.testclient import TestClient

from jury.api.app import create_app
from jury.api.demo_llm import DemoLLM
from jury.ingest.github import IngestError
from jury.models import Brief


@pytest.fixture
def client(tmp_path):
    def fake_builder(url, demo, token):
        if "broken" in url:
            raise IngestError("not found (private repos are not supported in v1)")
        return Brief(project_name="widget", repo_url="https://github.com/o/widget", summary="A widget.",
                     files={"README.md": "# widget\n\nA widget that does things well.\n"}, tree=["README.md"])

    app = create_app(str(tmp_path / "j.sqlite"), lambda: DemoLLM(delay=0), brief_builder=fake_builder)
    with TestClient(app) as c:
        yield c


def wait_for(client, review_id, statuses, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/api/reviews/{review_id}").json()
        if r["status"] in statuses and not r["running"]:
            return r["status"]
        time.sleep(0.05)
    raise AssertionError(f"review stuck in {r['status']}")


def sse(client, review_id, last_id=None):
    headers = {"Last-Event-ID": str(last_id)} if last_id else {}
    events, ids = [], []
    with client.stream("GET", f"/api/reviews/{review_id}/events", headers=headers) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        for block in resp.read().decode().split("\n\n"):
            lines = dict(l.split(": ", 1) for l in block.splitlines() if ": " in l and not l.startswith(":"))
            if "data" in lines and lines.get("event") != "end":
                events.append(json.loads(lines["data"]))
                ids.append(int(lines["id"]))
    return events, ids


def run_to_done(client, review_id):
    while wait_for(client, review_id, {"paused", "done", "error"}) == "paused":
        qs = [e for e in client_events(client, review_id) if e["type"] == "needs_answers"][-1]["questions"]
        assert client.post(f"/api/reviews/{review_id}/answers", json={"answers": {q["id"]: "" for q in qs}}).status_code == 202
    return client.get(f"/api/reviews/{review_id}").json()["status"]


def client_events(client, review_id):
    store = client.app.state.runner.store
    return [e for _, e in store.events_after(review_id)]


def test_access_code_gates_the_api(tmp_path, monkeypatch):
    monkeypatch.setenv("JURY_ACCESS_CODE", "s3cret")
    app = create_app(str(tmp_path / "j.sqlite"), lambda: DemoLLM(delay=0))
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/session").json() == {"needs_code": True, "ok": False}
        assert c.get("/api/personas").status_code == 401
        assert c.post("/api/reviews", json={"sample": True}).status_code == 401
        assert c.get("/api/reviews/x/events").status_code == 401
        assert c.post("/api/login", json={"code": "wrong"}).status_code == 401
        r = c.post("/api/login", json={"code": "s3cret"})
        assert r.status_code == 200 and "httponly" in r.headers["set-cookie"].lower()
        assert c.get("/api/session").json() == {"needs_code": True, "ok": True}
        assert c.get("/api/personas").status_code == 200


def test_no_access_code_means_open(client):
    assert client.get("/api/session").json() == {"needs_code": False, "ok": True}


def test_quota_endpoint_with_demo_model(client):
    assert client.get("/api/quota").json() == {"demo_model": True, "free_quota": None, "site_calls": 4}


def test_personas(client):
    ps = client.get("/api/personas").json()
    assert len(ps) == 6 and sum(p["default"] for p in ps) == 4
    assert {"id", "name", "tagline", "tier", "verdict_question"} <= set(ps[0])


@pytest.mark.parametrize("body", [
    {"persona_ids": ["senior_engineer"]},  # no repo and not sample
    {"sample": True, "persona_ids": []},
    {"sample": True, "persona_ids": ["security_reviewer"]},
    {"repo_url": "https://gitlab.com/a/b"},
])
def test_new_review_validation(client, body):
    assert client.post("/api/reviews", json=body).status_code == 422


def test_sample_review_end_to_end_over_sse(client):
    rid = client.post("/api/reviews", json={"sample": True, "persona_ids": ["senior_engineer", "ux_designer", "general_user"]}).json()["id"]
    assert run_to_done(client, rid) == "done"

    events, ids = sse(client, rid)
    types = [e["type"] for e in events]
    assert types[0] == "brief" and events[0]["project_name"] == "tasklite"
    for t in ("impression", "router", "debate_turn", "verdict", "summary", "done", "usage"):
        assert t in types, t
    assert ids == sorted(ids) and len(set(ids)) == len(ids)

    # reconnecting with Last-Event-ID replays only what came after
    later, later_ids = sse(client, rid, last_id=ids[-3])
    assert later_ids == ids[-2:]

    listed = client.get("/api/reviews").json()
    assert listed[0]["id"] == rid and listed[0]["status"] == "done"


def test_answers_only_when_paused(client):
    rid = client.post("/api/reviews", json={"sample": True, "persona_ids": ["senior_engineer"]}).json()["id"]
    status = wait_for(client, rid, {"paused", "done"})
    if status == "done":
        assert client.post(f"/api/reviews/{rid}/answers", json={"answers": {}}).status_code == 409
    assert client.post("/api/reviews/nope/answers", json={"answers": {}}).status_code == 404


def test_repo_review_and_ingest_failure(client):
    rid = client.post("/api/reviews", json={"repo_url": "https://github.com/o/widget", "demo": "1. open it"}).json()["id"]
    assert client.get(f"/api/reviews/{rid}").json()["project_name"] == "widget"
    assert run_to_done(client, rid) == "done"
    assert client_events(client, rid)[0] == {"type": "status", "stage": "ingesting", "repo_url": "https://github.com/o/widget"}

    bad = client.post("/api/reviews", json={"repo_url": "https://github.com/o/broken"}).json()["id"]
    assert wait_for(client, bad, {"error"}) == "error"
    events, _ = sse(client, bad)  # stream closes on error
    assert events[-1]["type"] == "error" and "private repos" in events[-1]["message"]


def test_review_with_live_site(tmp_path):
    from jury.ingest.site import SiteCapture, Shot
    from jury.ingest.site_log import add_site
    from jury.models import SiteView

    seen = []

    def capture(url, max_pages):
        seen.append(url)
        return SiteCapture(url=url, shots=[Shot(view=SiteView(ref="page-1-desktop", url=url, width="desktop",
                                                              text="Welcome to widget"), image=b"jpg")])

    async def adder(llm, brief, site_url):
        return await add_site(llm, brief, site_url, capture=capture)

    def builder(url, demo, token):
        return Brief(project_name="widget", repo_url="https://github.com/o/widget", summary="A widget.",
                     files={"README.md": "# widget\n\nA widget that does things well.\n"}, tree=["README.md"])

    app = create_app(str(tmp_path / "j.sqlite"), lambda: DemoLLM(delay=0), brief_builder=builder, site_adder=adder)
    with TestClient(app) as c:
        assert c.post("/api/reviews", json={"repo_url": "https://github.com/o/widget", "site_url": "https://"}).status_code == 422
        rid = c.post("/api/reviews", json={"repo_url": "https://github.com/o/widget",
                                           "site_url": "widget.example.com"}).json()["id"]
        assert run_to_done(c, rid) == "done"
        events = client_events(c, rid)
        assert seen == ["https://widget.example.com/"]
        assert {"type": "status", "stage": "site", "site_url": "https://widget.example.com/"} in events
        brief = next(e for e in events if e["type"] == "brief")
        assert brief["site_views"] == 1 and brief["site_logs"] == 1
        first_usage = next(e for e in events if e["type"] == "usage")  # at the pause after round 1
        assert first_usage["calls"] == 1 + 4  # the vision call is on the review's budget


def test_chat_clean_and_with_room_history(client):
    rid = client.post("/api/reviews", json={"sample": True, "persona_ids": ["senior_engineer", "product_manager"]}).json()["id"]
    run_to_done(client, rid)

    clean = client.post("/api/chats", json={"persona_id": "senior_engineer", "review_id": rid}).json()
    assert clean["with_history"] is False and clean["project_name"] == "tasklite"
    linked = client.post("/api/chats", json={"persona_id": "senior_engineer", "review_id": rid, "with_history": True}).json()
    assert linked["with_history"] is True and linked["room_thread"] == rid

    reply = client.post(f"/api/chats/{linked['id']}/messages", json={"text": "What would you fix first?"}).json()
    assert reply["role"] == "agent" and reply["claims"]
    assert len(client.get(f"/api/chats/{linked['id']}").json()["messages"]) == 2

    sample = client.post("/api/chats", json={"persona_id": "ux_designer", "sample": True})
    assert sample.status_code == 201
    assert client.post("/api/chats", json={"persona_id": "nobody", "sample": True}).status_code == 422
    assert client.post("/api/chats/nope/messages", json={"text": "hi"}).status_code == 404
    assert client.post(f"/api/chats/{clean['id']}/messages", json={"text": ""}).status_code == 422


def test_retry_runs_again_only_what_failed(tmp_path):
    down = {"verdicts": True}

    class Flaky(DemoLLM):
        async def complete_json(self, tier, messages, vision=False):
            if down["verdicts"] and "Give your final verdict" in messages[-1]["content"]:
                raise RuntimeError("model down")
            return await super().complete_json(tier, messages, vision)

    app = create_app(str(tmp_path / "j.sqlite"), lambda: Flaky(delay=0))
    with TestClient(app) as c:
        ids = ["senior_engineer", "ux_designer"]
        rid = c.post("/api/reviews", json={"sample": True, "persona_ids": ids}).json()["id"]
        assert run_to_done(c, rid) == "done"
        before = client_events(c, rid)
        assert not [e for e in before if e["type"] == "verdict"]
        assert len([e for e in before if e["type"] == "agent_error" and e.get("phase") == "verdict"]) == 2

        down["verdicts"] = False
        r = c.post(f"/api/reviews/{rid}/retry")
        assert r.status_code == 202 and r.json()["verdicts"] == ids and r.json()["impressions"] == []
        assert wait_for(c, rid, {"done", "error"}) == "done"
        after = client_events(c, rid)[len(before):]
        types = [e["type"] for e in after]
        assert types[0] == "resumed" and types.count("verdict") == 2
        assert "impression" not in types and "debate_turn" not in types  # nothing that worked is redone
        summary = [e for e in after if e["type"] == "summary"][-1]
        assert sum(summary["tally"].values()) == 2

        # the stream of a retried review replays everything and still ends
        events, _ = sse(c, rid)
        assert [e["type"] for e in events].count("done") == 2

        assert c.post(f"/api/reviews/{rid}/retry").status_code == 409  # nothing left to fix
        assert c.post("/api/reviews/nope/retry").status_code == 404


def test_retry_brings_back_a_reviewer_who_missed_round_one(tmp_path):
    down = {"on": True}

    class Flaky(DemoLLM):
        async def complete_json(self, tier, messages, vision=False):
            if down["on"] and "designer" in messages[0]["content"].lower()[:400] and "first impression" in messages[-1]["content"]:
                raise RuntimeError("model down")
            return await super().complete_json(tier, messages, vision)

    app = create_app(str(tmp_path / "j.sqlite"), lambda: Flaky(delay=0))
    with TestClient(app) as c:
        rid = c.post("/api/reviews", json={"sample": True, "persona_ids": ["senior_engineer", "ux_designer"]}).json()["id"]
        assert run_to_done(c, rid) == "done"
        before = client_events(c, rid)
        if not any(e["type"] == "agent_error" and e["persona_id"] == "ux_designer" for e in before):
            raise AssertionError("the test double no longer fails the designer in round 1")
        down["on"] = False
        assert c.post(f"/api/reviews/{rid}/retry").json()["impressions"] == ["ux_designer"]
        assert wait_for(c, rid, {"done", "error"}) == "done"
        after = client_events(c, rid)[len(before):]
        assert [e["persona_id"] for e in after if e["type"] == "impression"] == ["ux_designer"]
        assert [e["persona_id"] for e in after if e["type"] == "verdict"] == ["ux_designer"]


def test_retry_refused_when_the_project_was_never_read(client):
    rid = client.post("/api/reviews", json={"repo_url": "https://github.com/o/broken"}).json()["id"]
    assert wait_for(client, rid, {"error"}) == "error"
    assert client.post(f"/api/reviews/{rid}/retry").status_code == 409


def test_builder_can_talk_to_the_room_mid_debate(tmp_path):
    app = create_app(str(tmp_path / "j.sqlite"), lambda: DemoLLM(delay=0.05))
    with TestClient(app) as c:
        ids = ["senior_engineer", "ux_designer"]
        rid = c.post("/api/reviews", json={"sample": True, "persona_ids": ids}).json()["id"]
        assert c.post(f"/api/reviews/{rid}/messages", json={"to": "hiring_manager", "text": "hi"}).status_code == 422
        # wait until the project is read, then speak
        end = time.time() + 10
        while "brief" not in [e["type"] for e in client_events(c, rid)] and time.time() < end:
            time.sleep(0.02)
        r = c.post(f"/api/reviews/{rid}/messages", json={"to": "everyone", "text": "It is deployed at example.com."})
        assert r.status_code == 202
        assert run_to_done(c, rid) == "done"
        events = client_events(c, rid)
        said = [e for e in events if e["type"] == "user_message"]
        assert said == [{"type": "user_message", "to": "everyone", "text": "It is deployed at example.com."}]
        answered = [e for e in events if e["type"] == "debate_turn" and e.get("addressed_by_user")]
        assert len(answered) == 1 and answered[0]["user_text"] == "It is deployed at example.com."
        assert not [e for e in events if e["type"] == "user_message_missed"]
        # once the review is over the room is closed
        assert c.post(f"/api/reviews/{rid}/messages", json={"text": "late"}).status_code == 409


def test_chat_about_a_repo_without_a_review(client):
    """One-on-one takes a GitHub link directly; it must not fall back to the sample project."""
    chat = client.post("/api/chats", json={"persona_id": "hiring_manager", "repo_url": "https://github.com/o/widget"})
    assert chat.status_code == 201 and chat.json()["project_name"] == "widget"

    broken = client.post("/api/chats", json={"persona_id": "hiring_manager", "repo_url": "https://github.com/o/broken"})
    assert broken.status_code == 422 and "private repos" in broken.json()["detail"]

    assert client.post("/api/chats", json={"persona_id": "hiring_manager"}).status_code == 422
