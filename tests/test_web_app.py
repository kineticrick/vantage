from pathlib import Path
from fastapi.testclient import TestClient
from vantage.settings import Settings
from vantage.web.app import create_app, _sse

def _settings(tmp_path):
    for sub in ("reports", "data", "config", "cache"):
        (tmp_path / sub).mkdir(exist_ok=True)
    return Settings(anthropic_api_key="k", gmail_user="", gmail_app_password="",
                    email_recipient="", model="claude-opus-4-8",
                    portfolio_analysis_path="/nonexistent", project_root=tmp_path,
                    config_dir=tmp_path / "config", data_dir=tmp_path / "data",
                    reports_dir=tmp_path / "reports", cache_dir=tmp_path / "cache")

def test_sse_formats_frames():
    out = list(_sse([{"type": "text", "text": "hi"}, {"type": "done"}]))
    assert out[0] == 'data: {"type": "text", "text": "hi"}\n\n'
    assert out[1] == 'data: {"type": "done"}\n\n'

def test_index_and_static_served(tmp_path):
    app = create_app(settings=_settings(tmp_path))
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Vantage" in r.text
    assert client.get("/static/app.js").status_code == 200
