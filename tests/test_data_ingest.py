# tests/test_data_ingest.py
from datetime import date
import pandas as pd
from vantage.data_ingest import fetch_market_data, MarketData

def _fake_download(tickers, period):
    # Mimic yfinance.download multiindex columns: (field, ticker)
    idx = pd.date_range("2025-06-01", periods=5, freq="D")
    cols = pd.MultiIndex.from_product([["Close", "Volume"], tickers])
    data = {}
    for f in ["Close", "Volume"]:
        for t in tickers:
            base = 100.0 if f == "Close" else 1000.0
            data[(f, t)] = [base + i for i in range(5)]
    return pd.DataFrame(data, index=idx, columns=cols)

def _fake_sector(ticker):
    return {"sector": {"AAPL": "Technology", "MU": "Technology"}.get(ticker, "Unknown"),
            "name": {"AAPL": "Apple Inc.", "MU": "Micron Technology"}.get(ticker)}

def test_fetch_market_data_builds_series(tmp_path):
    md = fetch_market_data(["AAPL", "MU"], cache_dir=tmp_path, batch_size=2,
                           _downloader=_fake_download, _info_fn=_fake_sector)
    assert isinstance(md, MarketData)
    assert md.as_of == date.today().isoformat()
    assert "AAPL" in md.prices and len(md.prices["AAPL"]) == 5
    assert md.prices["AAPL"].iloc[-1] == 104.0
    assert md.volumes["MU"].iloc[0] == 1000.0
    assert md.sectors["AAPL"] == "Technology"

def test_fetch_market_data_caches(tmp_path):
    calls = {"n": 0}
    def counting_download(tickers, period):
        calls["n"] += 1
        return _fake_download(tickers, period)
    fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1,
                      _downloader=counting_download, _info_fn=_fake_sector)
    md2 = fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1,
                            _downloader=counting_download, _info_fn=_fake_sector)
    assert calls["n"] == 1  # second run served from cache
    assert len(md2.prices["AAPL"]) == 5

def test_fetch_market_data_caches_sectors(tmp_path):
    calls = {"n": 0}
    def counting_sector(t):
        calls["n"] += 1
        return {"sector": "Technology", "name": "Apple Inc."}
    fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1,
                      _downloader=_fake_download, _info_fn=counting_sector)
    fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1,
                      _downloader=_fake_download, _info_fn=counting_sector)
    assert calls["n"] == 1  # sectors served from sidecar on the second run

def test_fetch_market_data_handles_flat_columns(tmp_path):
    import pandas as pd
    idx = pd.date_range("2025-06-01", periods=5, freq="D")
    flat = pd.DataFrame({"Close": [100.0 + i for i in range(5)],
                         "Volume": [1000.0] * 5}, index=idx)
    md = fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1,
                           _downloader=lambda tickers, period: flat,
                           _info_fn=_fake_sector)
    assert len(md.prices["AAPL"]) == 5
    assert md.volumes["AAPL"].iloc[0] == 1000.0

def test_sector_cache_is_long_lived_across_price_refresh(tmp_path):
    # A fresh sector entry is reused even when the price cache misses
    # (a different period yields a different parquet key). The old per-batch
    # sidecar would have re-fetched here; the long-lived cache must not.
    calls = {"n": 0}
    def counting_sector(t):
        calls["n"] += 1
        return {"sector": "Technology", "name": "Apple Inc."}
    fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1, period="1y",
                      _downloader=_fake_download, _info_fn=counting_sector)
    fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1, period="6mo",
                      _downloader=_fake_download, _info_fn=counting_sector)
    assert calls["n"] == 1  # sector not re-fetched despite a fresh price download

def test_sector_cache_refetches_when_stale(tmp_path):
    import json
    from datetime import date, timedelta
    old = (date.today() - timedelta(days=40)).isoformat()
    (tmp_path / "sectors.json").write_text(
        json.dumps({"AAPL": {"sector": "OldSector", "name": "Apple Inc.", "fetched": old}}))
    calls = {"n": 0}
    def counting_sector(t):
        calls["n"] += 1
        return {"sector": "Technology", "name": "Apple Inc."}
    md = fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1,
                           _downloader=_fake_download, _info_fn=counting_sector)
    assert calls["n"] == 1                  # stale entry -> re-fetched
    assert md.sectors["AAPL"] == "Technology"

def test_fetch_default_period_exceeds_12mo_window():
    # Regression guard: data_ingest must fetch MORE than 252 trading sessions so
    # the screener's 12-month (252-day) lookback can compute. "1y" (~252
    # sessions) is one session too short and silently yields no 12mo leaders.
    import inspect
    default = inspect.signature(fetch_market_data).parameters["period"].default
    assert default not in ("1y", "ytd", "6mo", "3mo", "1mo"), \
        f"period {default!r} too short for the 252-day screener window"

def _fake_info(ticker):
    return {"AAPL": {"sector": "Technology", "name": "Apple Inc."},
            "MU": {"sector": "Technology", "name": "Micron Technology"}}.get(
                ticker, {"sector": "Unknown", "name": None})

def test_fetch_market_data_captures_names(tmp_path):
    md = fetch_market_data(["AAPL", "MU"], cache_dir=tmp_path, batch_size=2,
                           _downloader=_fake_download, _info_fn=_fake_info)
    assert md.names["AAPL"] == "Apple Inc."
    assert md.sectors["MU"] == "Technology"

def test_name_survives_cache_round_trip(tmp_path):
    fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1,
                      _downloader=_fake_download, _info_fn=_fake_info)
    md2 = fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1,
                            _downloader=_fake_download, _info_fn=_fake_info)
    assert md2.names["AAPL"] == "Apple Inc."

def test_legacy_cache_entry_without_name_is_refetched(tmp_path):
    import json
    from datetime import date
    # A fresh-by-age entry from before names existed.
    (tmp_path / "sectors.json").write_text(json.dumps(
        {"AAPL": {"sector": "Technology", "fetched": date.today().isoformat()}}))
    calls = {"n": 0}
    def counting_info(t):
        calls["n"] += 1
        return _fake_info(t)
    md = fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1,
                           _downloader=_fake_download, _info_fn=counting_info)
    assert calls["n"] == 1              # missing name => stale, re-fetched
    assert md.names["AAPL"] == "Apple Inc."

def test_cached_none_name_does_not_refetch(tmp_path):
    # A ticker with genuinely no company name (e.g. no longName/shortName in
    # .info) caches {"name": None}. The "name" key is present -- just null --
    # so this must NOT be treated as a pre-name-era legacy entry: re-fetching
    # it forever would mean every no-name ticker hits yfinance on every run.
    calls = {"n": 0}
    def counting_info(t):
        calls["n"] += 1
        return _fake_info(t)
    fetch_market_data(["ZZZZ"], cache_dir=tmp_path, batch_size=1,
                      _downloader=_fake_download, _info_fn=counting_info)
    fetch_market_data(["ZZZZ"], cache_dir=tmp_path, batch_size=1,
                      _downloader=_fake_download, _info_fn=counting_info)
    assert calls["n"] == 1              # name present-but-None => not stale
