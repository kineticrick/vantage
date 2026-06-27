# tests/test_chat.py
from pathlib import Path
import chat
from radar.settings import Settings

def _settings(tmp_path):
    (tmp_path / "reports").mkdir(exist_ok=True)
    return Settings(anthropic_api_key="k", gmail_user="", gmail_app_password="",
                    email_recipient="", model="claude-opus-4-8",
                    portfolio_analysis_path="/x", project_root=tmp_path,
                    config_dir=tmp_path, data_dir=tmp_path,
                    reports_dir=tmp_path / "reports", cache_dir=tmp_path)

class _FakeConversation:
    def __init__(self): self.sent = []
    def send(self, msg):
        self.sent.append(msg)
        yield {"type": "text", "text": f"echo: {msg}"}
        yield {"type": "done"}

def test_main_loops_streams_and_writes_transcript(tmp_path, capsys):
    s = _settings(tmp_path)
    conv = _FakeConversation()
    # feed two questions then EOF (StopIteration -> exit)
    lines = iter(["what's MU?", "and NVDA?"])
    chat.main(settings=s, _conversation=conv, _input=lambda _prompt: next(lines))
    assert conv.sent == ["what's MU?", "and NVDA?"]
    out = capsys.readouterr().out
    assert "echo: what's MU?" in out and "echo: and NVDA?" in out
    transcripts = list((s.reports_dir).glob("chat-*.md"))
    assert len(transcripts) == 1
    body = transcripts[0].read_text()
    assert "what's MU?" in body and "echo: and NVDA?" in body

def test_main_exits_on_quit_command(tmp_path):
    s = _settings(tmp_path)
    conv = _FakeConversation()
    lines = iter(["quit", "should-not-be-sent"])
    chat.main(settings=s, _conversation=conv, _input=lambda _prompt: next(lines))
    assert conv.sent == []  # quit before sending anything
