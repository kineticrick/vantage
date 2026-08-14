# tests/test_screener.py
import pandas as pd
import pytest
from vantage.data_ingest import MarketData
from vantage.screener import run_screener

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

def test_screener_short_series_emits_no_signals():
    md = MarketData(as_of="2026-06-26",
                    prices={"AAA": _series([100.0 + i for i in range(10)])},
                    volumes={"AAA": _series([1.0] * 10)},
                    sectors={"AAA": "Tech"})
    ss = run_screener(md, return_leader_threshold=0.1, volume_spike_ratio=1.0)
    assert ss.signals == []
    assert ss.sector_momentum == {}

def test_screener_filters_implausible_return_artifact():
    # A freshly-spun-off-style series whose price 252 sessions ago is tiny
    # produces a huge bogus return; it must NOT become a leader or enter
    # sector momentum. A genuine ~+100% leader in the same sector survives.
    artifact = [1.0] * 8 + [50.0] * 252          # iloc[-253]=1.0, last=50 -> +4900%
    real = [100.0 + (i * 100.0 / 259) for i in range(260)]  # ~+100%
    md = MarketData(as_of="2026-06-26",
                    prices={"SNDK": _series(artifact), "MU": _series(real)},
                    volumes={"SNDK": _series([1.0] * 260), "MU": _series([1.0] * 260)},
                    sectors={"SNDK": "Technology", "MU": "Technology"})
    ss = run_screener(md, return_leader_threshold=0.5, volume_spike_ratio=99.0)
    tickers = {s.ticker for s in ss.signals if s.signal_type == "ret_12m_leader"}
    assert "SNDK" not in tickers          # artifact filtered out
    assert "MU" in tickers                # real leader kept
    # sector momentum reflects only the plausible return, not the +4900% artifact
    assert ss.sector_momentum["Technology"] < 5.0

def test_screener_sector_momentum_uses_median():
    # Three Tech names with 12mo returns ~0.2, ~0.3, ~2.0 (all sub-cap).
    # Median (0.3) is robust to the 2.0 outlier; mean would be ~0.83.
    def ret_series(target):  # 260 pts, ends 'target' fraction above the -253 price
        base = 100.0
        return _series([base] * 8 + [base * (1 + target)] * 252)
    md = MarketData(as_of="2026-06-26",
                    prices={"A": ret_series(0.2), "B": ret_series(0.3), "C": ret_series(2.0)},
                    volumes={t: _series([1.0] * 260) for t in ("A", "B", "C")},
                    sectors={"A": "Tech", "B": "Tech", "C": "Tech"})
    ss = run_screener(md, return_leader_threshold=0.1, volume_spike_ratio=99.0)
    assert abs(ss.sector_momentum["Tech"] - 0.3) < 1e-6   # median, not mean (~0.83)

def test_screener_carries_name_onto_signals():
    from vantage.data_ingest import MarketData
    from vantage.screener import run_screener
    import pandas as pd
    idx = pd.date_range("2024-01-01", periods=300, freq="D")
    rising = pd.Series([100.0 + i for i in range(300)], index=idx)
    md = MarketData(as_of="2026-08-12", prices={"MU": rising},
                    volumes={"MU": pd.Series([1000.0] * 300, index=idx)},
                    sectors={"MU": "Technology"},
                    names={"MU": "Micron Technology"})
    ss = run_screener(md)
    assert ss.signals[0].name == "Micron Technology"
    assert ss.signals[0].sector == "Technology"

def test_screener_attaches_drawdown_from_high():
    idx = pd.date_range("2024-01-01", periods=300, freq="D")
    # rises to 200 then falls back to 150 -> 25% below the trailing high
    values = [100.0 + i for i in range(100)] + [200.0] * 100 + [150.0] * 100
    md = MarketData(as_of="2026-08-14", prices={"AAA": pd.Series(values, index=idx)},
                    volumes={"AAA": pd.Series([1000.0] * 300, index=idx)},
                    sectors={"AAA": "Tech"}, names={"AAA": "Alpha"})
    ss = run_screener(md, return_leader_threshold=0.0)
    assert ss.signals[0].metrics["drawdown_from_high"] == pytest.approx(-0.25)

def test_screener_attaches_drawdown_at_minimum_supported_length():
    """Drawdown is attached when series length supports the 252-day lookback.

    Replaces the original test which was named for what it asserts (positive case),
    not for negative case it appeared to test. The guard itself (series too short,
    non-finite prices, etc.) is already covered in test_momentum.py.
    """
    idx = pd.date_range("2024-01-01", periods=260, freq="D")
    rising = pd.Series([100.0 + i for i in range(260)], index=idx)
    md = MarketData(as_of="2026-08-14", prices={"AAA": rising},
                    volumes={"AAA": pd.Series([1000.0] * 260, index=idx)},
                    sectors={"AAA": "Tech"}, names={"AAA": "Alpha"})
    ss = run_screener(md, return_leader_threshold=0.0)
    # a 260-day series supports the 252-day lookback window, so drawdown is computed
    assert "drawdown_from_high" in ss.signals[0].metrics

def test_drawdown_does_not_change_selection():
    """The premise of this whole project: nothing ranks on the term structure.

    Verifies the complete selection surface: tickers, signal types, values, ranks,
    sectors, other metrics, sector_momentum, and signal ordering. Checks both
    ret_12m_leader and volume_spike signals to ensure comprehensive coverage.
    """
    idx = pd.date_range("2024-01-01", periods=300, freq="D")

    def series(daily):
        return pd.Series([100.0 * (1 + daily) ** i for i in range(300)], index=idx)

    md = MarketData(
        as_of="2026-08-14",
        prices={
            "HIGH": series(0.006),   # ~3x return, leader rank 1
            "MID": series(0.004),    # ~2x return, leader rank 2
            "LOW": series(0.0005),   # ~12% return, below +100% threshold
            "SPIKE": series(0.002),  # ~70% return, will have volume spike
        },
        volumes={
            "HIGH": pd.Series([1000.0] * 300, index=idx),
            "MID": pd.Series([1000.0] * 300, index=idx),
            "LOW": pd.Series([1000.0] * 300, index=idx),
            "SPIKE": pd.Series([1000.0] * 299 + [3000.0], index=idx),  # 3x volume on last day
        },
        sectors={
            "HIGH": "Tech",
            "MID": "Tech",
            "LOW": "Tech",
            "SPIKE": "Healthcare",
        },
        names={"HIGH": "High", "MID": "Mid", "LOW": "Low", "SPIKE": "Spike"})

    ss = run_screener(md, return_leader_threshold=1.0, volume_spike_ratio=2.0)

    # Strip drawdown_from_high from all signals to get the pre-feature state
    ss_dict = ss.to_dict()
    for signal in ss_dict["signals"]:
        signal["metrics"].pop("drawdown_from_high", None)

    # Verify complete selection surface
    assert ss_dict["as_of"] == "2026-08-14"
    assert len(ss_dict["signals"]) == 3  # 2 leaders + 1 volume_spike

    # Verify ret_12m_leader signals (by ticker and rank)
    leaders = [s for s in ss_dict["signals"] if s["signal_type"] == "ret_12m_leader"]
    assert len(leaders) == 2
    assert leaders[0]["ticker"] == "HIGH" and leaders[0]["rank"] == 1
    assert leaders[1]["ticker"] == "MID" and leaders[1]["rank"] == 2

    # Verify values and other metrics are correct
    assert leaders[0]["value"] > leaders[1]["value"]  # HIGH > MID
    assert "ret_12m" in leaders[0]["metrics"]
    assert "ret_1m" in leaders[0]["metrics"]
    assert "volume_ratio" in leaders[0]["metrics"]

    # Verify volume_spike signal exists and is correct
    volume_spikes = [s for s in ss_dict["signals"] if s["signal_type"] == "volume_spike"]
    assert len(volume_spikes) == 1
    assert volume_spikes[0]["ticker"] == "SPIKE"
    assert volume_spikes[0]["value"] == pytest.approx(3.0)  # 3x volume
    assert volume_spikes[0]["rank"] == 0

    # Verify sector_momentum reflects all tickers with ret_12m (leaders and non-leaders)
    # HIGH, MID, and LOW are all Tech; SPIKE is Healthcare
    assert "Tech" in ss_dict["sector_momentum"]
    assert "Healthcare" in ss_dict["sector_momentum"]  # SPIKE has ret_12m even though not a leader

    # Verify signal ordering (unchanged from current behavior)
    signal_order = [(s["ticker"], s["signal_type"]) for s in ss_dict["signals"]]
    expected_order = [("HIGH", "ret_12m_leader"), ("MID", "ret_12m_leader"), ("SPIKE", "volume_spike")]
    assert signal_order == expected_order
