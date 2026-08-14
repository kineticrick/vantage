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
    return {"sector": "Technology", "name": "Micron Technology"}

def _fake_download_rise_then_fall(tickers, period):
    # Rises for 200 sessions (100 -> 299, the peak), then falls for 100
    # sessions (298 -> 199) — gives a known, non-zero, negative drawdown to
    # assert against, rather than a monotonic series where it's always 0.
    n = 300
    idx = pd.date_range("2024-06-01", periods=n, freq="D")
    cols = pd.MultiIndex.from_product([["Close", "Volume"], tickers])
    data = {}
    for t in tickers:
        prices = [100.0 + i for i in range(200)] + [299.0 - i for i in range(1, 101)]
        data[("Close", t)] = prices
        data[("Volume", t)] = [1000.0] * n
    return pd.DataFrame(data, index=idx, columns=cols)

def test_get_ticker_metrics_returns_real_numbers(tmp_path):
    out = get_ticker_metrics("MU", _settings(tmp_path),
                             _downloader=_fake_download, _info_fn=_fake_sector)
    assert out["ticker"] == "MU"
    assert out["name"] == "Micron Technology"
    assert out["sector"] == "Technology"
    assert out["ret_12m"] is not None and out["ret_12m"] > 0
    assert out["volume_ratio"] > 1.0
    assert "error" not in out

def test_get_ticker_metrics_error_on_no_data(tmp_path):
    def empty_download(tickers, period):
        return pd.DataFrame()
    out = get_ticker_metrics("ZZZZ", _settings(tmp_path),
                             _downloader=empty_download, _info_fn=_fake_sector)
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

def test_run_screen_returns_term_structure_per_leader(tmp_path):
    from vantage.chat_tools import run_screen
    import pandas as pd
    from vantage.data_ingest import MarketData
    (tmp_path / "universe.txt").write_text("AAA\n")
    idx = pd.date_range("2024-01-01", periods=300, freq="D")
    rising = pd.Series([100.0 * 1.006 ** i for i in range(300)], index=idx)
    md = MarketData(as_of="2026-08-14", prices={"AAA": rising},
                    volumes={"AAA": pd.Series([1000.0] * 300, index=idx)},
                    sectors={"AAA": "Tech"}, names={"AAA": "Alpha"})
    class _S:
        config_dir = tmp_path
        cache_dir = None
    out = run_screen(_S(), _market_data_fn=lambda tickers, cache_dir: md)
    ts = out["leaders"][0]["term_structure"]
    assert [e["label"] for e in ts] == ["1m", "3m", "6m", "12m", "off high"]
    # Values computed directly from the fixture's 0.6%/day compounding
    # (via _trailing_return/term_structure), not just "ends with %" — a
    # wrong window or a swapped sign would fail these.
    assert ts[0]["display"] == "+13.4%"    # 1m:  1.006**21  - 1
    assert ts[3]["display"] == "+352%"     # 12m: 1.006**252 - 1
    assert ts[4]["display"] == "+0.0%"     # off high: monotonic rise, never below its peak

def test_get_ticker_metrics_includes_drawdown(tmp_path):
    from vantage.chat_tools import get_ticker_metrics
    class _S:
        cache_dir = tmp_path / "cache-rising"   # own cache dir: fetch_market_data
                                                 # caches per (batch, period), and a
                                                 # shared dir would return another
                                                 # test's fixture instead of calling
                                                 # this test's _downloader.
    out = get_ticker_metrics("AAPL", _S(), _downloader=_fake_download,
                             _info_fn=_fake_sector)
    assert "drawdown_from_high" in out
    # Rising fixture never dips below its own high -> drawdown is exactly 0,
    # not merely present. See test_get_ticker_metrics_drawdown_matches_known_peak
    # for a non-zero, sign-sensitive check.
    assert out["drawdown_from_high"] == 0.0

def test_get_ticker_metrics_omits_drawdown_when_unavailable(tmp_path):
    # Non-positive prices -> drawdown_from_high returns None. The key is then
    # OMITTED, matching screener.py and spec 2.1 — not set to None.
    from vantage.chat_tools import get_ticker_metrics
    def _flat_zero(tickers, period):
        n = 300
        idx = pd.date_range("2024-06-01", periods=n, freq="D")
        cols = pd.MultiIndex.from_product([["Close", "Volume"], tickers])
        data = {}
        for t in tickers:
            data[("Close", t)] = [0.0] * n
            data[("Volume", t)] = [1000.0] * n
        return pd.DataFrame(data, index=idx, columns=cols)
    class _S:
        cache_dir = tmp_path / "cache-zero"
    out = get_ticker_metrics("AAPL", _S(), _downloader=_flat_zero,
                             _info_fn=_fake_sector)
    assert "error" not in out
    assert "drawdown_from_high" not in out

def test_run_screen_volume_spikes_carry_term_structure(tmp_path):
    # Same concept, same shape, whichever signal type it hangs off — the spike
    # branch was the only one of the three layers that dropped it.
    from vantage.chat_tools import run_screen
    idx = pd.date_range("2024-01-01", periods=300, freq="D")
    rising = pd.Series([100.0 * 1.006 ** i for i in range(300)], index=idx)
    vol = pd.Series([1000.0] * 299 + [9000.0], index=idx)   # last-day spike
    (tmp_path / "universe.txt").write_text("AAA\n")
    md = MarketData(as_of="2026-08-14", prices={"AAA": rising},
                    volumes={"AAA": vol}, sectors={"AAA": "Tech"},
                    names={"AAA": "Alpha"})
    class _S:
        config_dir = tmp_path
        cache_dir = None
    out = run_screen(_S(), _market_data_fn=lambda tickers, cache_dir: md)
    ts = out["volume_spikes"][0]["term_structure"]
    assert [e["label"] for e in ts] == ["1m", "3m", "6m", "12m", "off high"]
    assert ts[3]["display"] == "+352%"     # 12m: 1.006**252 - 1

def test_tool_schemas_name_what_they_return():
    # The schema is the model's contract; a key the tool returns but the
    # description omits is a key the model does not know to ask about.
    by_name = {t["name"]: t["description"] for t in TOOL_DEFINITIONS}
    assert "drawdown_from_high" in by_name["get_ticker_metrics"]
    assert "term_structure" in by_name["run_screen"]

def test_get_ticker_metrics_drawdown_matches_known_peak(tmp_path):
    from vantage.chat_tools import get_ticker_metrics
    import pytest
    class _S:
        cache_dir = tmp_path / "cache-rise-then-fall"
    out = get_ticker_metrics("AAPL", _S(), _downloader=_fake_download_rise_then_fall,
                             _info_fn=_fake_sector)
    # Fixture rises 100 -> 299 (the peak) then falls to 199. drawdown_from_high
    # must be <= 0 and equal to last/peak - 1 for the known peak/last pair —
    # a swapped sign or wrong window would fail this, unlike a bare "key present" check.
    expected = 199.0 / 299.0 - 1.0
    assert out["drawdown_from_high"] <= 0
    assert out["drawdown_from_high"] == pytest.approx(expected)
