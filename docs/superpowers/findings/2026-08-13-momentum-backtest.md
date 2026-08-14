# Finding: does the acceleration score beat 12-month momentum?

**Date:** 2026-08-13
**Spec:** `docs/superpowers/specs/2026-08-13-momentum-term-structure-design.md`
**Tooling:** `tools/fetch_history.py` → `tools/backtest_momentum.py`
**Snapshot:** `cache/history/prices-2026-08-13.parquet` — 913 tickers (912
non-benchmark, including QQQ — the harness only excludes the return
benchmark, SPY — plus SPY itself), 2,513 sessions, 2016-08-15 → 2026-08-13.
**Run:** `.venv/bin/python tools/backtest_momentum.py`, all default settings
(`n_cohort=15`, `benchmark="SPY"`, `horizons=(21, 63, 126)`, `step=21`).

**Correction note:** this document was reviewed after a first draft and two
critical analytical errors were found and fixed before publishing. Both are
disclosed in place below (§3 and §4) rather than silently corrected,
because how they were wrong is itself part of the finding. One harness bug
(the fading cohort) was fixed in `tools/backtest_momentum.py` and the study
re-run; every number in this document comes from that corrected run.

## 1. Headline

**No — the trajectory (acceleration) score does not beat the trailing
12-month leader rank at any tested horizon.** In the baseline configuration,
the pure 12-month-leader cohort outperformed the accelerating cohort by
-0.37 percentage points at 1 month, -3.81pp at 3 months, and -3.93pp at 6
months (median forward return, accelerating minus leaders). The mean-based
spread agrees in sign and is larger: -0.92pp, -3.30pp, -5.35pp. The gap
widens, not narrows, with horizon, on both statistics. Every one of the six
parameter variants tested produced the same sign at every horizon: the
accelerating cohort never beat the 12-month leader cohort.

That said — see §6 — the 12-month leader rank used as the control here is
itself an unusually strong performer relative to the plain universe, so
"loses to this control" is a narrower and more accurate claim than "carries
no information at all."

## 2. The table

Baseline parameters (`MomentumParams()` defaults), 102 formation dates,
step = 21 trading days. All four cohorts had 102/102 formation dates
contribute a value (no cohort was ever empty across the run).

### 2.1 Cohort forward returns

| Horizon | Accelerating | Leaders (12m rank) | Fading | Universe |
|---|---|---|---|---|
| 21d (~1mo) median | +2.06% | +2.43% | +2.01% | +2.14% |
| 21d mean | +1.53% | +2.44% | +1.34% | +1.22% |
| 63d (~3mo) median | +3.92% | +7.73% | +3.83% | +4.34% |
| 63d mean | +5.04% | +8.34% | +3.36% | +3.31% |
| 126d (~6mo) median | +8.19% | +12.12% | +5.96% | +6.68% |
| 126d mean | +10.27% | +15.62% | +5.87% | +6.15% |

Raw run output (baseline block, post-fix):

```
prices-2026-08-13.parquet: 913 tickers, 2513 sessions

=== baseline — 102 formation dates ===
   21d fwd  accel +2.06%  leaders +2.43%  universe +2.14%  fading +2.01%  spread -0.37%
   63d fwd  accel +3.92%  leaders +7.73%  universe +4.34%  fading +3.83%  spread -3.81%
  126d fwd  accel +8.19%  leaders +12.12%  universe +6.68%  fading +5.96%  spread -3.93%
```

### 2.2 Every cohort against the plain universe

The design spec (§4.2) calls for this comparison and an earlier draft of
this document printed the universe column without ever using it. Reporting
it changes the picture materially: the accelerating cohort is not "no
better than random" — it modestly beats the plain universe at longer
horizons, it simply loses by more to the 12-month-rank control.

| Comparison | 21d | 63d | 126d |
|---|---|---|---|
| Accelerating − universe (median) | -0.08pp | -0.42pp | **+1.51pp** |
| Accelerating − universe (mean) | **+0.30pp** | **+1.73pp** | **+4.13pp** |
| Leaders − universe (median) | +0.29pp | +3.39pp | +5.44pp |
| Leaders − universe (mean) | +1.22pp | +5.04pp | +9.47pp |
| Fading − universe (median) | -0.13pp | -0.51pp | -0.72pp |
| Fading − universe (mean) | +0.11pp | +0.05pp | -0.27pp |

Two things follow from this table. First, on the mean statistic the
accelerating cohort beats the plain universe at every horizon, and on the
median it does too by 6 months — so the honest description of the score is
"loses decisively to an unusually strong control, while still modestly
beating a naive baseline," not "carries no predictive information." Second,
the 12-month-leader control is not a neutral yardstick: it beats the
universe by +5.44pp median / +9.47pp mean at 6 months, which is a large
edge for a "control." Losing to that control is a real, negative finding
about the acceleration score relative to what Vantage does today — it is
just not evidence that trailing pace/acceleration information is worthless
in general.

## 3. Parameter sweep

All six variants, spread vs. leaders (accelerating − leaders, median) at
each horizon, from the actual run:

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
cherry-picked "winning" configuration to report — the sweep is six
genuinely distinct conditions tried against the same 102 formation dates
and same three horizons, and that width is itself a multiple-comparisons
exposure worth naming even though, in this case, it produced no false
positive to guard against.

### 3.1 §2.2 prediction, answered directly — corrected

**An earlier draft of this section claimed the -15% one-month floor "never
bound" because baseline and "no 1m gate" produced identical aggregate
spreads. That claim is false, and the review that caught it also caught the
coordinator repeating it — it is worth explaining exactly how, because the
mechanism is more informative than either the claim or its correction.**

Measured directly by re-classifying every ticker at every formation date
under both `min_1m_return=-0.15` (baseline) and `min_1m_return=-1.0` (no
gate) and diffing the results:

- The floor excluded **70 otherwise-eligible name-dates** — cases where a
  ticker passed every other accelerating gate (positive gap, strength
  floor, positive 12-month return) but its trailing one-month return was
  below -15%, so baseline denied it the "accelerating" label while the
  no-gate variant granted it.
- The accelerating-**eligible set** (before ranking/truncation to top-15)
  differed between the two variants on **29 of the 102 formation dates**.
- The actual **top-15 cohort** — after ranking by score and slicing — only
  differed on **7 of the 102 dates**. On those 7 dates, the floor's absence
  let a gate-rescued name outscore and displace the marginal 15th member:

  | Date | Dropped (baseline has, no-gate lacks) | Added (no-gate has, baseline lacks) |
  |---|---|---|
  | 2018-10-15 | CASY | AMD |
  | 2020-03-18 | SBAC | GEN |
  | 2020-11-13 | PCTY | GME |
  | 2021-03-18 | WAL | MSTR |
  | 2021-12-15 | SLAB | CAR |
  | 2024-01-19 | UBER | COIN |
  | 2024-04-19 | TXRH, DKS | MSTR, COIN |

So the floor *does* bind, and it binds specifically on the highest-volatility,
highest-drama names in the sample — AMD, GME, MSTR, COIN — which is exactly
the population a momentum-acceleration study most needs to get right. The
aggregate spread was identical anyway because **the headline statistic is a
median of 102 per-date medians, and a median is insensitive to changes on
~5% of periods unless those changes happen to move the 51st/52nd order
statistic.** Swapping one name in and one out of a 15-member cohort, on 7
dates out of 102, essentially never does that. The identical top-line
number is a property of the *estimator*, not evidence the *parameter* is
inert — and it means this backtest's headline number would not have
detected the floor mattering even though it demonstrably does at the
individual-cohort level.

With that corrected, the actual §2.2 result stands as previously reported:
the design predicted a strict positive-1m gate should *hurt* forward
performance (short-horizon reversal). It didn't — the strict gate
(`min_1m_return=0.0`) modestly *helped*: 63d accelerating median rose from
+3.92% (baseline) to +4.02%, spread improved from -3.81pp to -3.71pp; 126d
rose from +8.19% to +8.66%, spread improved from -3.93pp to -3.46pp; 21d
unchanged. **The prediction was wrong — in the opposite direction from what
was originally (also incorrectly) framed as "no effect to speak of."** The
sweep's six configurations are genuinely distinct conditions, not a
baseline-vs-strict-gate binary; there is no single "the informative
comparison," and treating one as such was itself part of the error.

## 4. Does the fade flag work? — corrected

**This section was rewritten after a second critical error was found:
`tools/backtest_momentum.py` built the fading cohort as `fading[:n_cohort]`
— a positional slice of Python dict/column iteration order (i.e., roughly
the parquet's column order), not a ranking. Unlike `accelerating` and
`leaders`, which are genuinely ranked top-15s, the old "fading" cohort was
whichever 15 fading-labeled names happened to sit earliest in column order,
which in practice meant the alphabetic head of the fading population on
every date. Every fade number in the original draft described that
alphabetic head, not the fade label's actual performance.**

**Fix applied:** `classify()` does not score fading names the way it scores
accelerating ones (`vantage/momentum.py` only computes `score` for the
`accelerating` path), so there is no principled "top-N by score" ranking
available for fading the way there is for accelerating. The harness now
reports the **full fading population** at each formation date — the
honest, complete answer to "does the fade label predict?" — rather than an
arbitrary positional subset. This is disclosed here as the choice made;
`tools/backtest_momentum.py`'s inline comment explains it at the source.

The fading population is large and variable: **median 290 names per date
(mean 300.4, range 181–521)**, versus the 15-member ranked accelerating and
leaders cohorts. It is not directly size-comparable to those two.

Fading vs. universe, full population, baseline parameters, recomputed from
the corrected run:

| Horizon | Fading (median) | Universe (median) | Fading − universe (median) | Fading − universe (mean) |
|---|---|---|---|---|
| 21d | +2.01% | +2.14% | **-0.13pp** | +0.11pp |
| 63d | +3.83% | +4.34% | **-0.51pp** | +0.05pp |
| 126d | +5.96% | +6.68% | **-0.72pp** | -0.27pp |

**On the median, the fade flag shows a small but real and monotonically
growing signal** — underperformance is weakest at 1 month and grows through
6 months, the opposite of what the original (bugged) draft reported
("some short-horizon signal, not durable"). This is a genuine reversal of
the earlier conclusion, not a restatement of it.

On the mean, the picture is noisier and does not confirm the same monotonic
growth (+0.11pp, +0.05pp, then -0.27pp) — plausibly because a
median-290-name population with a long right tail (it is unranked and
unfiltered) makes the mean sensitive to a handful of large outlier
recoveries that the median ignores. Both statistics agree on the sign at 6
months (fading underperforms universe), but only the median shows the
clean monotonic pattern. Read the fade flag's signal as **real but small**
— at most three quarters of a percentage point of median underperformance
by 6 months — and not something that should carry much weight on its own.

## 5. Caveats — stated plainly

**Survivorship bias is the largest threat to validity.** The universe is
today's index membership (`config/universe.txt`); anything delisted or
removed from the index over the ten-year window is silently absent from the
backtest, which biases every number in this document optimistic relative to
a point-in-time universe.

This backtest also measured, and must report, a related but distinct
effect: **the effective universe screened at each formation date grows over
time.** `metrics_at` does not require every day in a trailing window to be
finite — it samples five specific endpoints per ticker (`pos-252, pos-126,
pos-63, pos-21, pos`) and drops the ticker entirely if any one of those five
points is missing or non-finite (e.g., before an IPO or index addition;
occasionally a data gap). Measured directly across the 102 formation dates,
against the correct denominator of **912 non-benchmark tickers** (the
harness excludes only the return benchmark, SPY — QQQ remains in the
universe/leaders/accelerating/fading pools):

- Usable-ticker count per date: **minimum 805, median 862, maximum 903.**
- The count stabilizes to within 95% of its maximum (n=858) by the
  formation date **2021-07-19**; it climbs gradually and gently from the
  earliest formation date (2017-08-15, n=805) through roughly mid-2021,
  then holds in the 858–903 range for the remainder of the sample.

This is real but considerably milder than a naive read of "only ~165 of
913 tickers have zero-gap history across the full ten years" would
suggest. That stricter figure (164 tickers with a fully finite series
across all 2,513 sessions, out of the same 912, measured directly against
this snapshot) is a different, much stricter test: it disqualifies a
ticker for *any* missing observation anywhere in the ten-year panel,
including data gaps that have nothing to do with lifecycle (IPO/delisting)
and do not affect `metrics_at`'s narrower five-point check. The
per-formation-date counts above are the number actually relevant to this
study, and they show a universe that starts at ~89% of its eventual size
and reaches it within about four years — real but modest growth, not a
"hundred-odd vs. ~900" split. Even so, any apparent time trend in these
results (e.g., changes in cohort composition or spread magnitude across
formation dates) could be partly an artifact of this growing, narrower-early
pool rather than a pure regime effect, and should not be read as such
without controlling for it.

Separately: the 164-fully-gapless figure is driven almost entirely by
**three anomalous sessions in this snapshot** — 2026-07-21 (637 of 913
tickers NaN), 2026-07-22 (653 NaN), 2026-07-31 (519 NaN), evidently a data
gap in the fetch itself rather than genuine market non-trading days. None
of the three is ever sampled as a formation date, a forward-return
endpoint, or a `metrics_at` window endpoint in this study's 21-day grid, so
nothing in the reported numbers is contaminated by them — but that is luck
of the grid alignment, not a property that was verified in advance, and is
worth a line for anyone reusing this snapshot with a different step size.

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
document is transcribed from the run output or read directly out of the
JSON's numeric fields, rather than merely pointed at the file (the JSON is
also git-ignored — see below).

**The parameter sweep never varies cohort size.** Design spec §4.3 lists N
(cohort size) among the parameters the study should settle empirically
alongside `min_recent_return`, `min_1m_return`, recent window, and
volatility normalization. `SWEEP` in `tools/backtest_momentum.py` does not
include an N variant — every run uses the default `n_cohort=15`. This is an
omission relative to the spec, not a finding; whether a smaller or larger
cohort changes the spread (or the fade-flag sensitivity issue in §3.1) is
untested.

**Other caveats, standard for this kind of study:**
- Overlapping forward windows (21-day formation step against up to 126-day
  forward horizons) mean consecutive formation dates share most of their
  return history — they are not independent observations, and the
  "102 formation dates" figure overstates effective sample size.
- No transaction costs, slippage, or position sizing; cohort returns are
  equal-weighted medians (and, where reported, means) of a hypothetical
  instantaneous entry.
- One market regime (2016–2026, a long bull market punctuated by the 2020
  and 2022 drawdowns), one universe (US large/mid-cap index constituents),
  one country.

`cache/` is git-ignored, so neither the parquet snapshot nor
`backtest-results.json` is committed alongside this document — every number
above was transcribed by hand from the actual (post-fix) run's console
output and the JSON artifact's numeric fields, not regenerated or
estimated.

## 6. Recommendation for Phase 2

**The score does not beat 12-month momentum in this backtest, against a
control that is itself unusually strong.** Across all six parameter
variants and all three horizons, the accelerating cohort underperformed the
pure 12-month-leader cohort — most severely at 3 and 6 months, where the
median gap runs roughly -3.5pp to -4.6pp in five of six variants (the
sixth, the 6-month recent window, narrows the gap to -1.0pp to -1.2pp but
never crosses to positive; mean spreads are negative at every horizon in
baseline too, corroborating the median). This is a negative result relative
to the 12-month-rank control, and it should be reported as one rather than
framed around whichever variant happened to come closest.

At the same time, §2.2 shows the accelerating cohort is not informationless
in an absolute sense — it modestly beats the plain universe on the mean at
every horizon and on the median by 6 months. The correct framing is
**"loses to a strong control," not "carries no information."** Recommend
that **Phase 2 present momentum term structure as description only** —
"this name's recent pace versus its own longer-run pace," framed as context
alongside the existing 12-month rank — **and make no claim that the
acceleration score beats, replaces, or should reorder the trailing
12-month leader ranking.** Do not use it as a standalone ranking signal for
surfacing purposes.

The fade flag (§4) is a narrower, softer case: a small, real,
horizon-growing median signal (up to -0.72pp by 6 months) that does not
carry through cleanly on the mean. If Phase 2 wants to use it at all, it
should be as a low-confidence secondary annotation, not a claim with
forward-return weight attached.

If a future phase wants to revisit prediction more rigorously, it should
(a) do so against a point-in-time (non-survivorship-biased) universe, since
that bias runs in the direction that would make this already-negative
result look better, not worse, than a clean sample would show; (b) sweep
cohort size N, per spec §4.3, which this study did not; and (c) report both
median and mean throughout, since §3.1 demonstrates the median-of-medians
statistic can be blind to changes affecting up to ~5% of periods —
precisely the periods driven by the highest-volatility names a momentum
study most needs to handle correctly.
