from jury.api.store import ReviewStore
from jury.llm import LLM
from jury.redact import HIDDEN, redact

KEY = "sk-or-v1-" + "0123456789abcdef" * 4  # made up, in the shape of a real key


def test_redact_hides_a_key_from_the_environment(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "plain-secret-value-123")
    assert redact("failed with plain-secret-value-123 in it") == f"failed with {HIDDEN} in it"


def test_redact_hides_key_shapes_not_in_the_environment(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    out = redact(f"Illegal header value b'Bearer {KEY}\n'")
    assert KEY not in out and HIDDEN in out
    assert "ghp_" + "a" * 36 not in redact("token ghp_" + "a" * 36)


def test_redact_leaves_ordinary_text_alone():
    text = "HTTP 429: temporarily rate-limited upstream. The bearer of bad news."
    assert redact(text) == text


def test_key_with_a_trailing_newline_is_stripped(monkeypatch):
    monkeypatch.setenv("JURY_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY + "\n")
    assert LLM.from_env().api_key == KEY


def test_event_log_never_stores_a_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    store = ReviewStore(tmp_path / "app.sqlite")
    store.create("r1", "demo", "https://github.com/a/b", ["senior_engineer"])
    store.add_event("r1", {"type": "error", "message": f"LocalProtocolError: Illegal header value b'Bearer {KEY}'"})
    (_, event), = store.events_after("r1")
    assert KEY not in event["message"] and HIDDEN in event["message"]
