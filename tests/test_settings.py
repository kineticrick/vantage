# tests/test_settings.py
from pathlib import Path
import vantage.settings as s

def test_load_settings_reads_env_and_makes_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key123")
    monkeypatch.setenv("GMAIL_USER", "a@b.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    monkeypatch.setenv("EMAIL_RECIPIENT", "a@b.com")
    monkeypatch.setattr(s, "PROJECT_ROOT", tmp_path)
    cfg = s.load_settings(load_dotenv_file=False)
    assert cfg.anthropic_api_key == "key123"
    assert cfg.model == "claude-opus-4-8"
    assert cfg.data_dir.exists() and cfg.reports_dir.exists() and cfg.cache_dir.exists()
    assert cfg.portfolio_analysis_path  # has a default
