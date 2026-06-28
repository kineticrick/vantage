from pathlib import Path
from fastapi.testclient import TestClient
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
    def send(self, message):
        yield {"type": "text", "text": f"echo: {message}"}
        yield {"type": "done"}

def test_chat_streams_sse(tmp_path):
    created = []
    def factory(s):
        c = _FakeConversation(); created.append(c); return c
    app = create_app(settings=_settings(tmp_path), conversation_factory=factory)
    client = TestClient(app)
    r = client.post("/api/chat", json={"message": "what's MU?"})
    assert r.status_code == 200
    assert 'data: {"type": "text", "text": "echo: what\'s MU?"}' in r.text
    assert 'data: {"type": "done"}' in r.text
    # second message reuses the same conversation
    client.post("/api/chat", json={"message": "again"})
    assert len(created) == 1

def test_chat_new_resets(tmp_path):
    created = []
    def factory(s):
        c = _FakeConversation(); created.append(c); return c
    client = TestClient(create_app(settings=_settings(tmp_path),
                                   conversation_factory=factory))
    client.post("/api/chat", json={"message": "one"})
    assert client.post("/api/chat/new").json() == {"ok": True}
    client.post("/api/chat", json={"message": "two"})
    assert len(created) == 2  # new conversation built after reset
