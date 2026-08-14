import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from backtest_momentum import (WINDOW_DAYS, formation_positions, metrics_at,
                               forward_return, run_period, run_backtest)
from vantage.momentum import MomentumParams

def _ramp(n, daily):
    return 100.0 * np.cumprod(np.full(n, 1.0 + daily))

def _frame(cols, n=700):
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.DataFrame({k: v for k, v in cols.items()}, index=idx)

def test_formation_positions_respect_lookback_and_forward():
    pos = formation_positions(700, lookback=252, forward=126, step=21)
    assert pos[0] >= 252
    assert max(pos) <= 700 - 126 - 1
    assert all(b - a == 21 for a, b in zip(pos, pos[1:]))

def test_formation_positions_empty_when_history_too_short():
    assert formation_positions(200, lookback=252, forward=126) == []

def test_metrics_at_measures_backwards_from_position():
    vals = _ramp(400, 0.001)
    m = metrics_at(vals, 399)
    assert set(m) == set(WINDOW_DAYS)
    assert m["ret_1m"] == pytest.approx(1.001 ** 21 - 1, rel=1e-9)
    assert m["ret_12m"] == pytest.approx(1.001 ** 252 - 1, rel=1e-9)

def test_metrics_at_returns_none_without_enough_history():
    assert metrics_at(_ramp(100, 0.001), 99) is None

def test_forward_return_looks_ahead():
    vals = _ramp(400, 0.002)
    assert forward_return(vals, 100, 63) == pytest.approx(1.002 ** 63 - 1, rel=1e-9)
    assert forward_return(vals, 399, 63) is None      # runs off the end

def test_run_period_ranks_accelerator_above_leader():
    # ACCEL: flat for most of the series, then a hard ramp in the trailing 63
    # rows -> big pace gap. LEADER: huge steady year, no recent change -> top
    # 12m rank, no gap.
    #
    # Deviation from the brief: the brief evaluates at pos = n - 127, but the
    # ramp (the last 63 rows of the whole n=500 series, i.e. rows 437-499) is
    # still 64 rows in the *future* relative to that formation date -- so
    # metrics_at(pos=373), which only looks backward, sees nothing but the
    # flat region and classify() returns "steady" (gap == 0), not
    # "accelerating". Confirmed against the reference classify() pipeline: it
    # only starts labeling ACCEL "accelerating" around row ~440. This test
    # instead evaluates well inside the ramp (n - 40 = 460), which is what
    # the test's own comment and name require: a formation date from which
    # the recent ramp is actually visible in trailing metrics.
    n = 500
    accel = 100.0 * np.cumprod(np.concatenate([np.full(n - 63, 1.0001),
                                               np.full(63, 1.006)]))
    leader = 100.0 * np.cumprod(np.full(n, 1.004))
    bench = 100.0 * np.cumprod(np.full(n, 1.0002))
    prices = _frame({"ACCEL": accel, "LEADER": leader, "SPY": bench}, n=n)
    # n_cohort=2 (not 1): LEADER's pace_3m and pace_12m are mathematically
    # equal (same constant daily rate compounded), but classify() derives
    # pace_3m via a 63-day raw return raised to the 4th power and pace_12m
    # via a 252-day raw return raised to the 1st power -- two different
    # floating-point paths to the same exact value, which round differently
    # by ~1e-15 and leave a nonzero-sign `gap`. On this platform that gap is
    # positive, so LEADER *is* labeled "accelerating" and enters the scored
    # list (score ~0.23) alongside ACCEL (score ~17, from a real 63-day
    # ramp). The brief's Step 4 note ("a perfectly steady ramp has
    # pace_3m == pace_12m, so gap == 0 and it must not be labeled
    # accelerating") is wrong in floating point -- gap is *never* exactly
    # 0.0 for a compounded rate here, only close to it.
    # With n_cohort=1 the earlier version of this test passed either by
    # ACCEL alone qualifying (real signal) or, just as easily, by ACCEL
    # being the sole survivor of a coin-flip over LEADER's ULP sign --
    # trivially true either way and not actually proof of ranking. Asserting
    # the full 2-element order instead proves ACCEL outranks a genuine
    # rival: ACCEL's score comes from a deliberate, large 63-day ramp and so
    # dominates LEADER's float-noise-scale score by ~70x regardless of which
    # way that noise rounds, so the *order* is robust even though whether
    # LEADER qualifies as "accelerating" at all is not.
    out = run_period(prices, n - 40, MomentumParams(), n_cohort=2)
    assert out["accelerating"] == ["ACCEL", "LEADER"]
    # Only two non-benchmark tickers exist, so n_cohort=2 pulls both into
    # "leaders" too -- the ret_12m ranking still puts LEADER first (its
    # trailing 12m return is ~174% vs ACCEL's ~18%).
    assert out["leaders"] == ["LEADER", "ACCEL"]

def test_run_period_reports_forward_returns_per_cohort():
    n = 500
    accel = 100.0 * np.cumprod(np.concatenate([np.full(n - 63, 1.0001),
                                               np.full(63, 1.006)]))
    leader = 100.0 * np.cumprod(np.full(n, 1.004))
    bench = 100.0 * np.cumprod(np.full(n, 1.0002))
    prices = _frame({"ACCEL": accel, "LEADER": leader, "SPY": bench}, n=n)
    out = run_period(prices, 300, MomentumParams(), n_cohort=1)
    assert 63 in out["forward"]
    assert set(out["forward"][63]) >= {"accelerating", "leaders", "universe"}

def test_run_backtest_aggregates_across_periods():
    n = 700
    rng = np.random.default_rng(3)
    cols = {f"T{i}": 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
            for i in range(12)}
    cols["SPY"] = 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.006, n)))
    out = run_backtest(_frame(cols, n=n), MomentumParams(), n_cohort=3)
    assert out["periods"] > 0
    for horizon in (21, 63, 126):
        assert "accelerating" in out["cohorts"][horizon]
        assert "median" in out["cohorts"][horizon]["accelerating"]
    assert "spread_vs_leaders" in out

def test_run_backtest_on_short_history_reports_zero_periods():
    prices = _frame({"AAA": _ramp(100, 0.001), "SPY": _ramp(100, 0.0005)}, n=100)
    out = run_backtest(prices, MomentumParams())
    assert out["periods"] == 0


def test_run_backtest_reports_none_not_zero_when_nothing_accelerates():
    # This pins the aggregation contract that the headline number depends
    # on. Both cohorts and the empty case are already exercised elsewhere,
    # but only by key *presence* ("median" in ...), which a regression that
    # coerced an empty cohort's median to 0.0 instead of None would still
    # satisfy -- and 0.0 would silently bias spread_vs_leaders toward
    # whichever side happened to be empty. Assert the actual values.
    #
    # Every ticker here decelerates monotonically (daily rate slides from
    # +0.3%/day down to -0.1%/day), so at every formation date the recent
    # pace is below the trailing 12m pace: gap <= 0 everywhere, and no
    # ticker is ever labeled "accelerating" by construction, not by luck.
    n = 700
    rates = np.linspace(0.003, -0.001, n)

    def _decel(offset):
        return 100.0 * np.cumprod(1.0 + rates + offset)

    cols = {f"T{i}": _decel(i * 1e-5) for i in range(5)}
    cols["SPY"] = 100.0 * np.cumprod(1.0 + rates)
    out = run_backtest(_frame(cols, n=n), MomentumParams(), n_cohort=3)
    assert out["periods"] > 0
    for h in (21, 63, 126):
        accel = out["cohorts"][h]["accelerating"]
        assert accel["median"] is None
        assert accel["mean"] is None
        assert accel["periods"] == 0

        leaders = out["cohorts"][h]["leaders"]
        assert leaders["median"] is not None
        assert leaders["periods"] > 0

        assert out["spread_vs_leaders"][h] is None


def test_run_period_fading_cohort_is_not_capped_at_n_cohort():
    # Unlike accelerating/leaders, "fading" is not ranked -- it is the full
    # population labeled fading, not a top-n_cohort slice (see the comment
    # in run_period()). Pin that: with n_cohort deliberately smaller than
    # the number of names that actually decelerate, the fading cohort must
    # still report all of them, not just n_cohort.
    #
    # Every ticker here decelerates monotonically (daily rate slides from
    # +0.3%/day down to -0.1%/day), reproducing
    # test_run_backtest_reports_none_not_zero_when_nothing_accelerates's
    # fixture. Verified directly: at pos=483, four of the five (T1-T4) are
    # labeled "fading".
    n = 700
    rates = np.linspace(0.003, -0.001, n)

    def _decel(offset):
        return 100.0 * np.cumprod(1.0 + rates + offset)

    cols = {f"T{i}": _decel(i * 1e-5) for i in range(5)}
    cols["SPY"] = 100.0 * np.cumprod(1.0 + rates)
    prices = _frame(cols, n=n)
    out = run_period(prices, 483, MomentumParams(), n_cohort=2)
    assert out["fading"] == ["T1", "T2", "T3", "T4"]
    assert len(out["fading"]) > 2   # exceeds n_cohort -- proves it isn't sliced


def test_run_period_excludes_nan_scored_ticker_from_accelerating_cohort(monkeypatch):
    # Known hazard (carried forward from an earlier task's review): a
    # Trajectory labeled "accelerating" whose .score is NaN must never enter
    # the accelerating cohort -- NaN comparisons are all False, so a NaN sort
    # key produces a silently arbitrary, unstable order rather than an error.
    #
    # vantage.momentum.classify() no longer PRODUCES such a Trajectory (it
    # coerces non-finite volatility and non-finite scores to None; see
    # test_momentum.py's finiteness tests). This test keeps the consumer-side
    # guard honest anyway -- defense in depth, since run_period's sort is
    # wrong for any non-finite score regardless of which producer supplied it.
    # classify() is monkeypatched so the hazard is exercised deterministically
    # rather than depending on the producer to misbehave.
    import backtest_momentum as bm
    from vantage.momentum import Trajectory

    def fake_classify(metrics, benchmark_metrics=None, volatility=None,
                      drawdown=None, params=None):
        return Trajectory(label="accelerating", score=float("nan"))

    monkeypatch.setattr(bm, "classify", fake_classify)

    n = 500
    nanvol = 100.0 * np.cumprod(np.concatenate([np.full(n - 63, 1.0001),
                                                np.full(63, 1.006)]))
    bench = 100.0 * np.cumprod(np.full(n, 1.0002))
    prices = _frame({"NANVOL": nanvol, "SPY": bench}, n=n)
    out = run_period(prices, n - 127, MomentumParams(), n_cohort=5)
    assert out["accelerating"] == []
    assert "NANVOL" not in out["accelerating"]
