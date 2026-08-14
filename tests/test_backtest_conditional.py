import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from backtest_conditional import (BREADTH_KEYS, COHORTS, PAIRS,  # noqa: E402
                                  classify_at, conditional_cohorts,
                                  load_sector_map, price_arrays, rank_sectors,
                                  run_backtest, run_period, sector_members)
from vantage.momentum import MomentumParams, Trajectory  # noqa: E402


def _leader(ret_12m, score, label="steady"):
    """A (metrics, Trajectory) pair as classify_at would produce one."""
    return ({"ret_1m": 0.0, "ret_3m": 0.0, "ret_6m": 0.0, "ret_12m": ret_12m},
            Trajectory(label=label, score=score))


def _frame(cols, n):
    idx = pd.date_range("2016-01-04", periods=n, freq="B")
    return pd.DataFrame(cols, index=idx)


# --- sector map loading -----------------------------------------------------

def test_load_sector_map_flattens_the_cache_shape(tmp_path):
    p = tmp_path / "sectors.json"
    p.write_text(json.dumps({
        "AAA": {"sector": "Technology", "name": "A Co", "fetched": "2026-08-13"},
        "BBB": {"sector": "Energy"},
    }), encoding="utf-8")
    assert load_sector_map(p) == {"AAA": "Technology", "BBB": "Energy"}


def test_load_sector_map_drops_entries_without_a_usable_sector(tmp_path):
    # sector_breadth buckets on a truthy string; a None or "" would otherwise
    # become its own silent bucket keyed on a falsy value.
    p = tmp_path / "sectors.json"
    p.write_text(json.dumps({"AAA": {"sector": "Energy"}, "BBB": {"sector": None},
                             "CCC": {"sector": ""}, "DDD": {"name": "no sector"}}),
                 encoding="utf-8")
    assert load_sector_map(p) == {"AAA": "Energy"}


# --- experiment 1: conditional cohorts --------------------------------------

def test_conditional_cohorts_conditions_on_the_12m_rank_then_ranks_by_score():
    # 40 names; ret_12m descending with ticker index, so the top 30 are T0..T29.
    # Score runs the OTHER way inside that set, so the hi-score half must be
    # the *lowest* 12m ranks of the leaders -- proving the second sort is by
    # score and not a leftover of the first.
    classified = {f"T{i}": _leader(1.0 - i * 0.01, float(i)) for i in range(40)}
    cohorts, diag = conditional_cohorts(classified)
    assert cohorts["leaders_top30"] == [f"T{i}" for i in range(30)]
    assert cohorts["leaders_hi_traj"] == [f"T{i}" for i in range(29, 14, -1)]
    assert cohorts["leaders_lo_traj"] == [f"T{i}" for i in range(14, -1, -1)]
    assert diag == {"leaders": 30, "dropped": 0, "cohort_n": 15}


def test_conditional_cohorts_halves_are_disjoint_and_cover_the_ranked_set():
    classified = {f"T{i}": _leader(1.0 - i * 0.01, float(30 - i)) for i in range(40)}
    cohorts, _ = conditional_cohorts(classified)
    hi, lo = cohorts["leaders_hi_traj"], cohorts["leaders_lo_traj"]
    assert len(hi) == len(lo) == 15
    assert not set(hi) & set(lo)
    assert set(hi) | set(lo) == set(cohorts["leaders_top30"])


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf")])
def test_conditional_cohorts_drops_unusable_scores_and_counts_them(bad):
    # score is a SORT KEY: nan makes the order undefined and inf sorts to the
    # top. Both must be excluded from the ranking, not ranked badly -- and the
    # count must be reported, since a large one means the halves are no longer
    # drawn from a full top 30.
    classified = {f"T{i}": _leader(1.0 - i * 0.01, float(i)) for i in range(40)}
    classified["T5"] = _leader(0.95, bad)
    cohorts, diag = conditional_cohorts(classified)
    assert diag["dropped"] == 1
    assert "T5" not in cohorts["leaders_hi_traj"] + cohorts["leaders_lo_traj"]
    assert "T5" in cohorts["leaders_top30"]        # still a leader, just unranked


def test_conditional_cohorts_shrink_rather_than_overlap_when_scores_are_dropped():
    # 21 rankable leaders out of 30. A naive scored[:15] / scored[-15:] would
    # put 9 names in BOTH halves, driving the measured difference toward zero
    # while still looking like two 15-name cohorts.
    classified = {f"T{i}": _leader(1.0 - i * 0.01, float(i)) for i in range(40)}
    for i in range(9):
        classified[f"T{i}"] = _leader(1.0 - i * 0.01, None)
    cohorts, diag = conditional_cohorts(classified)
    assert diag["dropped"] == 9
    assert diag["cohort_n"] == 10                  # 21 // 2
    hi, lo = cohorts["leaders_hi_traj"], cohorts["leaders_lo_traj"]
    assert len(hi) == len(lo) == 10
    assert not set(hi) & set(lo)


def test_conditional_cohorts_are_empty_when_nothing_is_rankable():
    classified = {f"T{i}": _leader(1.0 - i * 0.01, None) for i in range(40)}
    cohorts, diag = conditional_cohorts(classified)
    assert diag["dropped"] == 30 and diag["cohort_n"] == 0
    assert cohorts["leaders_hi_traj"] == [] and cohorts["leaders_lo_traj"] == []


def test_conditional_cohorts_label_split_is_the_secondary_cross_check():
    # The label split covers the top 30 only, and its sizes vary by date --
    # unlike the score split it is not two equal halves, which is why it is a
    # cross-check rather than the primary.
    classified = {}
    for i in range(40):
        label = "accelerating" if i < 4 else ("fading" if i < 9 else "steady")
        classified[f"T{i}"] = _leader(1.0 - i * 0.01, float(i), label=label)
    cohorts, _ = conditional_cohorts(classified)
    assert cohorts["leaders_accelerating"] == ["T0", "T1", "T2", "T3"]
    assert cohorts["leaders_fading"] == [f"T{i}" for i in range(4, 9)]


def test_conditional_cohorts_ignore_names_outside_the_top_30():
    classified = {f"T{i}": _leader(1.0 - i * 0.01, 100.0 - i, label="accelerating")
                  for i in range(40)}
    cohorts, _ = conditional_cohorts(classified)
    # Every name is labeled "accelerating" and every name carries a finite
    # score, so only the top-30 conditioning keeps T30..T39 out of the cohorts.
    for name in ("leaders_hi_traj", "leaders_lo_traj", "leaders_accelerating"):
        assert not set(cohorts[name]) & {f"T{i}" for i in range(30, 40)}


# --- experiment 2: sector ranking -------------------------------------------

def _sector_fixture(shares):
    """Build classified names + a sector map realizing a given accel share."""
    classified, sector_map = {}, {}
    for sector, (n, n_accel) in shares.items():
        for i in range(n):
            t = f"{sector[:3].upper()}{i}"
            label = "accelerating" if i < n_accel else "steady"
            classified[t] = _leader(0.5, float(i), label=label)
            sector_map[t] = sector
    return classified, sector_map


def test_rank_sectors_orders_by_the_requested_statistic():
    classified, sector_map = _sector_fixture({
        "S1": (20, 18), "S2": (20, 14), "S3": (20, 12), "S4": (20, 8),
        "S5": (20, 4), "S6": (20, 1), "S7": (20, 10),
    })
    hi, lo, breadth = rank_sectors(classified, sector_map, "accelerating_share")
    # shares: S1 .90, S2 .70, S3 .60, S7 .50, S4 .40, S5 .20, S6 .05
    assert hi == ["S1", "S2", "S3"]
    assert lo == ["S4", "S5", "S6"]
    assert breadth["S1"]["accelerating_share"] == pytest.approx(0.9)


def test_rank_sectors_excludes_unknown_and_undersized_sectors():
    classified, sector_map = _sector_fixture({
        "S1": (20, 18), "S2": (20, 14), "S3": (20, 12), "S4": (20, 8),
        "S5": (20, 4), "S6": (20, 1),
        "Unknown": (20, 20),      # would top the ranking if not excluded
        "Tiny": (9, 9),           # 9 < MIN_SECTOR_NAMES, would also top it
    })
    hi, lo, _ = rank_sectors(classified, sector_map, "accelerating_share")
    assert hi == ["S1", "S2", "S3"]
    assert "Unknown" not in hi + lo and "Tiny" not in hi + lo


def test_rank_sectors_returns_nothing_when_top_and_bottom_would_overlap():
    # 5 eligible sectors cannot yield a disjoint top 3 and bottom 3.
    classified, sector_map = _sector_fixture({
        "S1": (20, 18), "S2": (20, 14), "S3": (20, 12), "S4": (20, 8),
        "S5": (20, 4),
    })
    hi, lo, _ = rank_sectors(classified, sector_map, "accelerating_share")
    assert hi == [] and lo == []


def test_rank_sectors_breaks_ties_on_name_so_runs_are_reproducible():
    classified, sector_map = _sector_fixture({s: (20, 10) for s in
                                              ["S6", "S3", "S1", "S5", "S2", "S4"]})
    hi, lo, _ = rank_sectors(classified, sector_map, "accelerating_share")
    assert hi == ["S1", "S2", "S3"] and lo == ["S4", "S5", "S6"]


def test_rank_sectors_supports_median_score_as_a_second_ordering():
    classified, sector_map = {}, {}
    for rank, sector in enumerate(["S1", "S2", "S3", "S4", "S5", "S6"]):
        for i in range(20):
            t = f"{sector}_{i}"
            classified[t] = _leader(0.5, float(-rank))
            sector_map[t] = sector
    hi, lo, breadth = rank_sectors(classified, sector_map, "median_score")
    assert hi == ["S1", "S2", "S3"] and lo == ["S4", "S5", "S6"]
    assert breadth["S1"]["median_score"] == pytest.approx(0.0)


def test_sector_members_takes_every_classified_name_in_the_sector():
    classified, sector_map = _sector_fixture({"S1": (4, 2), "S2": (3, 0)})
    members = sector_members(classified, sector_map, ["S1"])
    assert sorted(members) == ["S10", "S11", "S12", "S13"]


def test_sector_members_excludes_unlabeled_names_matching_the_breadth_count():
    # sector_breadth skips label="unknown" when it computes the share, so a
    # cohort that included them would not be the set that was ranked.
    classified, sector_map = _sector_fixture({"S1": (4, 2)})
    classified["S1X"] = _leader(0.5, None, label="unknown")
    sector_map["S1X"] = "S1"
    assert "S1X" not in sector_members(classified, sector_map, ["S1"])


# --- end to end --------------------------------------------------------------

def _noisy_prices(n=900, n_tickers=80, seed=11):
    rng = np.random.default_rng(seed)
    cols = {f"T{i}": 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, n)))
            for i in range(n_tickers)}
    cols["SPY"] = 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.006, n)))
    return _frame(cols, n)


def _noisy_sector_map(n_tickers=80, n_sectors=8):
    return {f"T{i}": f"S{i % n_sectors}" for i in range(n_tickers)}


def test_classify_at_screens_the_same_way_the_parent_harness_does():
    prices = _noisy_prices()
    arrays = price_arrays(prices)
    classified = classify_at(arrays, 500, MomentumParams())
    assert "SPY" not in classified                    # benchmark excluded
    assert 0 < len(classified) <= 80
    metrics, traj = next(iter(classified.values()))
    assert set(metrics) == {"ret_1m", "ret_3m", "ret_6m", "ret_12m"}
    assert traj.label in {"accelerating", "steady", "fading", "unknown"}


def test_run_period_emits_every_cohort_and_disjoint_breadth_halves():
    prices = _noisy_prices()
    out = run_period(price_arrays(prices), 500, MomentumParams(),
                     _noisy_sector_map())
    for name in COHORTS:
        assert name in out
    for h in (21, 63, 126):
        assert set(out["forward"][h]) == set(COHORTS)
    assert not set(out["hi_breadth_accel"]) & set(out["lo_breadth_accel"])
    assert not set(out["hi_breadth_score"]) & set(out["lo_breadth_score"])
    assert not set(out["leaders_hi_traj"]) & set(out["leaders_lo_traj"])
    for key in BREADTH_KEYS:
        assert not set(out["sectors_used"][key]["hi"]) & \
            set(out["sectors_used"][key]["lo"])


def test_run_backtest_reports_paired_stats_for_every_registered_pair():
    out = run_backtest(_noisy_prices(), MomentumParams(), _noisy_sector_map())
    assert out["periods"] > 0
    for h in (21, 63, 126):
        assert set(out["paired"][h]) == {f"{a}-{b}" for a, b in PAIRS}
        for st in out["paired"][h].values():
            assert set(st) == {"median_diff", "mean_diff", "std_diff", "wins",
                               "ties", "periods"}
            assert 0 <= st["wins"] <= st["periods"] <= out["periods"]


def test_run_backtest_never_emits_an_aggregate_cross_cohort_spread():
    # The parent study published the difference of two separately-aggregated
    # medians three times. This harness must not make that number available at
    # all -- pairing is the only cross-cohort route it offers.
    out = run_backtest(_noisy_prices(), MomentumParams(), _noisy_sector_map())
    assert "spread_vs_leaders" not in out
    assert all("spread" not in k for k in out)


def test_run_backtest_paired_mean_matches_the_unpaired_mean_difference():
    # mean is linear, so mean(a) - mean(b) == mean(a - b). An independent route
    # to the same number, verifying the pairing code itself.
    out = run_backtest(_noisy_prices(), MomentumParams(), _noisy_sector_map())
    for h in (21, 63, 126):
        c = out["cohorts"][h]
        for a, b in PAIRS:
            if c[a]["periods"] != out["periods"] or c[b]["periods"] != out["periods"]:
                continue
            assert out["paired"][h][f"{a}-{b}"]["mean_diff"] == \
                pytest.approx(c[a]["mean"] - c[b]["mean"])


def test_run_backtest_reports_sizes_drops_and_per_date_series():
    out = run_backtest(_noisy_prices(), MomentumParams(), _noisy_sector_map())
    assert out["screened"] == 80                       # SPY excluded
    assert len(out["dropped"]) == out["periods"]
    assert all(0 <= d <= 30 for d in out["dropped"])
    for name in COHORTS:
        assert len(out["sizes"][name]) == out["periods"]
    for i in range(out["periods"]):
        assert out["skipped"][i] == out["screened"] - out["sizes"]["universe"][i]
        assert out["sizes"]["leaders_top30"][i] <= 30
        assert out["sizes"]["leaders_hi_traj"][i] == out["sizes"]["leaders_lo_traj"][i]
    for h in (21, 63, 126):
        for name in COHORTS:
            assert len(out["per_date"][h][name]) == out["periods"]


def test_run_backtest_on_short_history_reports_zero_periods():
    prices = _noisy_prices(n=200, n_tickers=5)
    out = run_backtest(prices, MomentumParams(), _noisy_sector_map(5, 2))
    assert out["periods"] == 0
