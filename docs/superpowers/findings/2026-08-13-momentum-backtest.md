# Finding: does the acceleration score beat 12-month momentum?

**Date:** 2026-08-13
**Spec:** `docs/superpowers/specs/2026-08-13-momentum-term-structure-design.md`
**Tooling:** `tools/fetch_history.py` → `tools/backtest_momentum.py`
**Snapshot:** `cache/history/prices-2026-08-13.parquet` — 913 tickers (911
non-benchmark constituents plus SPY and QQQ), 2,513 sessions, 2016-08-15 →
2026-08-13.
**Run:** `.venv/bin/python tools/backtest_momentum.py`, all default settings
(`n_cohort=15`, `benchmark="SPY"`, `horizons=(21, 63, 126)`, `step=21`).

## 1. Headline

**No — the trajectory (acceleration) score does not beat the trailing
12-month leader rank at any tested horizon.** In the baseline configuration,
the pure 12-month-leader cohort outperformed the accelerating cohort by
-0.37 percentage points at 1 month, -3.81pp at 3 months, and -3.93pp at 6
months (median forward return, accelerating minus leaders). The gap widens,
not narrows, with horizon. Every one of the six parameter variants tested
produced the same sign at every horizon: the accelerating cohort never beat
the 12-month leader cohort.

## 2. The table

Baseline parameters (`MomentumParams()` defaults), 102 formation dates,
step = 21 trading days:

| Horizon | Accelerating (median) | Leaders — 12m rank (median) | Fading (median) | Universe (median) | Spread (accel − leaders) |
|---|---|---|---|---|---|
| 21d (~1mo) | +2.06% | +2.43% | +1.70% | +2.14% | -0.37pp |
| 63d (~3mo) | +3.92% | +7.73% | +4.08% | +4.34% | -3.81pp |
| 126d (~6mo) | +8.19% | +12.12% | +6.71% | +6.68% | -3.93pp |

All four cohorts had 102/102 formation dates contribute a value (no cohort
was ever empty across the run).

Raw run output (baseline block):

```
prices-2026-08-13.parquet: 913 tickers, 2513 sessions

=== baseline — 102 formation dates ===
   21d fwd  accel +2.06%  leaders +2.43%  universe +2.14%  fading +1.70%  spread -0.37%
   63d fwd  accel +3.92%  leaders +7.73%  universe +4.34%  fading +4.08%  spread -3.81%
  126d fwd  accel +8.19%  leaders +12.12%  universe +6.68%  fading +6.71%  spread -3.93%
```

## 3. Parameter sweep

All six variants, spread vs. leaders (accelerating − leaders) at each
horizon, from the actual run:

| Variant | 21d spread | 63d spread | 126d spread |
|---|---|---|---|
| baseline | -0.37pp | -3.81pp | -3.93pp |
| strict 1m gate (`min_1m_return=0.0`) | -0.37pp | -3.71pp | -3.46pp |
| no 1m gate (`min_1m_return=-1.0`) | -0.37pp | -3.81pp | -3.93pp |
| 6m recent window | -0.20pp | -0.98pp | -1.24pp |
| no vol normalization | -0.24pp | -2.43pp | -4.55pp |
| strength floor 15% (`min_recent_return=0.15`) | -0.39pp | -4.02pp | -3.10pp |

**Zero of the 18 (6 variants × 3 horizons) spread values were positive.**
No variant beat the 12-month leader cohort at any horizon, so there is no
cherry-picked "winning" configuration to report — six variants were tried
against the same 102 formation dates and same three horizons, and this
sweep width is itself a multiple-comparisons exposure worth naming even
though, in this case, it produced no false positive to guard against.

**§2.2 prediction, answered directly.** The design spec argued that because
short-horizon returns tend to reverse rather than continue, a strict
positive-1m gate (`min_1m_return=0.0`, requiring a positive trailing month)
should *hurt* forward performance. **The prediction was wrong.** The strict
gate did not hurt — it modestly *helped*:

- 63d: accelerating median rose from +3.92% (baseline, `min_1m_return=-0.15`)
  to +4.02% (strict gate); spread vs. leaders improved from -3.81pp to
  -3.71pp.
- 126d: accelerating median rose from +8.19% to +8.66%; spread improved from
  -3.93pp to -3.46pp.
- 21d: no change (+2.06% either way).

Separately, loosening the gate to `min_1m_return=-1.0` ("no 1m gate")
produced results **bit-for-bit identical** to baseline at every horizon —
the default -15% floor never actually excluded a candidate from the
accelerating cohort in this dataset, i.e. it never bound. So the informative
comparison is baseline/no-gate versus the strict positive gate, and that
comparison runs opposite the reversal hypothesis. The effect is small in
absolute terms (0.10–0.47pp) relative to the ~3.5–3.9pp gap the accelerating
cohort is already running behind leaders, so it does not change the
headline — but the direction is the opposite of what §2.2 predicted, and
that should be reported plainly rather than smoothed over.

## 4. Does the fade flag work?

Partially, and only briefly. Fading vs. universe (baseline):

| Horizon | Fading (median) | Universe (median) | Fading − universe |
|---|---|---|---|
| 21d | +1.70% | +2.14% | -0.44pp |
| 63d | +4.08% | +4.34% | -0.26pp |
| 126d | +6.71% | +6.68% | +0.03pp |

The fading cohort modestly underperforms the universe at 1 and 3 months
(consistent with the flag catching real deceleration), but the gap
collapses to essentially zero by 6 months. Read plainly: the fade label has
some short-horizon signal but it is not durable, and by the 6-month mark
fading names track the broad universe rather than continuing to lag it.

## 5. Caveats — stated plainly

**Survivorship bias is the largest threat to validity.** The universe is
today's index membership (`config/universe.txt`); anything delisted or
removed from the index over the ten-year window is silently absent from the
backtest, which biases every number in this document optimistic relative to
a point-in-time universe.

This backtest also measured, and must report, a related but distinct
effect: **the effective universe screened at each formation date grows over
time**, because `metrics_at` requires a full trailing 252-day window and
drops a ticker entirely if any part of that window is missing (e.g. before
an IPO or index addition). Measured directly across the 102 formation dates:

- Usable-ticker count per date: **minimum 804, median 860, maximum 902**
  (out of 911 non-benchmark tickers in the snapshot).
- The count stabilizes to within 95% of its maximum (n=857) by the formation
  date **2021-07-19**; it climbs gradually and gently from the earliest
  formation date (2017-08-15, n=804) through roughly mid-2021, then holds in
  the 857–902 range for the remainder of the sample.

This is real but considerably milder than a naive read of "only ~165 of
913 tickers have zero-gap history across the full ten years" would
suggest. That stricter figure (163 tickers with a fully finite series
across all 2,513 sessions, measured directly against this same snapshot) is
a different, much stricter test: it disqualifies a ticker for *any* missing
observation anywhere in the ten-year panel, including brief mid-series data
gaps that have nothing to do with lifecycle (IPO/delisting) and do not
affect `metrics_at`'s narrower trailing-window check. The per-formation-date
counts above are the number actually relevant to this study, and they show
a universe that starts at ~88% of its eventual size and reaches it within
about four years — a real but modest growth, not a "hundred-odd vs. ~900"
split. Even so, any apparent time trend in these results (e.g., changes in
cohort composition or spread magnitude across formation dates) could be
partly an artifact of this growing, narrower-early pool rather than a pure
regime effect, and should not be read as such without controlling for it.

**The `leaders` cohort here is not identical to what Vantage ships today.**
This backtest's `leaders` cohort is a pure top-15-by-trailing-12-month-return
rank with no floor — the correct control for isolating "does the
acceleration score beat 12-month rank," but it is a *superset* of what the
live screener actually surfaces. `vantage/screener.py` only emits a
`ret_12m_leader` signal when `ret_12m >= +100%` (`return_leader_threshold=1.0`),
and on an implausible metric reading the live pipeline drops just the
offending metric for that ticker, whereas this backtest's `metrics_at`
drops the entire ticker if any single window in it is unusable. Do not read
the `leaders` numbers in this document as "what the dashboard shows today";
they are the idealized 12-month-rank control the design called for.

**`backtest-results.json` does not round-trip its horizon keys.** The
`cohorts` and `spread_vs_leaders` dicts are keyed by the integer horizons
(21, 63, 126); `json.dumps` stringifies them, so a plain `json.loads` of the
artifact yields string keys ("21", "63", "126"), not ints. Anyone consuming
that file directly needs to know this; it is why every number in this
document is transcribed from the run output rather than merely pointed at
the JSON (the JSON is also git-ignored — see below).

**Other caveats, standard for this kind of study:**
- Overlapping forward windows (21-day formation step against up to 126-day
  forward horizons) mean consecutive formation dates share most of their
  return history — they are not independent observations, and the
  "102 formation dates" figure overstates effective sample size.
- No transaction costs, slippage, or position sizing; cohort returns are
  equal-weighted medians of a hypothetical instantaneous entry.
- One market regime (2016–2026, a long bull market punctuated by the 2020
  and 2022 drawdowns), one universe (US large/mid-cap index constituents),
  one country.

`cache/` is git-ignored, so neither the parquet snapshot nor
`backtest-results.json` is committed alongside this document — every number
above was transcribed by hand from the actual run's console output and the
JSON artifact, not regenerated or estimated.

## 6. Recommendation for Phase 2

**The score does not beat 12-month momentum in this backtest.** Across all
six parameter variants and all three horizons, the accelerating cohort
underperformed the pure 12-month-leader cohort — most severely at 3 and 6
months, where the gap runs roughly -3.5pp to -4.6pp in five of six variants
(the sixth, the 6-month recent window, narrows the gap to -1.0pp to -1.2pp
but never crosses to positive). This is a negative result, and it should be
reported as one rather than framed around whichever variant happened to
come closest.

Recommend that **Phase 2 present momentum term structure as description
only** — "this name's recent pace versus its own longer-run pace," framed
as context alongside the existing 12-month rank — **and make no
forward-return or ranking claim from the acceleration score.** Do not use
the acceleration score to replace, reorder, or supplement the trailing
12-month leader ranking for surfacing purposes. If a future phase wants to
revisit prediction, it should do so against a point-in-time (non-
survivorship-biased) universe, since that bias runs in the direction that
would make this already-negative result look better, not worse, than a
clean sample would show.
