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

def fetch_market_data(tickers, cache_dir, batch_size=100, period="1y",
                      _downloader=None, _sector_fn=None) -> MarketData:
    downloader = _downloader or _default_downloader
    sector_fn = _sector_fn or _default_sector_fn
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    prices, volumes, sectors = {}, {}, {}
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        cpath = _batch_cache_path(cache_dir, batch, period)
        spath = cpath.with_name(cpath.stem + ".sectors.json")
        if cpath.exists():
            df = pd.read_parquet(cpath)
            batch_sectors = json.loads(spath.read_text()) if spath.exists() else {}
        else:
            df = downloader(batch, period)
            df.to_parquet(cpath)
            batch_sectors = {t: sector_fn(t) for t in batch}
            spath.write_text(json.dumps(batch_sectors))
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
            sectors[t] = batch_sectors.get(t) or sector_fn(t)
            present += 1
        logger.info("Batch %d: %d/%d tickers loaded", i // batch_size, present, len(batch))
    if not prices:
        logger.warning("fetch_market_data produced no price series (empty MarketData)")
    return MarketData(as_of=date.today().isoformat(),
                      prices=prices, volumes=volumes, sectors=sectors)
