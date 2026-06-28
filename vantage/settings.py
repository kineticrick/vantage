import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PA_PATH = os.path.expanduser("~/code/python/wake")  # the Wake project (portfolio data)

@dataclass
class Settings:
    anthropic_api_key: str
    gmail_user: str
    gmail_app_password: str
    email_recipient: str
    model: str
    portfolio_analysis_path: str
    project_root: Path
    config_dir: Path
    data_dir: Path
    reports_dir: Path
    cache_dir: Path

def load_settings(load_dotenv_file: bool = True) -> Settings:
    if load_dotenv_file:
        load_dotenv(PROJECT_ROOT / ".env")
    data_dir = PROJECT_ROOT / "data"
    reports_dir = PROJECT_ROOT / "reports"
    cache_dir = PROJECT_ROOT / "cache"
    for d in (data_dir, reports_dir, cache_dir):
        d.mkdir(parents=True, exist_ok=True)
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        gmail_user=os.getenv("GMAIL_USER", ""),
        gmail_app_password=os.getenv("GMAIL_APP_PASSWORD", ""),
        email_recipient=os.getenv("EMAIL_RECIPIENT", ""),
        model=os.getenv("VANTAGE_MODEL", "claude-opus-4-8"),
        portfolio_analysis_path=os.getenv("WAKE_PATH", DEFAULT_PA_PATH),
        project_root=PROJECT_ROOT,
        config_dir=PROJECT_ROOT / "config",
        data_dir=data_dir,
        reports_dir=reports_dir,
        cache_dir=cache_dir,
    )
