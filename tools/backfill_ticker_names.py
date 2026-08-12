"""Fill company names into cache/sectors.json for already-cached tickers.

Entries written before names existed are age-fresh for 30 days, so they would
not re-fetch on their own. This walks them once. Writes incrementally, so it
is safe to interrupt and re-run — completed tickers are skipped.

Run:  .venv/bin/python tools/backfill_ticker_names.py
Tooling only; the weekly pipeline never needs it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vantage.data_ingest import _default_info_fn  # noqa: E402


def _cache_path(cache_dir):
    return Path(cache_dir) / "sectors.json"


def backfill(cache_dir, info_fn=None, save_every=25, log=print) -> dict:
    info_fn = info_fn or _default_info_fn
    path = _cache_path(cache_dir)
    if not path.exists():
        log(f"No cache at {path}; nothing to do.")
        return {"filled": 0, "skipped": 0, "failed": 0}
    cache = json.loads(path.read_text(encoding="utf-8"))
    todo = [t for t, e in cache.items() if isinstance(e, dict) and "name" not in e]
    stats = {"filled": 0, "skipped": len(cache) - len(todo), "failed": 0}
    log(f"{len(todo)} of {len(cache)} tickers need names.")
    for n, ticker in enumerate(todo, 1):
        try:
            info = info_fn(ticker)
            cache[ticker]["name"] = info.get("name")
            if info.get("sector"):
                cache[ticker]["sector"] = info["sector"]
            stats["filled"] += 1
        except Exception as e:  # one bad ticker must never end the run
            log(f"  {ticker}: {e}")
            stats["failed"] += 1
        if n % save_every == 0:
            path.write_text(json.dumps(cache), encoding="utf-8")
            log(f"  {n}/{len(todo)} …")
    path.write_text(json.dumps(cache), encoding="utf-8")
    log(f"Done: {stats}")
    return stats


if __name__ == "__main__":
    from vantage.settings import load_settings
    backfill(load_settings().cache_dir)
