import json
from pathlib import Path
from fastapi.testclient import TestClient
from vantage import chatstore
from vantage.settings import Settings
from vantage.web.app import create_app


def _settings(tmp_path):
    for sub in ("reports", "data", "config", "cache"):
        (tmp_path / sub).mkdir(exist_ok=True)
    return Settings(anthropic_api_key="k", gmail_user="", gmail_app_password="",
                    email_recipient="", model="m", portfolio_analysis_path="/x",
                    project_root=tmp_path, config_dir=tmp_path / "config",
                    data_dir=tmp_path / "data", reports_dir=tmp_path / "reports",
                    cache_dir=tmp_path / "cache")


class _FakeConversation:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append({"role": "user", "content": message})
        yield {"type": "text", "text": f"echo: {message}"}
        self.messages.append({"role": "assistant",
                              "content": [{"type": "text", "text": f"echo: {message}"}]})
        yield {"type": "done"}


class _AbandonedConversation(_FakeConversation):
    """Yields text, then more than the client will read."""
    def send(self, message):
        self.messages.append({"role": "user", "content": message})
        yield {"type": "text", "text": "partial"}
        self.messages.append({"role": "assistant",
                              "content": [{"type": "text", "text": "partial"}]})
        for i in range(1000):
            yield {"type": "text", "text": f"chunk{i}"}
        yield {"type": "done"}


def _app(tmp_path, conv=None, **kw):
    c = conv or _FakeConversation()
    return create_app(settings=_settings(tmp_path),
                      conversation_factory=lambda s: c, **kw), c


def test_a_turn_is_persisted(tmp_path):
    app, _ = _app(tmp_path)
    client = TestClient(app)
    client.post("/api/chat", json={"message": "what about MU?"})

    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert len(rows) == 1
    assert rows[0]["turns"] == 1
    sess = chatstore.load(tmp_path / "reports" / "chats", rows[0]["id"])
    assert sess.messages[0] == {"role": "user", "content": "what about MU?"}


def test_second_turn_appends_to_the_same_session(tmp_path):
    app, _ = _app(tmp_path)
    client = TestClient(app)
    client.post("/api/chat", json={"message": "one"})
    client.post("/api/chat", json={"message": "two"})

    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert len(rows) == 1
    assert rows[0]["turns"] == 2


def test_chat_new_starts_a_separate_session(tmp_path):
    settings = _settings(tmp_path)
    convs = []

    def factory(s):
        c = _FakeConversation()
        convs.append(c)
        return c

    client = TestClient(create_app(settings=settings, conversation_factory=factory))
    client.post("/api/chat", json={"message": "one"})
    client.post("/api/chat/new")
    client.post("/api/chat", json={"message": "two"})

    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert len(rows) == 2
    assert len(convs) == 2


def test_markdown_transcript_is_written(tmp_path):
    app, _ = _app(tmp_path)
    TestClient(app).post("/api/chat", json={"message": "what about MU?"})
    mds = list((tmp_path / "reports" / "chats").glob("chat-*.md"))
    assert len(mds) == 1
    assert "what about MU?" in mds[0].read_text(encoding="utf-8")


def test_save_failure_surfaces_an_error_event_but_still_streams(tmp_path,
                                                               monkeypatch):
    app, _ = _app(tmp_path)

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr("vantage.web.app.chatstore.save", boom)

    r = TestClient(app).post("/api/chat", json={"message": "hello"})
    assert r.status_code == 200
    assert "echo: hello" in r.text          # the answer still reached the client
    assert "not saved" in r.text            # and the failure was reported


def test_titling_failure_never_breaks_a_turn(tmp_path, monkeypatch):
    app, _ = _app(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("titling exploded")
    monkeypatch.setattr("vantage.web.app.chattitle.maybe_retitle", boom)

    r = TestClient(app).post("/api/chat", json={"message": "hello"})
    assert r.status_code == 200
    assert "echo: hello" in r.text
    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert rows[0]["turns"] == 1            # the turn was still saved


def test_abandoning_the_stream_still_persists_the_turn(tmp_path):
    """Closing the tab mid-answer must not lose the exchange."""
    app, conv = _app(tmp_path, conv=_AbandonedConversation())
    client = TestClient(app)
    with client.stream("POST", "/api/chat", json={"message": "hello"}) as r:
        for _ in r.iter_lines():
            break                            # read one line, then walk away

    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert len(rows) == 1
    sess = chatstore.load(tmp_path / "reports" / "chats", rows[0]["id"])
    assert sess.messages[0] == {"role": "user", "content": "hello"}
