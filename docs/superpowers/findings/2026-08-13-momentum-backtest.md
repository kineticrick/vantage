# Finding: does the acceleration score beat 12-month momentum?

**Date:** 2026-08-13
**Spec:** `docs/superpowers/specs/2026-08-13-momentum-term-structure-design.md`
**Tooling:** `tools/fetch_history.py` → `tools/backtest_momentum.py`
**Snapshot:** `cache/history/prices-2026-08-13.parquet` — 913 tickers (912
non-benchmark, including QQQ — the harness only excludes the return
benchmark, SPY — plus SPY itself), 2,513 sessions, 2016-08-15 → 2026-08-13.
**Run:** `.venv/bin/python tools/backtest_momentum.py`, all default settings
(`n_cohort=15`, `benchmark="SPY"`, `horizons=(21, 63, 126)`, `step=21`).

**Correction note (third pass):** this document has been reviewed and
corrected twice. Round one fixed a harness bug (the fading cohort was an
unranked positional slice, not the full population it now is) and an
analytical error (a false claim that a gate parameter "never bound"). Round
two — this pass — fixes a false statement about why that fix was necessary,
and a second analytical error that is the *same category of mistake* the
document itself diagnoses in round one: comparing two separately-aggregated
medians is not the same as pairing per-date differences, and doing so
silently flipped the sign of two conclusions (§2 and §4 below). All three
are disclosed in place rather than silently corrected, because the pattern
of error is as much the finding as the numbers are. Every number in this
document comes from the harness as currently committed; the paired
per-date statistics were computed directly from `run_period`'s per-date
output (not from `backtest-results.json`, which only stores the
already-aggregated cohort medians/means and cannot reproduce a paired
comparison).

## 1. Headline

**No — the trajectory (acceleration) score does not beat the trailing
12-month leader rank at any tested horizon, and this holds up under both an
aggregate and a paired per-date check.** Aggregate medians: the pure
12-month-leader cohort outperformed the accelerating cohort by -0.37
percentage points at 1 month, -3.81pp at 3 months, and -3.93pp at 6 months.
Paired per-date medians (accelerating minus leaders, computed per formation
date, then aggregated — the statistically correct way to compare two
cohorts measured on the same dates) show the same sign at every horizon:
-1.21pp, -1.41pp, -5.31pp, with accelerating losing to leaders on a
majority of individual formation dates (60/102, 56/102, 64/102). The two
methods disagree on exact magnitude but agree on sign and on which side
wins, at every horizon. Every one of the six parameter variants tested
produced the same negative sign at every horizon on the aggregate measure.

Do not read this as "the acceleration score carries no information in any
absolute sense" — see §2 below, where the same paired methodology shows its
apparent edge over the *plain universe* (as opposed to the leader control)
is not distinguishable from noise. The only claim this study supports is:
**it loses to the 12-month-rank control Vantage already uses.**

## 2. The table

Baseline parameters (`MomentumParams()` defaults), 102 formation dates,
step = 21 trading days. All four cohorts had 102/102 formation dates
contribute a value (no cohort was ever empty across the run).

### Cohort forward returns (unpaired, for context)

These are each cohort's own aggregate median/mean across all 102 dates,
useful for orientation but **not** valid for computing one cohort minus
another — see the next subsection for why, and for the numbers that are
valid for that purpose.

| Horizon | Accelerating | Leaders (12m rank) | Fading | Universe |
|---|---|---|---|---|
| 21d (~1mo) median | +2.06% | +2.43% | +2.01% | +2.14% |
| 21d mean | +1.53% | +2.44% | +1.34% | +1.22% |
| 63d (~3mo) median | +3.92% | +7.73% | +3.83% | +4.34% |
| 63d mean | +5.04% | +8.34% | +3.36% | +3.31% |
| 126d (~6mo) median | +8.19% | +12.12% | +5.96% | +6.68% |
| 126d mean | +10.27% | +15.62% | +5.87% | +6.15% |

Raw run output (baseline block):

```
prices-2026-08-13.parquet: 913 tickers, 2513 sessions

=== baseline — 102 formation dates ===
   21d fwd  accel +2.06%  leaders +2.43%  universe +2.14%  fading +2.01%  spread -0.37%
   63d fwd  accel +3.92%  leaders +7.73%  universe +4.34%  fading +3.83%  spread -3.81%
  126d fwd  accel +8.19%  leaders +12.12%  universe +6.68%  fading +5.96%  spread -3.93%
```

### Paired per-date comparisons: hit rate and dispersion

**This subsection replaces an earlier draft that computed "accelerating
minus universe" and "fading minus universe" as differences of the
separately-aggregated medians above (e.g. 8.19% − 6.68% = +1.51pp). That is
not a valid way to compare two cohorts observed on the same 102 dates — a
difference of medians is not the median of differences, and the earlier
draft's conclusions do not survive correcting it. This is the same failure
mode diagnosed in §3 below (a median-based aggregate can misrepresent what
happens date by date), showing up a second time in the same document.**

The correct comparison pairs each cohort's forward return *on the same
formation date* and aggregates the resulting 102 differences directly.
Design spec §4.2 requires hit rate and dispersion alongside mean/median for
exactly this reason; neither was reported in earlier drafts, which is what
let the error through.

**Accelerating − universe**, paired per date:

| Horizon | Median diff | Mean diff | Std dev (dispersion) | Hit rate (accel > universe) |
|---|---|---|---|---|
| 21d | +0.48pp | +0.30pp | 4.8pp | 54 / 102 |
| 63d | +0.03pp | +1.73pp | 10.8pp | 52 / 102 |
| 126d | +1.34pp | +4.13pp | 16.7pp | 58 / 102 |

**Fading − universe**, paired per date:

| Horizon | Median diff | Mean diff | Std dev (dispersion) | Hit rate (fading < universe) |
|---|---|---|---|---|
| 21d | -0.04pp | +0.11pp | 1.3pp | 54 / 102 |
| 63d | **+0.09pp** | +0.05pp | 2.4pp | 47 / 102 |
| 126d | -0.02pp | -0.27pp | 3.2pp | 52 / 102 |

**Accelerating − leaders**, paired per date, for comparison against the
headline (§1):

| Horizon | Median diff | Mean diff | Std dev (dispersion) | Hit rate (accel < leaders) |
|---|---|---|---|---|
| 21d | -1.21pp | -0.92pp | 7.5pp | 60 / 102 |
| 63d | -1.41pp | -3.30pp | 14.5pp | 56 / 102 |
| 126d | -5.31pp | -5.35pp | 23.7pp | 64 / 102 |

Reading these together: **accelerating-vs-universe and fading-vs-universe
are both statistically indistinguishable from noise.** Hit rates sit in the
50–58% range against a 50% coin-flip baseline, medians and means disagree
in sign and magnitude within the same row (e.g. accelerating-vs-universe at
63d: median +0.03pp but mean +1.73pp; fading-vs-universe at 63d: median is
*positive* — fading beat the universe on the median date — while the
earlier draft's aggregate-median approach reported -0.51pp), and dispersion
is large relative to the point estimates (e.g. accelerating-vs-universe at
126d: median +1.34pp against a 16.7pp standard deviation across only 102,
non-independent, overlapping dates). None of this supports "the score
modestly beats the universe" or "the fade flag has a small, real,
growing signal" — both claims in earlier drafts, both now withdrawn.

**Accelerating-vs-leaders (the actual headline) is different: it is
directionally consistent.** All three horizons show a negative median,
negative mean, and a hit rate that climbs with horizon (58.8% → 54.9% →
62.7%) — smaller effects than the ~50% coin-flip range seen in the
universe comparisons above, and still not dispositive on 102
non-independent dates, but a materially different picture from the
universe comparisons: same sign on both statistics at every horizon, and
hit rate consistently above half rather than oscillating around it. That
consistency, not the size of any single point estimate, is why §1 treats
this result as robust and the universe comparisons as noise.

*Why mean survived unpaired but median didn't:* mean is a linear
statistic, so `mean(A) − mean(B) == mean(A − B)` always holds — a
difference-of-means is automatically a mean-of-differences, paired or not.
Median has no such identity. That is precisely why the mean-based spread
figures reported throughout this document (e.g. -0.92 / -3.30 / -5.35pp in
§1) needed no correction, while every median-based cross-cohort comparison
did.

## 3. Parameter sweep

All six variants, spread vs. leaders (accelerating − leaders, aggregate
median) at each horizon, from the actual run:

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

### The one-month gate prediction (design spec §2.2), answered directly — corrected

**An earlier draft claimed the -15% one-month floor "never bound" because
baseline and "no 1m gate" produced identical aggregate median spreads. That
claim is false, and the review that caught it also caught the coordinator
repeating it — it is worth explaining exactly how, because the mechanism is
more informative than either the claim or its correction.**

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
**aggregate median** spread was identical anyway because it is a median of
102 per-date medians, and a median is insensitive to changes on ~5% of
periods unless those changes happen to move the 51st/52nd order statistic;
swapping one name in and one out of a 15-member cohort, on 7 dates out of
102, essentially never does that.

**One more corroboration, free of any re-classification work:** the
**mean** is not blind the way the median is — being linear (see the
identity noted in §2), it reacts to small compositional changes the median
can hide. And indeed, baseline and "no 1m gate" differ on the mean even
though their medians match exactly: accelerating mean is 1.53% vs. 1.52%
at 21d, 5.04% vs. 5.06% at 63d, 10.27% vs. 10.42% at 126d (all four values
read directly from `backtest-results.json`, no re-run needed). Small
differences, but they are there, and the median genuinely is not — this is
the same median-vs-mean sensitivity gap as the paired-comparison finding in
§2, appearing here as a second, independent line of evidence for the same
underlying fact: **the aggregate median statistic this study leans on is
frequently blind to real changes that the mean, or a proper per-date pairing,
can see.**

With that corrected, the actual empirical result on the gate stands as
previously reported: the design predicted a strict positive-1m gate should
*hurt* forward performance (short-horizon reversal). It didn't — the strict
gate (`min_1m_return=0.0`) modestly *helped* on the aggregate median: 63d
accelerating median rose from +3.92% (baseline) to +4.02%, spread improved
from -3.81pp to -3.71pp; 126d rose from +8.19% to +8.66%, spread improved
from -3.93pp to -3.46pp; 21d unchanged. **The prediction was wrong — in the
opposite direction from what was originally (also incorrectly) framed as
"no effect to speak of."** The sweep's six configurations are genuinely
distinct conditions, not a baseline-vs-strict-gate binary; there is no
single "the informative comparison," and treating one as such was itself
part of the original error.

## 4. Does the fade flag work? — corrected, twice

**Round one** of review found that `tools/backtest_momentum.py` built the
fading cohort as `fading[:n_cohort]` — a positional slice of Python
dict/column iteration order (i.e., roughly the parquet's column order), not
a ranking. Unlike `accelerating` and `leaders`, which are genuinely ranked
top-15s, the old "fading" cohort was whichever 15 fading-labeled names
happened to sit earliest in column order, which in practice meant the
alphabetic head of the fading population on every date.

**A false justification for the fix must itself be corrected here.** An
earlier draft, and the harness's own source comment, stated that
`classify()` "only computes `score` for the accelerating path" and that
therefore no principled ranking was available for fading, forcing the
choice of the full population. **That is false.** In `vantage/momentum.py`,
`score` is assigned *before* the label branch — every ticker gets a score
if volatility/gap are usable, regardless of what label it ends up with.
Verified directly: at the 2021-10-15 formation date, all 346 of 346 names
labeled "fading" carried a finite score (most negative: PR -9.81, TPL
-4.53, MRNA -4.23). **A principled ranked cohort — bottom-N by score, i.e.
the N most decelerating names — was available**, and would have preserved
design spec §4.1's requirement that all cohorts be "of equal size N."

**We nonetheless kept the full-population choice**, and are stating the
deviation from spec §4.1 explicitly rather than leaving it implicit: this
study's `fading` cohort is *not* size-N like `accelerating` and `leaders`,
it is every name labeled fading on that date. The full population is
arguably the more honest measurement of "does the fade label predict?" —
a bottom-N-by-score cohort would only test whether the *most extreme*
decelerators underperform, a narrower and different question — but it is a
deviation from the literal "equal size N" instruction, and the spec's own
bullet for cohort D ("names labeled fading") does not itself specify a size
cap the way the bullets for cohorts A and B do, which is the reading this
implementation followed. `tools/backtest_momentum.py`'s inline comment now
states this accurately rather than citing a nonexistent scoring limitation.

The fading population is large and variable: **median 290.5 names per date
(mean 300.4, range 181–521)**, versus the 15-member ranked accelerating and
leaders cohorts. It is not directly size-comparable to those two.

**Round two of review** caught that, independent of the ranking question,
the fading-vs-universe numbers computed after round one's fix were
themselves invalid — computed as a difference of separately-aggregated
medians rather than a paired per-date comparison (the same error described
in §2). The corrected, paired numbers are reproduced from §2 above:

| Horizon | Median diff (paired) | Mean diff (paired) | Std dev | Hit rate (fading underperforms) |
|---|---|---|---|---|
| 21d | -0.04pp | +0.11pp | 1.3pp | 54 / 102 |
| 63d | **+0.09pp** | +0.05pp | 2.4pp | 47 / 102 |
| 126d | -0.02pp | -0.27pp | 3.2pp | 52 / 102 |

**The fade flag shows no reliable signal.** This reverses both the
round-one bugged conclusion ("some short-horizon signal, not durable") and
the round-one-fixed-but-still-wrong conclusion ("small but real and
monotonically growing" — median deltas of -0.13/-0.51/-0.72pp, computed the
invalid unpaired way). The paired numbers are non-monotonic, flip sign
between horizons and between median/mean within the same horizon (63d
median is *positive* — fading modestly outperformed the universe on the
typical date — while 126d mean is negative), and sit on hit rates of
47–54 out of 102, which is within noise of a coin flip. There is nothing
here to report as a finding beyond "not distinguishable from noise, at
this sample size, with this methodology."

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

- Usable-ticker count per date: **minimum 805, median 861.5, maximum 903.**
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

**Methodological lesson, stated for anyone re-running this study: this
document's headline statistic needed a paired companion, twice.** §3 shows
a median-of-102-medians can be completely blind to a change (the one-month
gate) that demonstrably alters the ranked cohort on 7 of 102 dates,
because the change never happens to move the 51st/52nd order statistic.
§2 and §4 show that comparing two cohorts' separately-aggregated medians
(rather than pairing per formation date and aggregating the differences)
can flip the sign of the conclusion outright. Both failures share a root
cause: **median is not linear, so operations that are safe on means
(subtraction, in particular) are not safe on medians.** Anyone extending
this backtest should report hit rate and dispersion (design spec §4.2
already requires this) and should always compare cohorts via paired
per-date differences, never via the difference of two independently
computed aggregate statistics — the mean is forgiving of this shortcut,
the median is not.

**The `fading` cohort deviates from design spec §4.1's "cohorts of equal
size N."** `classify()` assigns every fading-labeled name a finite score
(not only accelerating names — see §4's correction above), so a ranked
bottom-N-by-score cohort was available and would have matched spec. This
study reports the full fading population instead, a deliberate choice
disclosed at the point of use (§4) and in `tools/backtest_momentum.py`'s
source comment, not an oversight — but it is a real deviation from the
letter of the spec, and is recorded here as one.

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

**`backtest-results.json` does not round-trip its horizon keys, and cannot
reproduce the paired per-date statistics in §2/§4.** The `cohorts` and
`spread_vs_leaders` dicts are keyed by the integer horizons (21, 63, 126);
`json.dumps` stringifies them, so a plain `json.loads` of the artifact
yields string keys ("21", "63", "126"), not ints. More importantly, the
JSON only stores each cohort's already-aggregated median/mean per horizon —
it does not retain per-formation-date values, so the paired comparisons in
this document (§2, §4, and the headline robustness check in §1) had to be
computed by re-running `run_period` directly over the snapshot, not by
reading the JSON. Anyone wanting to reproduce or extend the paired analysis
needs to do the same, or the harness needs to be extended to persist
per-date cohort medians.

**The parameter sweep never varies cohort size.** Design spec §4.3 lists N
(cohort size) among the parameters the study should settle empirically
alongside `min_recent_return`, `min_1m_return`, recent window, and
volatility normalization. `SWEEP` in `tools/backtest_momentum.py` does not
include an N variant — every run uses the default `n_cohort=15`. This is an
omission relative to the spec, not a finding; whether a smaller or larger
cohort changes the spread (or the gate-sensitivity issue in §3, or the
fading-cohort deviation above) is untested.

**Other caveats, standard for this kind of study:**
- Overlapping forward windows (21-day formation step against up to 126-day
  forward horizons) mean consecutive formation dates share most of their
  return history — they are not independent observations, and the
  "102 formation dates" figure overstates effective sample size. This also
  means the hit-rate and dispersion figures in §2/§4, while a large
  improvement on an unpaired aggregate, are still not a clean statistical
  test — 102 correlated dates carry less information than 102 independent
  ones.
- No transaction costs, slippage, or position sizing; cohort returns are
  equal-weighted medians (and, where reported, means) of a hypothetical
  instantaneous entry.
- One market regime (2016–2026, a long bull market punctuated by the 2020
  and 2022 drawdowns), one universe (US large/mid-cap index constituents),
  one country.

`cache/` is git-ignored, so neither the parquet snapshot nor
`backtest-results.json` is committed alongside this document — every number
above was transcribed by hand from the actual run's console output, the
JSON artifact's numeric fields, or a direct re-run of `run_period` for the
paired statistics, not regenerated or estimated.

## 6. Recommendation for Phase 2

**The score does not beat 12-month momentum in this backtest, and that
result is robust.** It holds on the aggregate median (-0.37 / -3.81 /
-3.93pp), the aggregate mean (-0.92 / -3.30 / -5.35pp), and the paired
per-date median (-1.21 / -1.41 / -5.31pp, with accelerating losing on the
majority of individual dates at every horizon: 60/102, 56/102, 64/102).
Three different ways of measuring "does accelerating beat leaders" agree in
sign at every horizon. All six parameter variants agree too — zero of 18
variant-horizon combinations showed a positive spread.

**Do not soften this. It should also not be over-extended.** Earlier
drafts additionally claimed the acceleration score "modestly beats the
plain universe" and that the fade flag shows "a small but real,
horizon-growing signal." Both claims relied on the same invalid
unpaired-median comparison and do not survive the paired correction in §2
and §4: accelerating-vs-universe and fading-vs-universe hit rates sit at
47–58 out of 102 (coin-flip range), with signs that flip between median and
mean within the same horizon. **Neither the score's apparent edge over the
universe nor the fade flag's apparent signal is distinguishable from noise
in this study.** The only claim with real support is the comparison Vantage
actually cares about: the acceleration score, as constructed, **loses to
the 12-month-rank control it would have to beat to be worth shipping.**

Recommend that **Phase 2 present momentum term structure as description
only** — "this name's recent pace versus its own longer-run pace," framed
as context alongside the existing 12-month rank — **and make no claim that
the acceleration score beats, replaces, or should reorder the trailing
12-month leader ranking, and no claim that either the acceleration score or
the fade flag carries a demonstrated edge over the plain universe.** Do not
use either as a standalone ranking or forward-return signal for surfacing
purposes.

If a future phase wants to revisit prediction more rigorously, it should
(a) do so against a point-in-time (non-survivorship-biased) universe, since
that bias runs in the direction that would make this already-negative
result look better, not worse, than a clean sample would show; (b) sweep
cohort size N, per spec §4.3, which this study did not, and resolve the
fading-cohort's deviation from spec §4.1 (§5) if a ranked cohort is wanted;
and (c) build paired per-date comparison (with hit rate and dispersion, per
spec §4.2) into the harness itself from the start, rather than as a
post-hoc script — this document needed two separate correction passes to
arrive at that methodology, and a harness that only ever produces
separately-aggregated medians will keep inviting the same mistake.
