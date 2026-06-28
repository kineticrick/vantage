# tests/test_chat_tools.py
import pandas as pd
from pathlib import Path
from vantage.settings import Settings
from vantage.chat_tools import (get_ticker_metrics, run_screen, dispatch,
                              TOOL_DEFINITIONS, CUSTOM_TOOL_NAMES)
from vantage.data_ingest import MarketData

def _settings(tmp_path):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "universe.txt").write_text("AAPL\nMU\n")
    return Settings(anthropic_api_key="", gmail_user="", gmail_app_password="",
                    email_recipient="", model="claude-opus-4-8",
                    portfolio_analysis_path="/x", project_root=tmp_path,
                    config_dir=tmp_path / "config", data_dir=tmp_path,
                    reports_dir=tmp_path, cache_dir=tmp_path)

def _fake_download(tickers, period):
    n = 300
    idx = pd.date_range("2024-06-01", periods=n, freq="D")
    cols = pd.MultiIndex.from_product([["Close", "Volume"], tickers])
    data = {}
    for t in tickers:
        data[("Close", t)] = [100.0 + i for i in range(n)]      # rising -> real returns
        data[("Volume", t)] = [1000.0] * (n - 1) + [5000.0]     # last-day spike
    return pd.DataFrame(data, index=idx, columns=cols)

def _fake_sector(t):
    return "Technology"

def test_get_ticker_metrics_returns_real_numbers(tmp_path):
    out = get_ticker_metrics("MU", _settings(tmp_path),
                             _downloader=_fake_download, _sector_fn=_fake_sector)
    assert out["ticker"] == "MU"
    assert out["sector"] == "Technology"
    assert out["ret_12m"] is not None and out["ret_12m"] > 0
    assert out["volume_ratio"] > 1.0
    assert "error" not in out

def test_get_ticker_metrics_error_on_no_data(tmp_path):
    def empty_download(tickers, period):
        return pd.DataFrame()
    out = get_ticker_metrics("ZZZZ", _settings(tmp_path),
                             _downloader=empty_download, _sector_fn=_fake_sector)
    assert "error" in out and out["ticker"] == "ZZZZ"

def test_run_screen_summarizes(tmp_path):
    md = MarketData(as_of="2026-06-27",
                    prices={"MU": pd.Series([100.0 + i for i in range(300)],
                                            index=pd.date_range("2024-06-01", periods=300, freq="D"))},
                    volumes={"MU": pd.Series([1000.0] * 300,
                                             index=pd.date_range("2024-06-01", periods=300, freq="D"))},
                    sectors={"MU": "Technology"})
    out = run_screen(_settings(tmp_path), return_leader_threshold=0.5,
                     _market_data_fn=lambda tickers, cache_dir: md)
    assert any(l["ticker"] == "MU" for l in out["leaders"])
    assert "sector_momentum" in out and "Technology" in out["sector_momentum"]

def test_tool_defs_and_dispatch(tmp_path):
    names = {d["name"] for d in TOOL_DEFINITIONS}
    assert names == CUSTOM_TOOL_NAMES == {"get_ticker_metrics", "run_screen"}
    # each tool def has an input_schema
    assert all("input_schema" in d for d in TOOL_DEFINITIONS)
    # dispatch routes to the impl
    out = dispatch("get_ticker_metrics", {"ticker": "MU"}, _settings(tmp_path))
    assert "ticker" in out  # ran (may be error if no network, but routed)
    assert dispatch("nope", {}, _settings(tmp_path))["error"].startswith("unknown tool: ")
