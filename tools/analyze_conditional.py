"""Read the follow-up backtest artifact and put every estimate next to its band.

A point estimate with no sample-size context is how the parent study talked
itself into three retracted conclusions. This prints, for every pre-registered
comparison, the paired median/mean/dispersion AND the hit-rate z-score and the
mean's t-statistic computed at the EFFECTIVE sample size -- 21-day formation
steps against 63- and 126-day horizons mean consecutive dates share most of
their forward window, so effective N is roughly 102 / 34 / 17, not 102 / 102 /
102.

It also runs a POSITIVE CONTROL that was not pre-registered and is counted as
such: the top-30 leaders against the plain universe. The parent study resolved
that effect (its only resolvable one), so a harness that cannot see it here is
not measuring what it claims to measure.

Run:  .venv/bin/python tools/analyze_conditional.py
Tooling only.
"""
import json
import sys
from math import sqrt
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tools"))

from backtest_conditional import PAIRS  # noqa: E402

# Effective independent observations per horizon: dates / (horizon / step).
EFFECTIVE_N = {21: 102, 63: 34, 126: 17}


def effective_n(horizon, periods):
    return max(1, int(round(periods / max(1, horizon / 21))))


def hit_rate_z(wins, periods, horizon):
    """How far a hit rate sits from a coin flip, at the honest sample size."""
    if not periods:
        return None
    n = effective_n(horizon, periods)
    share = wins / periods
    return (share - 0.5) / (0.5 / sqrt(n))


def mean_t(mean_diff, std_diff, periods, horizon):
    if mean_diff is None or not std_diff:
        return None
    n = effective_n(horizon, periods)
    return mean_diff / (std_diff / sqrt(n))


def paired_from_series(a_vals, b_vals):
    diffs = [a - b for a, b in zip(a_vals, b_vals)
             if a is not None and b is not None]
    if not diffs:
        return None
    return {"median_diff": float(np.median(diffs)), "mean_diff": float(np.mean(diffs)),
            "std_diff": float(np.std(diffs, ddof=1)) if len(diffs) > 1 else None,
            "wins": sum(d > 0 for d in diffs), "ties": sum(d == 0 for d in diffs),
            "periods": len(diffs)}


def _row(label, horizon, st):
    z = hit_rate_z(st["wins"], st["periods"], horizon)
    t = mean_t(st["mean_diff"], st["std_diff"], st["periods"], horizon)
    share = 100.0 * st["wins"] / st["periods"] if st["periods"] else float("nan")
    return (f"  {horizon:>3}d {label:<40}"
            f" med {st['median_diff'] * 100:+6.2f}pp"
            f" mean {st['mean_diff'] * 100:+6.2f}pp"
            f" sd {st['std_diff'] * 100:6.2f}pp"
            f" hit {st['wins']:>3}/{st['periods']} ({share:4.1f}%)"
            f" z {z:+5.2f} t {t:+5.2f}")


def main(argv=None):
    from vantage.settings import load_settings
    s = load_settings()
    path = s.cache_dir / "history" / "backtest-conditional-results.json"
    if not path.exists():
        print(f"No artifact at {path}. Run tools/backtest_conditional.py first.")
        return 1
    out = json.loads(path.read_text(encoding="utf-8"))   # horizon keys are STRINGS

    print("effective N per horizon (21-day step vs the horizon's window):")
    for h in (21, 63, 126):
        print(f"  {h:>3}d -> {effective_n(h, out['periods'])} of {out['periods']} dates")
    print("\nA fair coin over that many tosses lands inside |z| < 1.96 about 95%\n"
          "of the time. Every row below is a separate hypothesis test.\n")

    n_tests = 0
    for h in (21, 63, 126):
        for a, b in PAIRS:
            st = out["paired"][str(h)][f"{a}-{b}"]
            if st["periods"]:
                print(_row(f"{a} - {b}", h, st))
                n_tests += 1
        print()

    print("POSITIVE CONTROL (not pre-registered; counted in the tally):")
    for h in (21, 63, 126):
        st = paired_from_series(out["per_date"][str(h)]["leaders_top30"],
                                out["per_date"][str(h)]["universe"])
        print(_row("leaders_top30 - universe", h, st))
        n_tests += 1

    print(f"\ntests in this study: {n_tests}")
    sig = []
    for h in (21, 63, 126):
        for a, b in PAIRS:
            st = out["paired"][str(h)][f"{a}-{b}"]
            if not st["periods"]:
                continue
            z = hit_rate_z(st["wins"], st["periods"], h)
            t = mean_t(st["mean_diff"], st["std_diff"], st["periods"], h)
            if abs(z) >= 1.96 or (t is not None and abs(t) >= 1.96):
                sig.append((h, f"{a}-{b}", z, t))
    print(f"pre-registered comparisons reaching |z| or |t| >= 1.96: {len(sig)}")
    for h, k, z, t in sig:
        print(f"  {h}d {k}: z {z:+.2f} t {t:+.2f}")

    print("\nsign agreement between paired median and paired mean, per pair:")
    for a, b in PAIRS:
        signs = []
        for h in (21, 63, 126):
            st = out["paired"][str(h)][f"{a}-{b}"]
            signs.append(f"{h}d med {np.sign(st['median_diff']):+.0f}"
                         f"/mean {np.sign(st['mean_diff']):+.0f}")
        print(f"  {a} - {b}: " + "  ".join(signs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
