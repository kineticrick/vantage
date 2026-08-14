"""Does the trajectory score predict forward returns better than 12m rank?

Forms cohorts at past dates and measures what happened next. The 12-month
leader cohort is the control: it is exactly what Vantage does today, so the
headline number is the spread between the accelerating cohort and it.

Read the caveats in the generated report before believing anything here. The
universe is today's index membership, so the study is survivorship-biased.

Run:  .venv/bin/python tools/backtest_momentum.py
Tooling only.
"""
import json  # unused in Task 5; Task 6's CLI serializes run_backtest's output with it
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vantage.momentum import (MomentumParams, classify, drawdown_from_high,  # noqa: E402
                              realized_volatility)

WINDOW_DAYS = {"ret_1m": 21, "ret_3m": 63, "ret_6m": 126, "ret_12m": 252}
MAX_PLAUSIBLE_RETURN = 10.0     # same artifact guard the screener uses


def formation_positions(n_rows, lookback=252, forward=126, step=21):
    """Row positions with enough history behind and forward return ahead."""
    last = n_rows - forward - 1
    if last < lookback:
        return []
    return list(range(lookback, last + 1, step))


def metrics_at(values, pos):
    """Trailing returns measured backwards from integer position `pos`."""
    out = {}
    for key, days in WINDOW_DAYS.items():
        start = pos - days
        if start < 0:
            return None
        past, last = values[start], values[pos]
        if not np.isfinite(past) or not np.isfinite(last) or past <= 0:
            return None
        r = float(last / past - 1.0)
        if abs(r) > MAX_PLAUSIBLE_RETURN:
            return None
        out[key] = r
    return out


def forward_return(values, pos, horizon):
    end = pos + horizon
    if end >= len(values):
        return None
    past, last = values[pos], values[end]
    if not np.isfinite(past) or not np.isfinite(last) or past <= 0:
        return None
    return float(last / past - 1.0)


def run_period(prices, pos, params, n_cohort=15, benchmark="SPY",
               horizons=(21, 63, 126)) -> dict:
    """Form cohorts at one date and measure what happened next."""
    arrays = {c: prices[c].to_numpy(dtype="float64") for c in prices.columns}
    bench_metrics = metrics_at(arrays[benchmark], pos) if benchmark in arrays else None

    scored, leaders, fading, universe = [], [], [], []
    for ticker, values in arrays.items():
        if ticker == benchmark:
            continue
        m = metrics_at(values, pos)
        if m is None:
            continue
        window = pd.Series(values[:pos + 1])
        t = classify(m, benchmark_metrics=bench_metrics,
                     volatility=realized_volatility(window),
                     drawdown=drawdown_from_high(window), params=params)
        universe.append(ticker)
        leaders.append((ticker, m["ret_12m"]))
        if t.label == "accelerating" and t.score is not None and np.isfinite(t.score):
            scored.append((ticker, t.score))
        elif t.label == "fading":
            fading.append(ticker)

    scored.sort(key=lambda kv: -kv[1])
    leaders.sort(key=lambda kv: -kv[1])
    cohorts = {
        "accelerating": [t for t, _ in scored[:n_cohort]],
        "leaders": [t for t, _ in leaders[:n_cohort]],
        # Unlike accelerating/leaders, "fading" is not ranked by anything --
        # classify() doesn't score fading names, only accelerating ones (see
        # vantage/momentum.py). `fading[:n_cohort]` used to take an arbitrary
        # positional slice in column-iteration order (parquet column order,
        # i.e. roughly alphabetical), which silently measured only the
        # alphabetic head of the fading population rather than the fading
        # population itself. Report the full population instead: it is the
        # honest answer to "does the fade label predict?", at the cost of
        # not being directly comparable in size to the ranked top-n_cohort
        # accelerating/leaders cohorts.
        "fading": fading,
        "universe": universe,
    }

    forward = {}
    for h in horizons:
        forward[h] = {}
        for name, members in cohorts.items():
            rs = [forward_return(arrays[t], pos, h) for t in members]
            rs = [r for r in rs if r is not None]
            forward[h][name] = float(np.median(rs)) if rs else None
    return {**cohorts, "forward": forward, "pos": pos}


def run_backtest(prices, params, n_cohort=15, benchmark="SPY",
                 horizons=(21, 63, 126), step=21) -> dict:
    positions = formation_positions(len(prices), forward=max(horizons), step=step)
    periods = [run_period(prices, p, params, n_cohort, benchmark, horizons)
               for p in positions]
    out = {"periods": len(periods), "cohorts": {}, "spread_vs_leaders": {}}
    for h in horizons:
        out["cohorts"][h] = {}
        for name in ("accelerating", "leaders", "fading", "universe"):
            vals = [p["forward"][h][name] for p in periods
                    if p["forward"][h].get(name) is not None]
            out["cohorts"][h][name] = {
                "median": float(np.median(vals)) if vals else None,
                "mean": float(np.mean(vals)) if vals else None,
                "periods": len(vals),
            }
        a = out["cohorts"][h]["accelerating"]["median"]
        b = out["cohorts"][h]["leaders"]["median"]
        out["spread_vs_leaders"][h] = (a - b) if (a is not None and b is not None) else None
    return out


SWEEP = [
    ("baseline", MomentumParams()),
    ("strict 1m gate", MomentumParams(min_1m_return=0.0)),
    ("no 1m gate", MomentumParams(min_1m_return=-1.0)),
    ("6m recent window", MomentumParams(recent_window="ret_6m")),
    ("no vol normalization", MomentumParams(use_volatility=False)),
    ("strength floor 15%", MomentumParams(min_recent_return=0.15)),
]


def main(argv=None):
    from vantage.settings import load_settings
    s = load_settings()
    hist = sorted((s.cache_dir / "history").glob("prices-*.parquet"))
    if not hist:
        print("No history snapshot. Run tools/fetch_history.py first.")
        return 1
    prices = pd.read_parquet(hist[-1]).sort_index()
    print(f"{hist[-1].name}: {len(prices.columns)} tickers, {len(prices)} sessions")
    results = {}
    for label, params in SWEEP:
        out = run_backtest(prices, params)
        results[label] = out
        print(f"\n=== {label} — {out['periods']} formation dates ===")
        for h in (21, 63, 126):
            c = out["cohorts"][h]
            fmt = lambda v: "n/a" if v is None else f"{v:+.2%}"
            print(f"  {h:>3}d fwd  accel {fmt(c['accelerating']['median'])}"
                  f"  leaders {fmt(c['leaders']['median'])}"
                  f"  universe {fmt(c['universe']['median'])}"
                  f"  fading {fmt(c['fading']['median'])}"
                  f"  spread {fmt(out['spread_vs_leaders'][h])}")
    out_path = s.cache_dir / "history" / "backtest-results.json"
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
