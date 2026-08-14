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

def test_fetch_history_raises_on_total_failure(tmp_path):
    """All batches fail: should raise, not write parquet or manifest."""
    def always_fails(tickers, period):
        raise RuntimeError("network down")
    try:
        fetch_history(["AAA"], tmp_path, _downloader=always_fails, log=lambda *a: None)
        assert False, "should have raised"
    except RuntimeError as e:
        assert "fetch_history produced no price series" in str(e)
    # Verify neither parquet nor manifest was created
    parquets = list(tmp_path.glob("prices-*.parquet"))
    manifests = list(tmp_path.glob("manifest.json"))
    assert len(parquets) == 0, f"parquet should not exist but found {parquets}"
    assert len(manifests) == 0, f"manifest should not exist but found {manifests}"

def test_fetch_history_handles_staggered_ticker_histories(tmp_path):
    """Different date ranges per ticker: should align with NaN padding."""
    def staggered_download(tickers, period):
        # AAA starts 2020-01-01, BBB starts 2020-02-01 (20 business days later)
        if "AAA" in tickers:
            idx_aaa = pd.date_range("2020-01-01", periods=60, freq="B")
            cols_aaa = pd.MultiIndex.from_product([["Close", "Volume"], ["AAA"]])
            data_aaa = {(f, "AAA"): [100.0 + i for i in range(60)]
                        for f in ("Close", "Volume")}
            df_aaa = pd.DataFrame(data_aaa, index=idx_aaa, columns=cols_aaa)
        if "BBB" in tickers:
            idx_bbb = pd.date_range("2020-02-01", periods=40, freq="B")
            cols_bbb = pd.MultiIndex.from_product([["Close", "Volume"], ["BBB"]])
            data_bbb = {(f, "BBB"): [200.0 + i for i in range(40)]
                        for f in ("Close", "Volume")}
            df_bbb = pd.DataFrame(data_bbb, index=idx_bbb, columns=cols_bbb)
        if "AAA" in tickers and "BBB" in tickers:
            # Merge both with their different indexes
            return pd.concat([df_aaa, df_bbb], axis=1)
        elif "AAA" in tickers:
            return df_aaa
        else:
            return df_bbb

    path = fetch_history(["AAA", "BBB"], tmp_path, batch_size=2,
                         _downloader=staggered_download, log=lambda *a: None)
    df = pd.read_parquet(path)
    manifest = json.loads((Path(path).parent / "manifest.json").read_text(encoding="utf-8"))

    # Manifest should reflect true bounds (union of all tickers)
    assert manifest["first_date"] == "2020-01-01"
    assert manifest["last_date"] == "2020-03-27"  # BBB's last date (40 bdays from 2020-02-03)

    # BBB should have NaN in early rows (before 2020-02-03)
    assert df.loc["2020-01-02", "BBB"] != df.loc["2020-01-02", "BBB"]  # NaN != NaN is True

    # AAA should have values in those early rows, unaffected
    assert df.loc["2020-01-02", "AAA"] == 101.0

def test_fetch_history_handles_missing_ticker_in_frame(tmp_path):
    """Downloader doesn't return one requested ticker: should skip it."""
    def partial_download(tickers, period):
        # Only return AAA, not BBB
        idx = pd.date_range("2020-01-01", periods=60, freq="B")
        cols = pd.MultiIndex.from_product([["Close", "Volume"], ["AAA"]])
        data = {(f, "AAA"): [100.0 + i for i in range(60)]
                for f in ("Close", "Volume")}
        return pd.DataFrame(data, index=idx, columns=cols)

    path = fetch_history(["AAA", "BBB"], tmp_path, batch_size=2,
                         _downloader=partial_download, log=lambda *a: None)
    df = pd.read_parquet(path)
    # Only AAA should be present, BBB skipped silently
    assert list(df.columns) == ["AAA"]
    assert len(df) == 60
