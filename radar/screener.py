import pandas as pd
from statistics import median
from radar.models import Signal, SignalSet

_WINDOWS = {"ret_1m": 21, "ret_3m": 63, "ret_6m": 126, "ret_12m": 252}

# Returns whose magnitude exceeds this are treated as data artifacts (spin-off /
# IPO / split-adjustment glitches — e.g. a freshly spun-off ticker showing a
# +4300% "12-month" return) and dropped, so they neither become leaders nor skew
# sector momentum. Real equity moves essentially never exceed this in <= 12mo.
_MAX_PLAUSIBLE_RETURN = 10.0  # +1000%

def _trailing_return(series, lookback):
    if len(series) <= lookback:
        return None
    past = series.iloc[-(lookback + 1)]
    last = series.iloc[-1]
    if past == 0 or pd.isna(past) or pd.isna(last):
        return None
    return float(last / past - 1.0)

def _volume_ratio(series, lookback=21):
    if len(series) < lookback + 1:
        return None
    trailing = series.iloc[-(lookback + 1):-1]
    avg = float(trailing.mean())
    if avg == 0:
        return None
    return float(series.iloc[-1] / avg)

def run_screener(market_data, top_n=25, return_leader_threshold=1.0,
                 volume_spike_ratio=2.0,
                 max_plausible_return=_MAX_PLAUSIBLE_RETURN) -> SignalSet:
    rows = []
    for ticker, prices in market_data.prices.items():
        metrics = {}
        for name, lb in _WINDOWS.items():
            r = _trailing_return(prices, lb)
            # Drop implausible returns as data artifacts (see _MAX_PLAUSIBLE_RETURN).
            if r is not None and abs(r) <= max_plausible_return:
                metrics[name] = r
        vol = market_data.volumes.get(ticker)
        vr = _volume_ratio(vol) if vol is not None else None
        if vr is not None:
            metrics["volume_ratio"] = vr
        rows.append((ticker, market_data.sectors.get(ticker, "Unknown"), metrics))

    # rank by 12m return (desc); tickers without a 12m return sort last
    rows.sort(key=lambda r: r[2].get("ret_12m", float("-inf")), reverse=True)

    signals = []
    rank = 0
    for ticker, sector, metrics in rows:
        ret12 = metrics.get("ret_12m")
        if ret12 is not None and ret12 >= return_leader_threshold:
            rank += 1
            signals.append(Signal(ticker=ticker, signal_type="ret_12m_leader",
                                  value=ret12, rank=rank, sector=sector,
                                  metrics=metrics))
        vr = metrics.get("volume_ratio")
        if vr is not None and vr >= volume_spike_ratio:
            signals.append(Signal(ticker=ticker, signal_type="volume_spike",
                                  value=vr, rank=0, sector=sector, metrics=metrics))

    signals = signals[:top_n] if top_n is not None else signals

    by_sector = {}
    for _, sector, metrics in rows:
        if "ret_12m" in metrics:
            by_sector.setdefault(sector, []).append(metrics["ret_12m"])
    # median, not mean — one outlier shouldn't define a sector's momentum
    sector_momentum = {s: median(v) for s, v in by_sector.items()}

    return SignalSet(as_of=market_data.as_of, signals=signals,
                     sector_momentum=sector_momentum)
