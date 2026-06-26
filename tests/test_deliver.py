# tests/test_deliver.py
from radar.deliver import send_email
from radar.settings import Settings
from pathlib import Path

class _FakeSMTP:
    sent = []
    def __init__(self): self.logged_in = None
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def login(self, user, pw): self.logged_in = (user, pw)
    def send_message(self, msg): _FakeSMTP.sent.append(msg)

def _settings():
    return Settings(anthropic_api_key="", gmail_user="me@gmail.com",
                    gmail_app_password="pw", email_recipient="you@gmail.com",
                    model="claude-opus-4-8", portfolio_analysis_path="/x",
                    project_root=Path("."), config_dir=Path("."),
                    data_dir=Path("."), reports_dir=Path("."), cache_dir=Path("."))

def test_send_email_builds_and_sends():
    _FakeSMTP.sent.clear()
    fake = _FakeSMTP()
    send_email("Weekly Brief", "<html><body>hi</body></html>", _settings(),
               _smtp_factory=lambda: fake)
    assert len(_FakeSMTP.sent) == 1
    msg = _FakeSMTP.sent[0]
    assert msg["From"] == "me@gmail.com"
    assert msg["To"] == "you@gmail.com"
    assert msg["Subject"] == "Weekly Brief"
    assert fake.logged_in == ("me@gmail.com", "pw")
    html_part = msg.get_body(preferencelist=("html",))
    assert "hi" in html_part.get_content()
