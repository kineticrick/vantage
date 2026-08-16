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


def test_resume_repairs_a_dangling_tool_use_before_replay(tmp_path):
    """The stored transcript can end mid-turn (an abandoned stream persists
    it via web/app.py's finally). Resuming it must hand the API a valid
    prefix, or the very next send() gets rejected and that rejection is
    itself persisted, permanently bricking the conversation."""
    convs = []
    client = _client(tmp_path, convs=convs)
    _seed(tmp_path, "20260815T100000Z", "optical names",
          [{"role": "user", "content": "what about MU?"},
           {"role": "assistant", "content": [
               {"type": "tool_use", "id": "t1", "name": "get_ticker_metrics",
                "input": {"ticker": "MU"}}]}])

    assert client.post("/api/chats/20260815T100000Z/resume").status_code == 200
    client.post("/api/chat", json={"message": "follow-up"})

    for m in convs[-1].messages:
        content = m.get("content")
        blocks = content if isinstance(content, list) else []
        assert not any(b.get("type") == "tool_use" for b in blocks
                       if isinstance(b, dict))


def test_resume_repairs_a_trailing_bare_user_turn_before_replay(tmp_path):
    convs = []
    client = _client(tmp_path, convs=convs)
    _seed(tmp_path, "20260815T100000Z", "optical names",
          [{"role": "user", "content": "what about MU?"},
           {"role": "assistant", "content": [{"type": "text", "text": "MU is up."}]},
           {"role": "user", "content": "and NVDA?"}])

    assert client.post("/api/chats/20260815T100000Z/resume").status_code == 200
    client.post("/api/chat", json={"message": "follow-up"})

    # the dangling "and NVDA?" was dropped by resumable(); the conversation
    # handed to the factory starts with the balanced first turn, then the
    # NEW follow-up sent just now — never two consecutive user turns.
    roles = [m["role"] for m in convs[-1].messages]
    assert not any(a == "user" and b == "user"
                   for a, b in zip(roles, roles[1:]))


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


def test_get_chat_rejects_malformed_id_without_slash(tmp_path):
    # No "/" here, so the request reaches chat_one and chatstore.load itself
    # (unlike the %2F traversal case, which Starlette's router rejects before
    # the handler is ever called) — this is the defense chatstore.load's
    # ID_RE actually owns. A real file is seeded at this exact (malformed)
    # id's path so the 404 can only come from ID_RE rejecting the id before
    # the file-existence check runs — not from the file simply not existing.
    client = _client(tmp_path)
    _seed(tmp_path, "not-a-valid-id", "should never load",
          [{"role": "user", "content": "x"}])
    r = client.get("/api/chats/not-a-valid-id")
    assert r.status_code == 404
    assert r.json() == {"error": "not found"}


def test_resume_rejects_malformed_id_without_slash(tmp_path):
    client = _client(tmp_path)
    _seed(tmp_path, "not-a-valid-id", "should never load",
          [{"role": "user", "content": "x"}])
    r = client.post("/api/chats/not-a-valid-id/resume")
    assert r.status_code == 404
    assert r.json() == {"error": "not found"}


def test_get_chat_rejects_trailing_newline_id(tmp_path):
    # This is the exact case ID_RE's \Z anchor exists for: "$" would match
    # just before a trailing newline, but "\Z" only matches end-of-string.
    # The file is seeded under the literal (newline-suffixed) id so a regex
    # that let this through would actually find and return it.
    client = _client(tmp_path)
    _seed(tmp_path, "20260815T100000Z\n", "should never load",
          [{"role": "user", "content": "x"}])
    r = client.get("/api/chats/20260815T100000Z%0A")
    assert r.status_code == 404
    assert r.json() == {"error": "not found"}
