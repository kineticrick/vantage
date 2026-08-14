"""Fetch a deep, single-vintage price history for the backtest.

The weekly pipeline caches 2 years keyed by fetch date, and `cache/` therefore
holds batches from several different days. Reading across those vintages
silently corrupts a term structure — the same ticker's 12-month return can
differ by hundreds of percentage points depending on which batch answers. The
study needs one dated snapshot, so this writes somewhere else entirely.

Run:  .venv/bin/python tools/fetch_history.py
Tooling only; the weekly pipeline never touches this.
"""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vantage.universe import load_universe  # noqa: E402

BENCHMARKS = ("SPY", "QQQ")


def _default_downloader(tickers, period):
    import yfinance as yf
    return yf.download(tickers, period=period, auto_adjust=True,
                       progress=False, group_by="column")


def fetch_history(tickers, out_dir, period="10y", batch_size=100,
                  _downloader=None, log=print) -> Path:
    downloader = _downloader or _default_downloader
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    closes = {}
    for i in range(0, len(tickers), batch_size):
        batch = list(tickers[i:i + batch_size])
        try:
            df = downloader(batch, period)
        except Exception as e:          # one bad batch must not end the run
            log(f"  batch {i // batch_size} failed: {e}")
            continue
        for t in batch:
            try:
                s = df[("Close", t)].dropna() if isinstance(df.columns, pd.MultiIndex) \
                    else df["Close"].dropna()
            except KeyError:
                continue
            if len(s):
                closes[t] = s
        log(f"  {min(i + batch_size, len(tickers))}/{len(tickers)} …")

    if not closes:
        raise RuntimeError("fetch_history produced no price series")

    frame = pd.DataFrame(closes).sort_index()
    stamp = date.today().isoformat()
    path = out_dir / f"prices-{stamp}.parquet"
    frame.to_parquet(path)
    (out_dir / "manifest.json").write_text(json.dumps({
        "fetched": stamp,
        "period": period,
        "tickers": len(frame.columns),
        "first_date": str(frame.index[0].date()),
        "last_date": str(frame.index[-1].date()),
        "parquet": path.name,
    }, indent=2), encoding="utf-8")
    log(f"wrote {path} — {len(frame.columns)} tickers, {len(frame)} sessions")
    return path


if __name__ == "__main__":
    from vantage.settings import load_settings
    s = load_settings()
    universe = load_universe(s.config_dir / "universe.txt")
    fetch_history(list(universe) + list(BENCHMARKS), s.cache_dir / "history")
