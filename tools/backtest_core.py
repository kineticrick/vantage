"""Primitives shared by every backtest in this project.

A study defines its own cohorts; these are the parts every study needs and
none should reimplement — where the formation dates fall, how a trailing
window is measured, how a forward return is taken, and how two cohorts are
compared per date.

That last one is not optional. Comparing two separately aggregated statistics
produced three wrong conclusions in this project's own history; `paired_stats`
computes per-date differences and aggregates those. See
.claude/skills/validate-signal/SKILL.md.
"""
import numpy as np

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


def paired_stats(periods, horizon, a, b) -> dict:
    """Difference between two cohorts, formed per date and aggregated after.

    A difference of two separately-aggregated medians is NOT the median of the
    per-date differences -- median is not linear, so subtraction is not safe on
    it. Three rounds of review of this study's finding turned up three separate
    published conclusions whose sign was decided by that shortcut, the last of
    them inside the section written to correct the first two. Pair first,
    aggregate second; report hit rate and dispersion alongside, per design spec
    §4.2, so a point estimate is never read on its own.
    """
    diffs = [p["forward"][horizon][a] - p["forward"][horizon][b] for p in periods
             if p["forward"][horizon].get(a) is not None
             and p["forward"][horizon].get(b) is not None]
    return {
        "median_diff": float(np.median(diffs)) if diffs else None,
        "mean_diff": float(np.mean(diffs)) if diffs else None,
        "std_diff": float(np.std(diffs, ddof=1)) if len(diffs) > 1 else None,
        "wins": sum(d > 0 for d in diffs),      # dates where `a` beat `b`
        "ties": sum(d == 0 for d in diffs),     # e.g. identical cohorts
        "periods": len(diffs),
    }
