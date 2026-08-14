import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from backtest_core import (MAX_PLAUSIBLE_RETURN, WINDOW_DAYS,
                           formation_positions, forward_return, metrics_at,
                           paired_stats)

def _ramp(n, daily):
    return 100.0 * np.cumprod(np.full(n, 1.0 + daily))

def test_windows_and_guard_are_the_published_values():
    assert WINDOW_DAYS == {"ret_1m": 21, "ret_3m": 63, "ret_6m": 126, "ret_12m": 252}
    assert MAX_PLAUSIBLE_RETURN == 10.0

def test_formation_positions_boundaries():
    pos = formation_positions(700, lookback=252, forward=126, step=21)
    assert pos[0] == 252
    assert max(pos) <= 700 - 126 - 1
    assert formation_positions(200, lookback=252, forward=126) == []

def test_metrics_at_measures_backwards():
    vals = _ramp(400, 0.001)
    m = metrics_at(vals, 399)
    assert set(m) == set(WINDOW_DAYS)
    assert m["ret_12m"] == pytest.approx(1.001 ** 252 - 1, rel=1e-9)

def test_metrics_at_returns_none_without_history():
    assert metrics_at(_ramp(100, 0.001), 99) is None

def test_forward_return_looks_ahead_and_stops_at_the_end():
    vals = _ramp(400, 0.002)
    assert forward_return(vals, 100, 63) == pytest.approx(1.002 ** 63 - 1, rel=1e-9)
    assert forward_return(vals, 399, 63) is None

def test_paired_stats_pairs_per_period():
    periods = [{"forward": {21: {"a": 0.10, "b": 0.04}}},
               {"forward": {21: {"a": 0.02, "b": 0.05}}},
               {"forward": {21: {"a": 0.06, "b": 0.01}}}]
    out = paired_stats(periods, 21, "a", "b")
    assert out["periods"] == 3
    assert out["wins"] == 2
    assert out["median_diff"] == pytest.approx(0.05)

def test_paired_stats_skips_periods_missing_either_side():
    periods = [{"forward": {21: {"a": 0.10, "b": None}}},
               {"forward": {21: {"a": 0.02, "b": 0.05}}}]
    assert paired_stats(periods, 21, "a", "b")["periods"] == 1

def test_studies_still_expose_the_primitives():
    # backtest_momentum re-exports them, so existing test modules that import
    # from it keep working after the move.
    import backtest_momentum as bm
    for name in ("WINDOW_DAYS", "formation_positions", "metrics_at",
                 "forward_return", "paired_stats"):
        assert hasattr(bm, name), name
