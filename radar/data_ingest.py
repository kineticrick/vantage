import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

@dataclass
class MarketData:
    as_of: str
    prices: dict = field(default_factory=dict)
    volumes: dict = field(default_factory=dict)
    sectors: dict = field(default_factory=dict)

def _default_downloader(tickers, period):
    import yfinance as yf
    return yf.download(tickers, period=period, auto_adjust=True,
                       progress=False, group_by="column")

def _default_sector_fn(ticker):
    import yfinance as yf
    try:
        info = yf.Ticker(ticker).info
        return info.get("sector") or "Unknown"
    except Exception:
        return "Unknown"

def _batch_cache_path(cache_dir, batch, period):
    key = hashlib.sha1(
        ("|".join(batch) + period + date.today().isoformat()).encode()
    ).hexdigest()[:16]
    return Path(cache_dir) / f"batch_{key}.parquet"

def _extract_series(df, field, ticker):
    if isinstance(df.columns, pd.MultiIndex):
        return df[(field, ticker)].dropna()
    return df[field].dropna()

# Sectors barely change, so they live in one long-lived cache keyed by ticker
# (not the per-day price cache) and only re-fetch once they go stale.
SECTOR_TTL_DAYS = 30

def _sector_cache_path(cache_dir):
    return Path(cache_dir) / "sectors.json"

def _load_sector_cache(cache_dir) -> dict:
    p = _sector_cache_path(cache_dir)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (ValueError, OSError):
            return {}
    return {}

def _save_sector_cache(cache_dir, data) -> None:
    _sector_cache_path(cache_dir).write_text(json.dumps(data))

def _sector_for(ticker, cache, sector_fn, today):
    """Return the ticker's sector, fetching (and caching) only if absent or stale."""
    entry = cache.get(ticker)
    if entry:
        try:
            age = (today - date.fromisoformat(entry["fetched"])).days
            if age < SECTOR_TTL_DAYS:
                return entry["sector"]
        except (ValueError, KeyError, TypeError):
            pass  # malformed entry — re-fetch below
    sector = sector_fn(ticker)
    cache[ticker] = {"sector": sector, "fetched": today.isoformat()}
    return sector

def fetch_market_data(tickers, cache_dir, batch_size=100, period="2y",
                      _downloader=None, _sector_fn=None) -> MarketData:
    # period must exceed the screener's longest lookback (252 trading days for
    # the 12-month return). "1y" (~252 sessions) is one session too short and
    # silently yields no 12mo leaders / empty sector momentum — keep >= "2y".
    downloader = _downloader or _default_downloader
    sector_fn = _sector_fn or _default_sector_fn
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    today = date.today()
    sector_cache = _load_sector_cache(cache_dir)
    prices, volumes, sectors = {}, {}, {}
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        cpath = _batch_cache_path(cache_dir, batch, period)
        if cpath.exists():
            df = pd.read_parquet(cpath)
        else:
            df = downloader(batch, period)
            df.to_parquet(cpath)
        present = 0
        for t in batch:
            try:
                p = _extract_series(df, "Close", t)
                v = _extract_series(df, "Volume", t)
            except KeyError:
                logger.warning("Ticker %s missing from downloaded frame; skipping", t)
                continue
            prices[t] = p
            volumes[t] = v
            sectors[t] = _sector_for(t, sector_cache, sector_fn, today)
            present += 1
        logger.info("Batch %d: %d/%d tickers loaded", i // batch_size, present, len(batch))
    _save_sector_cache(cache_dir, sector_cache)
    if not prices:
        logger.warning("fetch_market_data produced no price series (empty MarketData)")
    return MarketData(as_of=today.isoformat(),
                      prices=prices, volumes=volumes, sectors=sectors)
