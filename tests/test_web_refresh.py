from pathlib import Path
from fastapi.testclient import TestClient
from vantage.settings import Settings
from vantage.data_ingest import MarketData
from vantage.web.app import create_app
from vantage.web.pipeline import run_refresh
import pandas as pd

def _settings(tmp_path):
    for sub in ("reports", "data", "config", "cache"):
        (tmp_path / sub).mkdir(exist_ok=True)
    (tmp_path / "config" / "universe.txt").write_text("NVDA\nMU\n")
    return Settings(anthropic_api_key="k", gmail_user="", gmail_app_password="",
                    email_recipient="", model="m", portfolio_analysis_path="/x",
                    project_root=tmp_path, config_dir=tmp_path / "config",
                    data_dir=tmp_path / "data", reports_dir=tmp_path / "reports",
                    cache_dir=tmp_path / "cache")

def _fake_market_data(tickers, cache_dir):
    idx = range(300)
    prices = {t: pd.Series([100 + i for i in idx]) for t in tickers}
    volumes = {t: pd.Series([1000 for _ in idx]) for t in tickers}
    sectors = {t: "Technology" for t in tickers}
    return MarketData(as_of="2026-06-27", prices=prices, volumes=volumes, sectors=sectors)

def test_run_refresh_emits_stages_and_writes(tmp_path):
    s = _settings(tmp_path)
    events = list(run_refresh(s, _market_data_fn=_fake_market_data,
                              _portfolio_fn=lambda p: None))
    stages = [e["stage"] for e in events if e["type"] == "progress"]
    assert stages == ["fetching market data", "screening", "loading portfolio"]
    assert events[-1] == {"type": "done", "as_of": "2026-06-27"}
    assert (s.data_dir / "signals-2026-06-27.json").exists()

def test_run_refresh_error(tmp_path):
    s = _settings(tmp_path)
    def boom(tickers, cache_dir):
        raise RuntimeError("network down")
    events = list(run_refresh(s, _market_data_fn=boom))
    assert events[-1] == {"type": "error", "message": "network down"}

def test_refresh_endpoint_streams(tmp_path):
    runner = lambda s: iter([{"type": "progress", "stage": "x"}, {"type": "done"}])
    client = TestClient(create_app(settings=_settings(tmp_path), refresh_runner=runner))
    r = client.post("/api/refresh")
    assert r.status_code == 200
    assert 'data: {"type": "progress", "stage": "x"}' in r.text
    assert 'data: {"type": "done"}' in r.text
