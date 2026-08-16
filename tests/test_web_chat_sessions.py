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


def _seed(tmp_path, session_id, title, messages):
    s = chatstore.ChatSession(id=session_id, started_at="2026-08-15T10:00:00Z",
                              updated_at="2026-08-15T10:00:00Z", title=title,
                              title_turns=1, messages=messages)
    chatstore.save(tmp_path / "reports" / "chats", s, now="2026-08-15T10:00:00Z")
    return s


def _client(tmp_path, convs=None):
    def factory(s):
        c = _FakeConversation()
        if convs is not None:
            convs.append(c)
        return c
    return TestClient(create_app(settings=_settings(tmp_path),
                                 conversation_factory=factory))


def test_list_chats_returns_titles_newest_first(tmp_path):
    client = _client(tmp_path)
    _seed(tmp_path, "20260813T100000Z", "older chat",
          [{"role": "user", "content": "a"}])
    _seed(tmp_path, "20260815T100000Z", "newer chat",
          [{"role": "user", "content": "b"}])
    rows = client.get("/api/chats").json()
    assert [r["title"] for r in rows] == ["newer chat", "older chat"]
    assert rows[0]["turns"] == 1


def test_get_one_chat_returns_its_messages(tmp_path):
    client = _client(tmp_path)
    _seed(tmp_path, "20260815T100000Z", "optical names",
          [{"role": "user", "content": "are the optical names overextended?"}])
    body = client.get("/api/chats/20260815T100000Z").json()
    assert body["title"] == "optical names"
    assert body["turns"] == 1
    assert body["messages"][0]["content"] == "are the optical names overextended?"


def test_get_unknown_chat_is_404(tmp_path):
    assert _client(tmp_path).get("/api/chats/20260101T000000Z").status_code == 404


def test_get_chat_rejects_path_traversal(tmp_path):
    r = _client(tmp_path).get("/api/chats/..%2F..%2Fbrief-2026-08-15")
    assert r.status_code == 404


def test_resume_loads_history_into_the_active_conversation(tmp_path):
    convs = []
    client = _client(tmp_path, convs=convs)
    _seed(tmp_path, "20260815T100000Z", "optical names",
          [{"role": "user", "content": "earlier question"},
           {"role": "assistant", "content": [{"type": "text", "text": "earlier answer"}]}])

    assert client.post("/api/chats/20260815T100000Z/resume").status_code == 200
    client.post("/api/chat", json={"message": "follow-up"})

    # the live conversation carries the old history plus the new turn
    assert convs[-1].messages[0] == {"role": "user", "content": "earlier question"}
    assert convs[-1].messages[-2] == {"role": "user", "content": "follow-up"}

    # and the follow-up landed in the SAME stored session, not a new one
    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert len(rows) == 1
    assert rows[0]["id"] == "20260815T100000Z"
    assert rows[0]["turns"] == 2


def test_resume_unknown_id_is_404(tmp_path):
    assert _client(tmp_path).post(
        "/api/chats/20260101T000000Z/resume").status_code == 404


def test_resume_rebuilds_context_rather_than_reusing_a_stale_conversation(tmp_path):
    """A resumed chat must be built fresh, so its system prompt reflects
    today's brief, portfolio and evidence register."""
    convs = []
    client = _client(tmp_path, convs=convs)
    _seed(tmp_path, "20260815T100000Z", "x", [{"role": "user", "content": "a"}])
    client.post("/api/chat", json={"message": "live one"})
    before = len(convs)
    client.post("/api/chats/20260815T100000Z/resume")
    assert len(convs) == before + 1
