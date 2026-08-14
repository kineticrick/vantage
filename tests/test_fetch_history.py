import json
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from fetch_history import fetch_history, BENCHMARKS

def _fake_download(tickers, period):
    idx = pd.date_range("2020-01-01", periods=60, freq="B")
    cols = pd.MultiIndex.from_product([["Close", "Volume"], tickers])
    data = {(f, t): [100.0 + i for i in range(60)] for f in ("Close", "Volume")
            for t in tickers}
    return pd.DataFrame(data, index=idx, columns=cols)

def test_fetch_history_writes_wide_close_frame(tmp_path):
    path = fetch_history(["AAA", "BBB"], tmp_path, batch_size=1,
                         _downloader=_fake_download, log=lambda *a: None)
    df = pd.read_parquet(path)
    assert list(df.columns) == ["AAA", "BBB"]
    assert len(df) == 60
    assert df["AAA"].iloc[-1] == 159.0

def test_fetch_history_writes_manifest(tmp_path):
    path = fetch_history(["AAA"], tmp_path, _downloader=_fake_download,
                         log=lambda *a: None)
    manifest = json.loads((Path(path).parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["period"] == "10y"
    assert manifest["tickers"] == 1
    assert manifest["last_date"] == "2020-03-24"
    assert manifest["parquet"] == Path(path).name

def test_fetch_history_survives_a_failing_batch(tmp_path):
    def flaky(tickers, period):
        if "BAD" in tickers:
            raise RuntimeError("network down")
        return _fake_download(tickers, period)
    path = fetch_history(["AAA", "BAD"], tmp_path, batch_size=1,
                         _downloader=flaky, log=lambda *a: None)
    df = pd.read_parquet(path)
    assert list(df.columns) == ["AAA"]

def test_benchmarks_are_declared():
    assert "SPY" in BENCHMARKS
