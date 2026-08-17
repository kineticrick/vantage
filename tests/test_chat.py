# tests/test_chat.py
from pathlib import Path
import chat
from vantage.settings import Settings
from vantage import chatstore
import chat as chat_module

def _settings(tmp_path):
    (tmp_path / "reports").mkdir(exist_ok=True)
    return Settings(anthropic_api_key="k", gmail_user="", gmail_app_password="",
                    email_recipient="", model="claude-opus-4-8",
                    portfolio_analysis_path="/x", project_root=tmp_path,
                    config_dir=tmp_path, data_dir=tmp_path,
                    reports_dir=tmp_path / "reports", cache_dir=tmp_path)

class _FakeConversation:
    def __init__(self):
        self.sent = []
        self.messages = []
    def send(self, msg):
        self.sent.append(msg)
        self.messages.append({"role": "user", "content": msg})
        yield {"type": "text", "text": f"echo: {msg}"}
        self.messages.append({"role": "assistant",
                              "content": [{"type": "text",
                                           "text": f"echo: {msg}"}]})
        yield {"type": "done"}

def test_main_loops_streams_and_writes_transcript(tmp_path, monkeypatch, capsys):
    s = _settings(tmp_path)
    conv = _FakeConversation()
    monkeypatch.setattr("vantage.chattitle.maybe_retitle", lambda *a, **k: False)
    # feed two questions then EOF (StopIteration -> exit)
    lines = iter(["what's MU?", "and NVDA?"])
    chat.main(settings=s, _conversation=conv, _input=lambda _prompt: next(lines))
    assert conv.sent == ["what's MU?", "and NVDA?"]
    out = capsys.readouterr().out
    assert "echo: what's MU?" in out and "echo: and NVDA?" in out
    rows = chatstore.list_sessions(s.reports_dir / "chats")
    assert len(rows) == 1
    assert rows[0]["turns"] == 2

def test_main_exits_on_quit_command(tmp_path):
    s = _settings(tmp_path)
    conv = _FakeConversation()
    lines = iter(["quit", "should-not-be-sent"])
    chat.main(settings=s, _conversation=conv, _input=lambda _prompt: next(lines))
    assert conv.sent == []  # quit before sending anything
    assert not (tmp_path / "reports" / "chats").exists()  # no transcript on empty session


class _RecordingConversation:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append({"role": "user", "content": message})
        yield {"type": "text", "text": f"reply to {message}"}
        self.messages.append({"role": "assistant",
                              "content": [{"type": "text",
                                           "text": f"reply to {message}"}]})
        yield {"type": "done"}


def test_repl_saves_each_turn_through_chatstore(tmp_path, monkeypatch, capsys):
    settings = _settings(tmp_path)   # reuse this module's existing helper
    monkeypatch.setattr("vantage.chattitle.maybe_retitle", lambda *a, **k: False)
    lines = iter(["what about MU?", "and WDC?", "exit"])
    chat_module.main(settings=settings, _conversation=_RecordingConversation(),
                     _input=lambda prompt: next(lines))

    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert len(rows) == 1
    assert rows[0]["turns"] == 2


def test_repl_turn_survives_an_interrupted_session(tmp_path, monkeypatch):
    """A turn is on disk before the next prompt, so Ctrl-C keeps what was said."""
    settings = _settings(tmp_path)
    monkeypatch.setattr("vantage.chattitle.maybe_retitle", lambda *a, **k: False)

    def _input(prompt):
        if not getattr(_input, "called", False):
            _input.called = True
            return "what about MU?"
        raise KeyboardInterrupt

    try:
        chat_module.main(settings=settings,
                         _conversation=_RecordingConversation(), _input=_input)
    except KeyboardInterrupt:
        pass

    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert len(rows) == 1
    assert rows[0]["turns"] == 1


def test_repl_no_longer_writes_the_old_flat_transcript(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr("vantage.chattitle.maybe_retitle", lambda *a, **k: False)
    lines = iter(["hello", "exit"])
    chat_module.main(settings=settings, _conversation=_RecordingConversation(),
                     _input=lambda prompt: next(lines))
    assert list((tmp_path / "reports").glob("chat-*.md")) == []
