import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from backfill_ticker_names import backfill

def _cache(tmp_path, data):
    (tmp_path / "sectors.json").write_text(json.dumps(data), encoding="utf-8")

def test_backfill_fills_only_missing_names(tmp_path):
    _cache(tmp_path, {"MU": {"sector": "Technology", "fetched": "2026-08-11"},
                      "AAPL": {"sector": "Technology", "name": "Apple Inc.",
                               "fetched": "2026-08-11"}})
    calls = []
    def info_fn(t):
        calls.append(t)
        return {"sector": "Technology", "name": "Micron Technology"}
    stats = backfill(tmp_path, info_fn=info_fn, log=lambda *a: None)
    assert calls == ["MU"]                      # AAPL already had a name
    assert stats == {"filled": 1, "skipped": 1, "failed": 0}
    saved = json.loads((tmp_path / "sectors.json").read_text())
    assert saved["MU"]["name"] == "Micron Technology"
    assert saved["MU"]["sector"] == "Technology"
    assert saved["AAPL"]["name"] == "Apple Inc."

def test_backfill_survives_a_failing_ticker(tmp_path):
    _cache(tmp_path, {"BAD": {"sector": "Technology", "fetched": "2026-08-11"},
                      "MU": {"sector": "Technology", "fetched": "2026-08-11"}})
    def info_fn(t):
        if t == "BAD":
            raise RuntimeError("network down")
        return {"sector": "Technology", "name": "Micron Technology"}
    stats = backfill(tmp_path, info_fn=info_fn, log=lambda *a: None)
    assert stats["failed"] == 1 and stats["filled"] == 1
    saved = json.loads((tmp_path / "sectors.json").read_text())
    assert saved["MU"]["name"] == "Micron Technology"

def test_backfill_on_missing_cache_is_a_noop(tmp_path):
    assert backfill(tmp_path, info_fn=lambda t: {}, log=lambda *a: None) == \
        {"filled": 0, "skipped": 0, "failed": 0}
