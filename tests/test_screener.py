# tests/test_screener.py
import pandas as pd
from radar.data_ingest import MarketData
from radar.screener import run_screener

def _series(values):
    idx = pd.date_range("2025-06-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx)

def test_screener_flags_12m_leader_and_volume_spike():
    # 260 days so 252d lookback exists. Doubler: ends at 2x its 252-days-ago price.
    doubler = [100.0] + [100.0 + (i * 100.0 / 259) for i in range(259)]  # 100 -> 200
    flat = [50.0] * 260
    vols_spike = [1000.0] * 259 + [5000.0]  # last day 5x
    vols_flat = [1000.0] * 260
    md = MarketData(
        as_of="2026-06-26",
        prices={"MU": _series(doubler), "AAPL": _series(flat)},
        volumes={"MU": _series(vols_spike), "AAPL": _series(vols_flat)},
        sectors={"MU": "Technology", "AAPL": "Technology"},
    )
    ss = run_screener(md, return_leader_threshold=0.9, volume_spike_ratio=2.0)
    types = {(s.ticker, s.signal_type) for s in ss.signals}
    assert ("MU", "ret_12m_leader") in types
    assert ("MU", "volume_spike") in types
    assert ("AAPL", "ret_12m_leader") not in types
    assert ss.sector_momentum["Technology"] > 0  # MU pulls it positive

def test_screener_ranks_by_12m_return():
    big = [100.0 + (i * 100.0 / 259) for i in range(260)]   # ~+100%
    small = [100.0 + (i * 20.0 / 259) for i in range(260)]  # ~+20%
    md = MarketData(as_of="2026-06-26",
                    prices={"BIG": _series(big), "SM": _series(small)},
                    volumes={"BIG": _series([1.0]*260), "SM": _series([1.0]*260)},
                    sectors={"BIG": "Tech", "SM": "Tech"})
    ss = run_screener(md, return_leader_threshold=0.1, volume_spike_ratio=99.0)
    leaders = [s for s in ss.signals if s.signal_type == "ret_12m_leader"]
    assert leaders[0].ticker == "BIG" and leaders[0].rank == 1
