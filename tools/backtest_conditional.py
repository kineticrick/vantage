"""Two follow-up questions the acceleration backtest did not answer.

The parent study (docs/superpowers/findings/2026-08-13-momentum-backtest.md)
asked "does the acceleration score beat the trailing 12-month rank across the
whole market" and answered no, unanimously, across 36 paired point estimates.
It never asked either of these:

1. **Conditional.** *Given* a name is already a 12-month leader, does its
   trajectory tell you which leaders do better? Take the top 30 by trailing
   12-month return, rank those 30 by trajectory score, and race the top 15
   against the bottom 15.
2. **Sector breadth.** `sector_breadth()` was built and never validated. Rank
   sectors by their accelerating share (and, separately, by median score), and
   race every name in the top 3 sectors against every name in the bottom 3.

Both designs were pre-registered in full before any result was seen; nothing
here was altered after looking at an outcome.

Every cross-cohort comparison is paired per formation date, via the parent
harness's `paired_stats`. A difference of two separately-aggregated medians is
NOT the median of the per-date differences -- the parent study published that
error three separate times, and its central methodological lesson is to never
compare aggregates. This module computes no aggregate difference at all.

Run:  .venv/bin/python tools/backtest_conditional.py
Tooling only.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tools"))

from backtest_core import (formation_positions, forward_return,  # noqa: E402
                           metrics_at, paired_stats)
from vantage.momentum import (MomentumParams, classify, drawdown_from_high,  # noqa: E402
                              realized_volatility, sector_breadth)

TOP_N_LEADERS = 30      # the conditioning set: "already a 12-month leader"
COHORT_N = 15           # half of it, per pre-registered design
N_SECTORS = 3           # top-3 / bottom-3 by breadth
MIN_SECTOR_NAMES = 10   # a sector with fewer classified names is not ranked
EXCLUDED_SECTORS = ("Unknown",)

# Ranking keys for experiment 2: two independent orderings of the same idea.
BREADTH_KEYS = ("accelerating_share", "median_score")


def load_sector_map(path) -> dict:
    """`{TICKER: {"sector": ...}}` on disk -> the flat `{TICKER: sector}` that
    `sector_breadth` wants. Entries without a usable sector string are dropped.

    CAVEAT, restated wherever this is used: these are *today's* sector labels,
    applied to historical formation dates. Sector membership is fairly stable,
    but this is an anachronism in the same family as the parent study's
    survivorship bias.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for ticker, rec in (raw or {}).items():
        sector = rec.get("sector") if isinstance(rec, dict) else rec
        if isinstance(sector, str) and sector:
            out[ticker] = sector
    return out


def price_arrays(prices) -> dict:
    """Column -> float64 array, computed once instead of per formation date."""
    return {c: prices[c].to_numpy(dtype="float64") for c in prices.columns}


def classify_at(arrays, pos, params, benchmark="SPY") -> dict:
    """Every usable ticker at one formation date -> (metrics, Trajectory).

    Same screen as the parent harness's `run_period`: a ticker whose
    `metrics_at` fails on any of the four trailing windows is dropped entirely.
    """
    bench_metrics = metrics_at(arrays[benchmark], pos) if benchmark in arrays else None
    out = {}
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
        out[ticker] = (m, t)
    return out


def _usable_score(t):
    return t.score is not None and np.isfinite(t.score)


def conditional_cohorts(classified, top_n=TOP_N_LEADERS, cohort_n=COHORT_N) -> tuple:
    """Experiment 1: split the 12-month leaders by trajectory score.

    Returns `(cohorts, diagnostics)`. Leaders whose score is None or non-finite
    are excluded from the ranking and counted in `diagnostics["dropped"]` -- if
    that count is ever large, the two halves are no longer drawn from a full
    top-`top_n` and the result is qualified accordingly.

    When drops leave fewer than `2 * cohort_n` rankable leaders, both halves
    shrink to `len(scored) // 2` so that hi and lo never share a member. A
    naive `scored[:15]` / `scored[-15:]` would overlap silently and drive the
    measured difference toward zero.
    """
    leaders = sorted(classified.items(), key=lambda kv: -kv[1][0]["ret_12m"])[:top_n]
    scored = [(t, r[1].score) for t, r in leaders if _usable_score(r[1])]
    scored.sort(key=lambda kv: -kv[1])
    n = min(cohort_n, len(scored) // 2)
    cohorts = {
        "leaders_top30": [t for t, _ in leaders],
        "leaders_hi_traj": [t for t, _ in scored[:n]],
        "leaders_lo_traj": [t for t, _ in scored[len(scored) - n:]] if n else [],
        # Secondary cross-check: the same 30 split by LABEL rather than by
        # score rank. Sizes vary per date by construction and are reported.
        "leaders_accelerating": [t for t, r in leaders if r[1].label == "accelerating"],
        "leaders_fading": [t for t, r in leaders if r[1].label == "fading"],
    }
    diagnostics = {"leaders": len(leaders), "dropped": len(leaders) - len(scored),
                   "cohort_n": n}
    return cohorts, diagnostics


def rank_sectors(classified, sector_map, key, n_sectors=N_SECTORS,
                 min_names=MIN_SECTOR_NAMES, excluded=EXCLUDED_SECTORS) -> tuple:
    """Experiment 2: order sectors by one breadth statistic. -> (hi, lo, breadth).

    Sectors in `excluded`, sectors with fewer than `min_names` classified
    names, and sectors whose statistic is None are not ranked at all. If fewer
    than `2 * n_sectors` sectors survive, the top and bottom slices would share
    members, so both come back empty rather than overlapping.

    Ties break on sector name so a run is reproducible.
    """
    breadth = sector_breadth({t: r[1] for t, r in classified.items()}, sector_map)
    eligible = {s: b for s, b in breadth.items()
                if s not in excluded and b["count"] >= min_names
                and b.get(key) is not None}
    ranked = sorted(eligible.items(), key=lambda kv: (-kv[1][key], kv[0]))
    if len(ranked) < 2 * n_sectors:
        return [], [], breadth
    return ([s for s, _ in ranked[:n_sectors]],
            [s for s, _ in ranked[len(ranked) - n_sectors:]], breadth)


def sector_members(classified, sector_map, sectors) -> list:
    """Every classified name in `sectors`. Unlabeled names are excluded, to
    match what `sector_breadth` counted when it ranked the sector."""
    wanted = set(sectors)
    return [t for t, r in classified.items()
            if sector_map.get(t) in wanted and r[1].label != "unknown"]


COHORTS = ("universe", "leaders_top30", "leaders_hi_traj", "leaders_lo_traj",
           "leaders_accelerating", "leaders_fading",
           "hi_breadth_accel", "lo_breadth_accel",
           "hi_breadth_score", "lo_breadth_score")

# Experiment 1 is the first four; experiment 2 is the last six. Every one is a
# hypothesis test and every one is counted in the finding's multiple-
# comparisons tally -- 10 pairs x 3 horizons = 30 tests in this study alone.
PAIRS = (
    ("leaders_hi_traj", "leaders_lo_traj"),          # E1 primary
    ("leaders_hi_traj", "leaders_top30"),            # E1 context
    ("leaders_lo_traj", "leaders_top30"),            # E1 context
    ("leaders_accelerating", "leaders_fading"),      # E1 secondary (by label)
    ("hi_breadth_accel", "lo_breadth_accel"),        # E2 primary, accel share
    ("hi_breadth_accel", "universe"),
    ("lo_breadth_accel", "universe"),
    ("hi_breadth_score", "lo_breadth_score"),        # E2 primary, median score
    ("hi_breadth_score", "universe"),
    ("lo_breadth_score", "universe"),
)

_BREADTH_COHORTS = {"accelerating_share": ("hi_breadth_accel", "lo_breadth_accel"),
                    "median_score": ("hi_breadth_score", "lo_breadth_score")}


def run_period(arrays, pos, params, sector_map, top_n=TOP_N_LEADERS,
               cohort_n=COHORT_N, benchmark="SPY", horizons=(21, 63, 126)) -> dict:
    """Form every cohort of both experiments at one date, then look forward."""
    classified = classify_at(arrays, pos, params, benchmark)
    cohorts, diag = conditional_cohorts(classified, top_n, cohort_n)
    cohorts["universe"] = list(classified)

    sectors_used = {}
    for key in BREADTH_KEYS:
        hi_s, lo_s, _ = rank_sectors(classified, sector_map, key)
        hi_name, lo_name = _BREADTH_COHORTS[key]
        cohorts[hi_name] = sector_members(classified, sector_map, hi_s)
        cohorts[lo_name] = sector_members(classified, sector_map, lo_s)
        sectors_used[key] = {"hi": hi_s, "lo": lo_s}

    forward = {}
    for h in horizons:
        forward[h] = {}
        for name, members in cohorts.items():
            rs = [forward_return(arrays[t], pos, h) for t in members]
            rs = [r for r in rs if r is not None]
            forward[h][name] = float(np.median(rs)) if rs else None
    return {**cohorts, "forward": forward, "pos": pos, "diagnostics": diag,
            "sectors_used": sectors_used}


def run_backtest(prices, params, sector_map, top_n=TOP_N_LEADERS,
                 cohort_n=COHORT_N, benchmark="SPY", horizons=(21, 63, 126),
                 step=21) -> dict:
    arrays = price_arrays(prices)
    positions = formation_positions(len(prices), forward=max(horizons), step=step)
    periods = [run_period(arrays, p, params, sector_map, top_n, cohort_n,
                          benchmark, horizons) for p in positions]
    screened = sum(1 for c in prices.columns if c != benchmark)
    out = {
        "periods": len(periods), "positions": positions, "screened": screened,
        "sizes": {name: [len(p[name]) for p in periods] for name in COHORTS},
        "dropped": [p["diagnostics"]["dropped"] for p in periods],
        "skipped": [screened - len(p["universe"]) for p in periods],
        "sectors_used": {k: [p["sectors_used"][k] for p in periods]
                         for k in BREADTH_KEYS},
        "cohorts": {}, "paired": {}, "per_date": {},
    }
    for h in horizons:
        out["cohorts"][h] = {}
        for name in COHORTS:
            vals = [p["forward"][h][name] for p in periods
                    if p["forward"][h].get(name) is not None]
            out["cohorts"][h][name] = {
                "median": float(np.median(vals)) if vals else None,
                "mean": float(np.mean(vals)) if vals else None,
                "periods": len(vals),
            }
        # No aggregate cross-cohort spread is computed anywhere in this module,
        # deliberately: the parent study shipped that error three times.
        out["paired"][h] = {f"{a}-{b}": paired_stats(periods, h, a, b)
                            for a, b in PAIRS}
        out["per_date"][h] = {name: [p["forward"][h][name] for p in periods]
                              for name in COHORTS}
    return out


def _fmt_pp(v):
    return "n/a" if v is None else f"{v * 100:+.2f}pp"


def _fmt_pct(v):
    return "n/a" if v is None else f"{v:+.2%}"


def main(argv=None):
    from vantage.settings import load_settings
    s = load_settings()
    hist = sorted((s.cache_dir / "history").glob("prices-*.parquet"))
    if not hist:
        print("No history snapshot. Run tools/fetch_history.py first.")
        return 1
    sector_path = s.cache_dir / "sectors.json"
    if not sector_path.exists():
        print(f"No sector map at {sector_path}.")
        return 1
    prices = pd.read_parquet(hist[-1]).sort_index()
    sector_map = load_sector_map(sector_path)
    print(f"{hist[-1].name}: {len(prices.columns)} tickers, {len(prices)} sessions")
    print(f"sectors.json: {len(sector_map)} tickers "
          f"(TODAY's labels applied to historical dates -- see caveats)")

    out = run_backtest(prices, MomentumParams(), sector_map)
    idx = prices.index
    print(f"\n=== conditional + sector breadth — {out['periods']} formation dates "
          f"({idx[out['positions'][0]].date()} .. {idx[out['positions'][-1]].date()}) ===")
    u, sk, dr = out["sizes"]["universe"], out["skipped"], out["dropped"]
    print(f"  usable tickers/date  min {min(u)}  median {np.median(u):g}  max {max(u)}"
          f"  of {out['screened']} screened  (skipped: min {min(sk)}, max {max(sk)})")
    print(f"  leaders dropped for unusable score/date  min {min(dr)}"
          f"  median {np.median(dr):g}  max {max(dr)}  of {TOP_N_LEADERS}")
    for name in COHORTS:
        z = out["sizes"][name]
        print(f"  size {name:<22} min {min(z)}  median {np.median(z):g}"
              f"  mean {np.mean(z):.1f}  max {max(z)}"
              f"  empty on {sum(1 for v in z if v == 0)} dates")
    print()
    for h in (21, 63, 126):
        for name in COHORTS:
            c = out["cohorts"][h][name]
            print(f"  {h:>3}d cohort {name:<22} median {_fmt_pct(c['median'])}"
                  f"  mean {_fmt_pct(c['mean'])}  on {c['periods']} dates")
    print()
    for h in (21, 63, 126):
        for key, st in out["paired"][h].items():
            print(f"  {h:>3}d paired {key:<42} median {_fmt_pp(st['median_diff'])}"
                  f"  mean {_fmt_pp(st['mean_diff'])}  sd {_fmt_pp(st['std_diff'])}"
                  f"  first-wins {st['wins']}/{st['periods']}  ties {st['ties']}")

    # How often did each sector land in the top 3 / bottom 3? Context for
    # reading experiment 2: a ranking that always picks the same sectors is
    # measuring those sectors, not breadth.
    print()
    for key in BREADTH_KEYS:
        for side in ("hi", "lo"):
            counts = {}
            for rec in out["sectors_used"][key]:
                for sec in rec[side]:
                    counts[sec] = counts.get(sec, 0) + 1
            top = sorted(counts.items(), key=lambda kv: -kv[1])
            print(f"  {key} {side}: " +
                  ", ".join(f"{s} {n}" for s, n in top))

    out_path = s.cache_dir / "history" / "backtest-conditional-results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
