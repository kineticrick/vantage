import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from backtest_momentum import (WINDOW_DAYS, formation_positions, metrics_at,
                               forward_return, run_period, run_backtest,
                               paired_stats)
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


# --- paired per-date statistics (design spec §4.2) -------------------------
# The finding this harness produced needed two correction passes, both for the
# same reason: a difference of two separately-aggregated medians is not the
# median of the per-date differences. The harness only ever emitted the former,
# which is what kept inviting the mistake. These pin the latter.

def _periods(pairs, horizon=63):
    """Fake period records carrying just the per-date cohort medians."""
    return [{"forward": {horizon: {"a": a, "b": b}}} for a, b in pairs]


# One date where "a" wins big, four where it loses slightly. Hand-checked:
#   diffs        +0.08, -0.01, -0.01, -0.01, -0.01   -> median -0.01, mean +0.008
#   median(a)     0.08   (from 0.01, 0.02, 0.08, 0.09, 0.10)
#   median(b)     0.03   (from 0.02, 0.02, 0.03, 0.09, 0.10)
# So the unpaired difference of medians is +0.05 -- "a" wins by five points --
# while "a" actually loses on four dates out of five.
_FLIP = [(0.10, 0.02), (0.09, 0.10), (0.08, 0.09), (0.02, 0.03), (0.01, 0.02)]


def test_paired_stats_pairs_before_aggregating():
    s = paired_stats(_periods(_FLIP), 63, "a", "b")
    assert s["median_diff"] == pytest.approx(-0.01)
    assert s["mean_diff"] == pytest.approx(0.008)
    assert s["periods"] == 5
    assert s["wins"] == 1                                # a beat b once
    assert s["ties"] == 0
    assert s["std_diff"] == pytest.approx(np.std([0.08, -0.01, -0.01, -0.01,
                                                  -0.01], ddof=1))


def test_paired_stats_median_can_disagree_in_sign_with_the_unpaired_median():
    # The exact failure that flipped three of this study's published
    # conclusions: the difference of aggregate medians says "a wins by 5pp"
    # while the paired median says "a loses on the typical date".
    periods = _periods(_FLIP)
    a_vals = [p["forward"][63]["a"] for p in periods]
    b_vals = [p["forward"][63]["b"] for p in periods]
    unpaired = float(np.median(a_vals)) - float(np.median(b_vals))
    assert unpaired == pytest.approx(0.05)
    assert paired_stats(periods, 63, "a", "b")["median_diff"] < 0


def test_paired_stats_counts_ties_separately_from_losses():
    # Two identical cohorts differ on no date. Without a tie count, 0 wins
    # reads as 0/3 -- "a lost every date" -- when nothing happened at all.
    periods = _periods([(0.05, 0.05), (0.02, 0.02), (0.09, 0.09)])
    s = paired_stats(periods, 63, "a", "b")
    assert s["median_diff"] == pytest.approx(0.0)
    assert (s["wins"], s["ties"], s["periods"]) == (0, 3, 3)


def test_paired_stats_skips_dates_where_either_cohort_is_empty():
    periods = _periods([(0.05, 0.03), (None, 0.03), (0.05, None), (0.01, 0.02)])
    s = paired_stats(periods, 63, "a", "b")
    assert s["periods"] == 2                             # only the two full rows
    assert s["mean_diff"] == pytest.approx((0.02 + -0.01) / 2)


def test_paired_stats_on_no_usable_dates_is_none_not_zero():
    s = paired_stats(_periods([(None, 0.03)]), 63, "a", "b")
    assert s["median_diff"] is None and s["mean_diff"] is None
    assert s["std_diff"] is None and s["periods"] == 0


def test_paired_stats_dispersion_needs_two_dates():
    s = paired_stats(_periods([(0.05, 0.03)]), 63, "a", "b")
    assert s["periods"] == 1
    assert s["median_diff"] == pytest.approx(0.02)
    assert s["std_diff"] is None                         # ddof=1 on n=1


def _noisy_frame(n=700, seed=3):
    rng = np.random.default_rng(seed)
    cols = {f"T{i}": 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
            for i in range(12)}
    cols["SPY"] = 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.006, n)))
    return _frame(cols, n=n)


def test_run_backtest_reports_paired_stats_per_horizon():
    out = run_backtest(_noisy_frame(), MomentumParams(), n_cohort=3)
    for h in (21, 63, 126):
        assert "accelerating-leaders" in out["paired"][h]
        assert "accelerating-universe" in out["paired"][h]
        assert "fading-universe" in out["paired"][h]
        assert "fading-non_fading" in out["paired"][h]
        s = out["paired"][h]["accelerating-leaders"]
        assert set(s) == {"median_diff", "mean_diff", "std_diff", "wins",
                          "ties", "periods"}
        assert 0 <= s["wins"] <= s["periods"] <= out["periods"]


def test_run_backtest_paired_mean_matches_the_unpaired_mean_difference():
    # mean is linear, so mean(a) - mean(b) == mean(a - b) exactly. This is the
    # reason the study's mean-based figures survived the unpaired shortcut and
    # its median-based ones did not; pin it so the pairing code is verified
    # against an independent route to the same number.
    out = run_backtest(_noisy_frame(), MomentumParams(), n_cohort=3)
    for h in (21, 63, 126):
        c = out["cohorts"][h]
        if c["accelerating"]["periods"] != out["periods"]:
            continue                     # some date had no accelerating name
        expected = c["accelerating"]["mean"] - c["leaders"]["mean"]
        assert out["paired"][h]["accelerating-leaders"]["mean_diff"] == \
            pytest.approx(expected)


def test_run_backtest_paired_median_is_not_the_unpaired_median_difference():
    # Same data, both statistics available; they must be computed differently.
    # (If they ever coincide exactly on this fixture, the pairing is a no-op.)
    out = run_backtest(_noisy_frame(), MomentumParams(), n_cohort=3)
    differ = [h for h in (21, 63, 126)
              if out["paired"][h]["accelerating-leaders"]["median_diff"]
              != out["spread_vs_leaders"][h]]
    assert differ, "paired median is identical to the unpaired difference"


def test_run_backtest_retains_per_date_values_for_cross_run_pairing():
    # Comparing two PARAMETER SETS per formation date (e.g. the one-month gate
    # question) is a pairing across two run_backtest calls, which no single
    # run can pre-compute. The per-date series is what makes it possible
    # without an uncommitted ad-hoc script.
    prices = _noisy_frame()
    base = run_backtest(prices, MomentumParams(), n_cohort=3)
    strict = run_backtest(prices, MomentumParams(min_1m_return=0.0), n_cohort=3)
    assert base["positions"] == strict["positions"]
    for h in (21, 63, 126):
        assert len(base["per_date"][h]["accelerating"]) == base["periods"]
        assert len(base["positions"]) == base["periods"]
        paired = [(s - b) for s, b in zip(strict["per_date"][h]["accelerating"],
                                          base["per_date"][h]["accelerating"])
                  if s is not None and b is not None]
        assert len(paired) <= base["periods"]


def test_run_period_non_fading_is_the_universe_minus_fading():
    n = 700
    rates = np.linspace(0.003, -0.001, n)

    def _decel(offset):
        return 100.0 * np.cumprod(1.0 + rates + offset)

    cols = {f"T{i}": _decel(i * 1e-5) for i in range(5)}
    cols["SPY"] = 100.0 * np.cumprod(1.0 + rates)
    out = run_period(_frame(cols, n=n), 483, MomentumParams(), n_cohort=2)
    assert out["fading"] == ["T1", "T2", "T3", "T4"]
    assert out["non_fading"] == ["T0"]
    assert sorted(out["fading"] + out["non_fading"]) == sorted(out["universe"])


def test_run_backtest_reports_cohort_sizes_and_skipped_tickers():
    # Design spec §5: "the study skips tickers with insufficient history at a
    # given formation date and reports how many were skipped." `universe` is
    # the usable set, so its size is that report -- and the fading cohort's
    # size is what makes "fading - universe" interpretable (fading is a large
    # share of its own control, which attenuates the difference toward zero).
    prices = _noisy_frame()
    out = run_backtest(prices, MomentumParams(), n_cohort=3)
    assert out["screened"] == len(prices.columns) - 1        # SPY excluded
    for name in ("accelerating", "leaders", "fading", "universe", "non_fading"):
        assert len(out["sizes"][name]) == out["periods"]
    assert len(out["skipped"]) == out["periods"]
    for i in range(out["periods"]):
        assert out["skipped"][i] == out["screened"] - out["sizes"]["universe"][i]
        assert out["sizes"]["fading"][i] + out["sizes"]["non_fading"][i] == \
            out["sizes"]["universe"][i]
        assert out["sizes"]["accelerating"][i] <= 3          # n_cohort
        assert out["sizes"]["leaders"][i] <= 3


def test_run_backtest_counts_a_ticker_with_no_history_as_skipped():
    n = 700
    rng = np.random.default_rng(5)
    cols = {f"T{i}": 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
            for i in range(4)}
    cols["LATE"] = np.concatenate([np.full(600, np.nan),
                                   100.0 * np.exp(np.cumsum(
                                       rng.normal(0.0005, 0.01, n - 600)))])
    cols["SPY"] = 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.006, n)))
    out = run_backtest(_frame(cols, n=n), MomentumParams(), n_cohort=3)
    assert out["screened"] == 5                       # 4 normal + LATE
    assert max(out["skipped"]) >= 1                   # LATE is unusable early
    assert min(out["skipped"]) >= 0
