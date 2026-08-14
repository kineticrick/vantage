import pytest
from vantage.momentum import (WINDOW_MONTHS, MomentumParams, Trajectory,
                              annualize, classify, sector_breadth)

def _m(r1, r3, r6, r12):
    return {"ret_1m": r1, "ret_3m": r3, "ret_6m": r6, "ret_12m": r12}

def test_annualize_scales_windows():
    assert annualize(0.30, 3) == pytest.approx(1.30 ** 4 - 1)
    assert annualize(0.10, 6) == pytest.approx(1.10 ** 2 - 1)
    assert annualize(0.40, 12) == pytest.approx(0.40)
    assert annualize(None, 3) is None

def test_annualize_guards_total_loss():
    # (1+r) <= 0 would raise or go complex under a fractional exponent
    assert annualize(-1.0, 3) is None
    assert annualize(-1.5, 3) is None

def test_accelerating_when_recent_pace_exceeds_long_run():
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.5)
    assert t.label == "accelerating"
    assert t.pace_3m == pytest.approx(1.30 ** 4 - 1)
    assert t.pace_12m == pytest.approx(0.40)
    assert t.score == pytest.approx((1.30 ** 4 - 1 - 0.40) / 0.5)

def test_fading_requires_both_3m_and_6m_decay():
    t = classify(_m(-0.02, 0.02, 0.10, 0.60), volatility=0.4)
    assert t.label == "fading"

def test_3m_decay_alone_is_not_fading():
    # 3m pace below the 12m pace, but 6m pace well above it -> not fading
    t = classify(_m(-0.02, 0.05, 0.60, 0.50), volatility=0.4)
    assert t.label == "steady"

def test_one_month_decline_alone_never_fades():
    # a weak month against a strong, still-accelerating 3m/6m
    t = classify(_m(-0.06, 0.40, 0.30, 0.35), volatility=0.5)
    assert t.label != "fading"

def test_near_zero_long_run_base_does_not_explode():
    # regression: a ratio formulation scored this kind of name at 200+
    t = classify(_m(0.09, 0.29, 0.20, 0.008), volatility=0.4)
    assert t.score is not None
    assert abs(t.score) < 20

def test_recovering_loser_is_not_accelerating():
    # down on the year, merely less bad lately -> not promise
    t = classify(_m(0.02, 0.06, -0.15, -0.25), volatility=0.4)
    assert t.label != "accelerating"

def test_weak_recent_return_fails_the_strength_gate():
    # gap > 0 (pace_3m > pace_12m) and every other gate passes; only the raw
    # ret_3m (0.03) sits below min_recent_return (0.05), so this must be the
    # thing standing between this name and "accelerating".
    t = classify(_m(0.01, 0.03, 0.06, 0.05), volatility=0.4)
    assert t.label != "accelerating"

def test_collapsing_month_fails_the_soft_floor():
    t = classify(_m(-0.30, 0.30, 0.35, 0.40), volatility=0.5)
    assert t.label != "accelerating"

def test_volatility_normalization_orders_equal_gaps():
    calm = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.2)
    wild = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.8)
    assert calm.score > wild.score
    assert calm.label == wild.label == "accelerating"

def test_benchmark_subtracts_market_pace():
    raw = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.5)
    rel = classify(_m(0.05, 0.30, 0.35, 0.40),
                   benchmark_metrics=_m(0.02, 0.10, 0.18, 0.25), volatility=0.5)
    assert rel.score < raw.score
    assert rel.benchmark_adjusted is True
    assert raw.benchmark_adjusted is False

def test_missing_window_is_unknown_not_an_exception():
    t = classify({"ret_1m": 0.05, "ret_3m": 0.30}, volatility=0.5)
    assert t.label == "unknown" and t.score is None

def test_zero_or_missing_volatility_yields_no_score_but_keeps_label():
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.0)
    assert t.score is None
    assert t.label in {"accelerating", "steady", "fading"}
    assert classify(_m(0.05, 0.30, 0.35, 0.40), volatility=None).score is None

def test_volatility_can_be_disabled():
    p = MomentumParams(use_volatility=False)
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=None, params=p)
    assert t.score == pytest.approx(1.30 ** 4 - 1 - 0.40)

def test_disagrees_flags_accelerating_far_below_its_high():
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.5, drawdown=-0.35)
    assert t.label == "accelerating" and t.disagrees is True

def test_disagrees_flags_fading_at_its_high():
    t = classify(_m(-0.02, 0.02, 0.10, 0.60), volatility=0.4, drawdown=-0.01)
    assert t.label == "fading" and t.disagrees is True

def test_no_disagreement_when_story_is_consistent():
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.5, drawdown=-0.02)
    assert t.disagrees is False

def test_classify_never_raises_on_garbage():
    for bad in ({}, {"ret_3m": None, "ret_12m": None}, {"ret_1m": "x"}):
        assert classify(bad).label == "unknown"

def test_recent_window_is_configurable():
    p = MomentumParams(recent_window="ret_6m")
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.5, params=p)
    assert t.score == pytest.approx((1.35 ** 2 - 1 - 0.40) / 0.5)

def test_non_numeric_volatility_yields_no_score_not_an_exception():
    # score becomes unusable, but the label is still fully computable.
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility="abc")
    assert t.score is None
    assert t.label == "accelerating"

def test_non_numeric_drawdown_disables_disagreement_not_an_exception():
    # disagreement becomes unusable, but the label is still fully computable.
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.5, drawdown="deep")
    assert t.disagrees is False
    assert t.label == "accelerating"

def test_unknown_recent_window_is_unusable_not_an_exception():
    p = MomentumParams(recent_window="ret_9m")
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.5, params=p)
    assert t.label == "unknown" and t.score is None

def test_strength_gate_boundary_is_inclusive():
    # ret_3m exactly at min_recent_return (0.05) still clears the gate.
    t = classify(_m(0.02, 0.05, 0.15, 0.10), volatility=0.4)
    assert t.label == "accelerating"

def test_soft_floor_boundary_is_inclusive():
    # ret_1m exactly at min_1m_return (-0.15) still clears the soft floor.
    t = classify(_m(-0.15, 0.10, 0.08, 0.05), volatility=0.4)
    assert t.label == "accelerating"

import numpy as np
import pandas as pd
from vantage.momentum import (realized_volatility, drawdown_from_high,
                              single_day_share)

def _series(values):
    idx = pd.date_range("2025-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx, dtype="float64")

def test_realized_volatility_of_constant_growth_is_zero():
    prices = _series([100.0 * (1.01 ** i) for i in range(200)])
    assert realized_volatility(prices) == pytest.approx(0.0, abs=1e-9)

def test_realized_volatility_scales_with_dispersion():
    rng = np.random.default_rng(0)
    calm = _series(100.0 * np.exp(np.cumsum(rng.normal(0, 0.005, 200))))
    wild = _series(100.0 * np.exp(np.cumsum(rng.normal(0, 0.020, 200))))
    assert realized_volatility(wild) > realized_volatility(calm)

def test_realized_volatility_annualizes():
    # daily log-return stdev s -> annualized s * sqrt(252)
    rng = np.random.default_rng(1)
    daily = rng.normal(0, 0.01, 5000)
    prices = _series(100.0 * np.exp(np.cumsum(daily)))
    v = realized_volatility(prices, lookback=5000)
    assert v == pytest.approx(np.std(daily, ddof=1) * np.sqrt(252), rel=0.05)

def test_realized_volatility_short_series_is_none():
    assert realized_volatility(_series([100.0, 101.0])) is None

def test_drawdown_from_high_measures_distance_below_peak():
    prices = _series([100.0] * 10 + [200.0] + [150.0])
    assert drawdown_from_high(prices) == pytest.approx(-0.25)

def test_drawdown_from_high_at_the_high_is_zero():
    prices = _series([100.0, 120.0, 150.0])
    assert drawdown_from_high(prices) == pytest.approx(0.0)

def test_drawdown_from_high_empty_is_none():
    assert drawdown_from_high(_series([])) is None

def test_single_day_share_of_one_gap_move():
    # one +10% session, flat either side: that day IS the whole move
    prices = _series([100.0] * 5 + [110.0] * 5)
    assert single_day_share(prices) == pytest.approx(1.0, rel=1e-6)

def test_single_day_share_exceeds_one_when_a_day_beats_the_net_move():
    # +20% in a day, then giving half back: the day outran the net result
    prices = _series([100.0] * 3 + [120.0] + [110.0] * 3)
    assert single_day_share(prices) > 1.0

def test_single_day_share_flat_window_is_none():
    assert single_day_share(_series([100.0] * 10)) is None

def test_realized_volatility_interior_zero_price_is_none():
    prices = _series([100.0, 100.0, 0.0, 100.0, 100.0] * 20)
    assert realized_volatility(prices) is None

def test_realized_volatility_interior_negative_price_is_none():
    prices = _series([100.0, 100.0, -5.0, 100.0, 100.0] * 20)
    assert realized_volatility(prices) is None

def test_single_day_share_interior_zero_price_is_none():
    prices = _series([100.0, 100.0, 0.0, 100.0, 100.0] * 20)
    assert single_day_share(prices) is None

def test_single_day_share_interior_negative_price_is_none():
    prices = _series([100.0, 100.0, -5.0, 100.0, 100.0] * 20)
    assert single_day_share(prices) is None

def _traj(label, score):
    return Trajectory(label=label, score=score)

def test_sector_breadth_computes_shares_and_median():
    trajectories = {
        "AAA": _traj("accelerating", 2.0),
        "BBB": _traj("accelerating", 4.0),
        "CCC": _traj("fading", -1.0),
        "DDD": _traj("steady", 0.5),
    }
    sectors = {"AAA": "Tech", "BBB": "Tech", "CCC": "Tech", "DDD": "Energy"}
    out = sector_breadth(trajectories, sectors)
    assert out["Tech"]["count"] == 3
    assert out["Tech"]["accelerating_share"] == pytest.approx(2 / 3)
    assert out["Tech"]["fading_share"] == pytest.approx(1 / 3)
    assert out["Tech"]["median_score"] == pytest.approx(2.0)   # median of 2, 4, -1
    assert out["Energy"]["count"] == 1
    assert out["Energy"]["accelerating_share"] == pytest.approx(0.0)

def test_sector_breadth_ignores_unknown_and_missing_sector():
    trajectories = {"AAA": _traj("accelerating", 1.0), "ZZZ": _traj("unknown", None)}
    out = sector_breadth(trajectories, {"AAA": "Tech"})   # ZZZ has no sector
    assert set(out) == {"Tech"}
    assert out["Tech"]["count"] == 1

def test_sector_breadth_handles_all_scoreless_sector():
    trajectories = {"AAA": _traj("steady", None), "BBB": _traj("steady", None)}
    out = sector_breadth(trajectories, {"AAA": "Utilities", "BBB": "Utilities"})
    assert out["Utilities"]["median_score"] is None
    assert out["Utilities"]["count"] == 2

def test_sector_breadth_empty_input():
    assert sector_breadth({}, {}) == {}
