"""The published findings must still reproduce.

Extracting shared primitives is exactly the change that could alter a published
result with nothing noticing: both study suites run on synthetic fixtures, and
the real numbers live only in docs/superpowers/findings/ and in git-ignored
JSON. This runs the momentum backtest against the real snapshot and asserts the
headline figures from
docs/superpowers/findings/2026-08-13-momentum-backtest.md.

Skips when cache/history/ is absent — that directory is git-ignored, so a fresh
clone has no snapshot. It must skip, never silently pass.
"""
import glob
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

SNAPSHOTS = sorted(glob.glob(str(REPO / "cache" / "history" / "prices-*.parquet")))
needs_snapshot = pytest.mark.skipif(
    not SNAPSHOTS, reason="no price snapshot in cache/history (git-ignored)")


@pytest.fixture(scope="module")
def baseline():
    import pandas as pd
    from backtest_momentum import run_backtest
    from vantage.momentum import MomentumParams
    prices = pd.read_parquet(SNAPSHOTS[-1]).sort_index()
    return run_backtest(prices, MomentumParams())


@needs_snapshot
def test_formation_date_count(baseline):
    assert baseline["periods"] == 102


@needs_snapshot
def test_published_aggregate_spreads(baseline):
    # "the 12-month-leader cohort outperformed the accelerating cohort by
    #  -0.37 percentage points at 1 month, -3.81pp at 3 months, -3.93pp at
    #  6 months"  — findings §1. Note: horizon keys are ints from the
    #  function, strings only after json.dumps.
    spreads = baseline["spread_vs_leaders"]
    assert spreads[21] == pytest.approx(-0.0037, abs=5e-5)
    assert spreads[63] == pytest.approx(-0.0381, abs=5e-5)
    assert spreads[126] == pytest.approx(-0.0393, abs=5e-5)


@needs_snapshot
def test_published_paired_medians(baseline):
    # The paired figures are a different statistic from the aggregate spreads
    # above and are published separately. Pinning both is deliberate: a change
    # that made them agree would be as much a regression as one that moved
    # either. Median diffs from table at findings:222-224.
    paired = baseline["paired"]
    expected = {21: -0.0121, 63: -0.0141, 126: -0.0531}
    for horizon, med in expected.items():
        cell = paired[horizon]["accelerating-leaders"]
        assert cell["median_diff"] == pytest.approx(med, abs=5e-5)
        assert cell["periods"] == 102

    # Win counts derived directly from published loss counts (findings:222-224).
    # 21d: findings says first-wins 42/102 (published directly at baseline output).
    assert paired[21]["accelerating-leaders"]["wins"] == 42
    # 63d: findings says 56/102 losses + 2 ties, so 102 - 56 - 2 = 44 wins.
    assert paired[63]["accelerating-leaders"]["wins"] == 44
    assert paired[63]["accelerating-leaders"]["ties"] == 2
    # 126d: findings says 64/102 losses (ties omitted means 0), so 102 - 64 = 38 wins.
    assert paired[126]["accelerating-leaders"]["wins"] == 38
    assert paired[126]["accelerating-leaders"]["ties"] == 0


@needs_snapshot
def test_the_headline_conclusion_still_holds(baseline):
    # The finding's entire claim: the acceleration score loses to the 12-month
    # rank at every horizon, on both statistics.
    assert all(v < 0 for v in baseline["spread_vs_leaders"].values())
    assert all(baseline["paired"][h]["accelerating-leaders"]["median_diff"] < 0
               for h in (21, 63, 126))
