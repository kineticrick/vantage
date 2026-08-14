# Finding: does the acceleration score beat 12-month momentum?

**Date:** 2026-08-13
**Spec:** `docs/superpowers/specs/2026-08-13-momentum-term-structure-design.md`
**Tooling:** `tools/fetch_history.py` → `tools/backtest_momentum.py`
**Snapshot:** `cache/history/prices-2026-08-13.parquet` — 913 tickers (912
non-benchmark, including QQQ — the harness only excludes the return
benchmark, SPY — plus SPY itself), 2,513 sessions, 2016-08-15 → 2026-08-13.
**Run:** `.venv/bin/python tools/backtest_momentum.py`, all default settings
(`n_cohort=15`, `benchmark="SPY"`, `horizons=(21, 63, 126)`, `step=21`).

**Correction note (fourth pass):** this document has been reviewed and
corrected three times. Round one fixed a harness bug (the fading cohort was
an unranked positional slice, not the full population it now is) and an
analytical error (a false claim that a gate parameter "never bound"). Round
two fixed a false statement about why that fix was necessary, and a second
analytical error that is the *same category of mistake* the document itself
diagnoses in round one: comparing two separately-aggregated medians is not
the same as pairing per-date differences, and doing so silently flipped the
sign of two conclusions (§2 and §4).

**Round three — this pass — found a _third_ instance of that same error, in
§3's one-month-gate conclusion, which survived both earlier passes.** It was
caught only at final whole-branch review. That is worth stating plainly,
because it is itself the strongest evidence for the methodological caveat
this document already makes (§5): an author who has diagnosed this exact
mistake twice, in writing, in this same document, still shipped a third
instance of it. The unpaired shortcut is not a lapse of attention that more
care would have prevented — it is what the tooling made easy. So round three
also changed the tooling: `run_backtest` now computes paired per-date
differences, hit rate and dispersion itself (design spec §4.2), and every
paired number below is read straight out of it. Round three additionally
withdrew a robustness claim in §3 (the parameter sweep was entirely
unpaired), corrected a misdescribed hit-rate trend in §2, and applied one
consistent standard to hit rates that §2 previously judged two different ways
two paragraphs apart.

All four rounds are disclosed in place rather than silently corrected,
because the pattern of error is as much the finding as the numbers are.

**Reproducibility.** Every number in this document now comes from
`.venv/bin/python tools/backtest_momentum.py` as currently committed — its
console output or `cache/history/backtest-results.json` — with two exceptions
that are labelled where they appear (§3's re-classification of the gate's
mechanism, and §5's fully-gapless-ticker count, both of which answer
questions the harness is not built to answer). Earlier drafts' paired
statistics came from an ad-hoc script that was never committed and could not
be regenerated; that is fixed.

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
wins, at every horizon. All 18 variant-horizon combinations of the parameter
sweep agree in sign, on the unpaired *and* the paired measure (§3).

**What "does not beat" means here, stated precisely.** This study is not
powered to prove that the acceleration score is actively harmful, and should
not be read as proving it. Formation dates step 21 trading days against
horizons up to 126 days, so consecutive dates share most of their forward
window: roughly `horizon / step` consecutive dates overlap, putting the
effective sample at about 102, 34 and 17 independent observations rather than
102. At 63d the paired mean is -3.30pp against a 14.54pp standard deviation —
a standard error of about 2.5pp at the honest N (t ≈ -1.3), or 5.8pp at 126d
(t ≈ -0.9). **Nothing in this study clears conventional significance.** The
supportable claim is the weaker and sufficient one: *the score failed to
demonstrate an edge over the control it would have to beat.* What carries the
headline is not any single point estimate — it is that the sign never once
came out the other way, across three statistics, three horizons, and six
parameter configurations.

Do not read this as "the acceleration score carries no information in any
absolute sense" — see §2 below, where the same paired methodology shows its
apparent edge over the *plain universe* (as opposed to the leader control)
is not distinguishable from noise. The only claim this study supports is:
**it loses to the 12-month-rank control Vantage already uses.**

## 2. The table

Baseline parameters (`MomentumParams()` defaults), 102 formation dates
(2017-08-15 through 2026-01-23), step = 21 trading days. All cohorts had
102/102 formation dates contribute a value (no cohort was ever empty across
the run), so every paired comparison below is over the full 102 and none is
a differently-sized subset of another.

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

Raw run output (baseline block, abridged — the paired lines are reproduced in
the tables below):

```
prices-2026-08-13.parquet: 913 tickers, 2513 sessions

=== baseline — 102 formation dates ===
  usable tickers/date  min 805  median 861.5  max 903  of 912 screened  (skipped: min 9, max 107)
  fading names/date    min 181  median 290.5  mean 300.4  max 521  = 34.9% of universe
   21d fwd  accel +2.06%  leaders +2.43%  universe +2.14%  fading +2.01%  spread -0.37%
   63d fwd  accel +3.92%  leaders +7.73%  universe +4.34%  fading +3.83%  spread -3.81%
  126d fwd  accel +8.19%  leaders +12.12%  universe +6.68%  fading +5.96%  spread -3.93%
   21d paired accelerating-leaders     median -1.21pp  mean -0.92pp  sd +7.51pp  first-wins 42/102  ties 0
   21d paired accelerating-universe    median +0.48pp  mean +0.30pp  sd +4.77pp  first-wins 54/102  ties 0
   21d paired fading-universe          median -0.04pp  mean +0.11pp  sd +1.31pp  first-wins 48/102  ties 0
   21d paired fading-non_fading        median -0.06pp  mean +0.19pp  sd +2.01pp  first-wins 48/102  ties 0
   21d paired leaders-universe         median +1.43pp  mean +1.22pp  sd +7.54pp  first-wins 59/102  ties 0
   ... (63d and 126d blocks follow the same shape)
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
let the error through. `run_backtest` now computes all of it — every number
in this subsection is read from its output rather than from a side script.

**How to read a hit rate here — one standard, applied to every comparison
below and in §3 and §4.** Overlapping forward windows put the effective
sample at roughly 102, 34 and 17 independent observations at 21d, 63d and
126d (§1). A fair coin tossed that many times lands between 40–60%, 33–67%
and 26–74% of the time respectively, about 95% of the time. **Every hit rate
this study measures, in every cohort comparison, falls between 37.3% and
62.7% — inside the coin-flip band at its own horizon.** No single hit rate
reported anywhere in this document is individually distinguishable from
chance, including the ones supporting the headline. What differs between the
comparisons is only whether the sign is *stable* across horizons, statistics
and parameter settings; that stability, not any individual figure, is the
evidence.

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

**Fading − non-fading**, paired per date. `fading` averages 300.4 names
against a universe averaging 861 — **about 35% of the universe is inside the
`fading` cohort itself**, so "fading − universe" is a cohort measured partly
against itself and is mechanically attenuated toward zero. This row is the
un-overlapped version of the same question. It is a blunter instrument
pointing the same way; no correction to the numbers above is needed, but the
attenuation should be known when reading how small they are:

| Horizon | Median diff | Mean diff | Std dev (dispersion) | Hit rate (fading < non-fading) |
|---|---|---|---|---|
| 21d | -0.06pp | +0.19pp | 2.0pp | 54 / 102 |
| 63d | **+0.15pp** | +0.08pp | 3.5pp | 47 / 102 |
| 126d | -0.07pp | -0.36pp | 4.9pp | 52 / 102 |

**Accelerating − leaders**, paired per date, for comparison against the
headline (§1):

| Horizon | Median diff | Mean diff | Std dev (dispersion) | Hit rate (accel < leaders) |
|---|---|---|---|---|
| 21d | -1.21pp | -0.92pp | 7.5pp | 60 / 102 |
| 63d | -1.41pp | -3.30pp | 14.5pp | 56 / 102 (+2 exact ties) |
| 126d | -5.31pp | -5.35pp | 23.7pp | 64 / 102 |

Reading these together: **accelerating-vs-universe and fading-vs-universe
are both statistically indistinguishable from noise.** Hit rates sit at
51–57% and 46–54% against a 50% coin-flip baseline, medians and means
disagree in magnitude by an order of magnitude or in sign within the same row
(e.g. accelerating-vs-universe at 63d: median +0.03pp but mean +1.73pp, so
the average is carried by a handful of dates rather than the typical one;
fading-vs-universe at 63d: median is *positive* — fading beat the universe on
the median date — while the earlier draft's aggregate-median approach
reported -0.51pp), and dispersion is large relative to the point estimates
(e.g. accelerating-vs-universe at 126d: median +1.34pp against a 16.7pp
standard deviation across only 102 non-independent, overlapping dates). None
of this supports "the score modestly beats the universe" or "the fade flag
has a small, real, growing signal" — both claims in earlier drafts, both now
withdrawn.

**Accelerating-vs-leaders (the actual headline) differs in degree, not in
kind, and the difference is consistency rather than significance.** Its
per-date hit rates against the leader control are 58.8%, 54.9% and 62.7% —
**above half at every horizon, but not increasing with horizon; the 3-month
figure dips below the 1-month one.** (An earlier draft described this as "a
hit rate that climbs with horizon," which the numbers it cited do not show.
There is no horizon trend here to explain.)

Applying the one standard set out above, honestly and in both directions:
**58.8/54.9/62.7% is inside the coin-flip band for its effective sample size,
exactly as 51–57% and 46–54% are.** An earlier draft called 56/102 at 63d "a
materially different picture" two paragraphs after dismissing 52–58/102 as
noise; those are the same magnitude and that was two standards, not one. That
judgement is withdrawn. What actually separates the leader comparison from
the universe comparisons is none of the following — not significance, not
effect size on any single date — but this:

- median and mean **agree in sign** at all three horizons (the universe
  comparisons disagree in relative magnitude at 63d and in sign at 126d);
- the sign holds in **all 18** variant-horizon cells of the parameter sweep,
  on the paired measure and the unpaired one alike (§3);
- the point estimates are an order of magnitude larger (-1.21/-1.41/-5.31pp
  versus +0.48/+0.03/+1.34pp).

Unanimity across 36 paired point estimates is the entire case. Any one of
them, read alone, is noise — and §1's phrasing ("failed to demonstrate an
edge") is chosen to claim no more than that.

*Why mean survived unpaired but median didn't:* mean is a linear
statistic, so `mean(A) − mean(B) == mean(A − B)` always holds — a
difference-of-means is automatically a mean-of-differences, paired or not.
Median has no such identity. That is precisely why the mean-based spread
figures reported throughout this document (e.g. -0.92 / -3.30 / -5.35pp in
§1) needed no correction, while every median-based cross-cohort comparison
did.

## 3. Parameter sweep

All six variants, accelerating − leaders at each horizon, from the actual
run. **Earlier drafts gave only the first of these three columns per horizon
— the unpaired aggregate-median spread — while §1 and §6 leaned on "zero of
18 positive" as a robustness pillar. That was the same unpaired construction
this document condemns elsewhere, applied to its own robustness check.** The
paired columns were added in round three. The conclusion survives: in all 18
cells, the paired median *and* the paired mean are negative, and the
accelerating cohort loses to leaders on a majority of individual formation
dates.

| Variant | Horizon | Unpaired spread | Paired median | Paired mean | Accel loses on |
|---|---|---|---|---|---|
| baseline | 21d | -0.37pp | -1.21pp | -0.92pp | 60 / 102 |
| baseline | 63d | -3.81pp | -1.41pp | -3.30pp | 56 / 102 |
| baseline | 126d | -3.93pp | -5.31pp | -5.35pp | 64 / 102 |
| strict 1m gate (`min_1m_return=0.0`) | 21d | -0.37pp | -0.64pp | -1.13pp | 57 / 102 |
| strict 1m gate | 63d | -3.71pp | -1.50pp | -3.46pp | 57 / 102 |
| strict 1m gate | 126d | -3.46pp | -5.61pp | -4.94pp | 65 / 102 |
| no 1m gate (`min_1m_return=-1.0`) | 21d | -0.37pp | -1.21pp | -0.92pp | 60 / 102 |
| no 1m gate | 63d | -3.81pp | -1.41pp | -3.28pp | 57 / 102 |
| no 1m gate | 126d | -3.93pp | -5.31pp | -5.20pp | 64 / 102 |
| 6m recent window | 21d | -0.20pp | -0.54pp | -1.12pp | 54 / 102 |
| 6m recent window | 63d | -0.98pp | -1.92pp | -2.37pp | 57 / 102 |
| 6m recent window | 126d | -1.24pp | -4.10pp | -3.90pp | 63 / 102 |
| no vol normalization | 21d | -0.24pp | -0.37pp | -0.32pp | 55 / 102 |
| no vol normalization | 63d | -2.43pp | -1.78pp | -2.74pp | 56 / 102 |
| no vol normalization | 126d | -4.55pp | -4.27pp | -4.39pp | 58 / 102 |
| strength floor 15% (`min_recent_return=0.15`) | 21d | -0.39pp | -1.21pp | -1.06pp | 60 / 102 |
| strength floor 15% | 63d | -4.02pp | -1.65pp | -3.34pp | 58 / 102 |
| strength floor 15% | 126d | -3.10pp | -5.31pp | -5.40pp | 63 / 102 |

("Accel loses on" counts dates where the accelerating cohort's forward return
was strictly below the leaders'; the remainder are wins plus a small number
of exact ties, 0–3 per cell, reported in the run output.)

**Zero of the 18 (6 variants × 3 horizons) spread values were positive — on
the unpaired measure and on both paired measures alike: 36 of 36 paired point
estimates are negative, and the accelerating cohort loses on 54 to 65 of 102
dates in every single cell.** No variant beat the 12-month leader cohort at
any horizon, so there is no cherry-picked "winning" configuration to report —
the sweep is six genuinely distinct conditions tried against the same 102
formation dates and same three horizons, and that width is itself a
multiple-comparisons exposure worth naming even though, in this case, it
produced no false positive to guard against. Note also that the six variants
are not independent trials: they share a universe, a snapshot and 102
formation dates, and four of them differ from baseline only in a gate value,
so unanimity across them is weaker evidence than 18 independent replications
would be. It is still the strongest thing in this study.

### The one-month gate (design spec §2.2): does the floor bind? — corrected

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
at 21d, 5.04% vs. 5.06% at 63d, 10.27% vs. 10.42% at 126d (all six values
read directly from `backtest-results.json`, no re-run needed). Small
differences, but they are there, and the median genuinely is not — this is
the same median-vs-mean sensitivity gap as the paired-comparison finding in
§2, appearing here as a second, independent line of evidence for the same
underlying fact: **the aggregate median statistic this study leans on is
frequently blind to real changes that the mean, or a proper per-date pairing,
can see.**

### The strict gate's effect — a third instance of the unpaired error, corrected

**Every draft of this document up to and including round two closed this
section by concluding "the prediction was wrong — in the opposite
direction," on the strength of these two lines:**

> the strict gate (`min_1m_return=0.0`) modestly *helped* on the aggregate
> median: 63d accelerating median rose from +3.92% (baseline) to +4.02%,
> spread improved from -3.81pp to -3.71pp; 126d rose from +8.19% to +8.66%,
> spread improved from -3.93pp to -3.46pp; 21d unchanged.

**Those four numbers are arithmetically correct and the conclusion drawn from
them is not supported.** They compare two separately-aggregated medians from
two runs over the same 102 formation dates — the identical construction this
document condemns in §2, §4 and §5, here making its third appearance, in the
one section written specifically to correct the first two. It was caught only
at final whole-branch review. See the correction note at the top: this is the
clearest evidence available that the unpaired shortcut is a property of the
tooling, not of the author's attention.

Paired per formation date, `min_1m_return=0.0` minus `min_1m_return=-0.15`,
on the accelerating cohort's own forward return (computed from
`backtest-results.json`'s per-date series, which the harness now retains
precisely so a cross-run pairing like this needs no side script):

| Horizon | Paired median | Paired mean | Std dev | Strict better | Baseline better | Identical |
|---|---|---|---|---|---|---|
| 21d | 0.000pp | -0.21pp | 2.1pp | 16 / 102 | 20 / 102 | 66 / 102 |
| 63d | 0.000pp | -0.16pp | 3.7pp | 19 / 102 | 16 / 102 | 67 / 102 |
| 126d | 0.000pp | +0.41pp | 4.3pp | 22 / 102 | 14 / 102 | 66 / 102 |

The median effect is **exactly zero at every horizon** — on two thirds of
formation dates the two settings produce an identical cohort return — and the
mean effect changes sign across horizons on a base of 14–22 dates either way.
This is not a "modest help." It is not distinguishable from noise.

And on the paired accelerating − leaders spread, the strict gate is *worse*
at exactly the two horizons the old text cited as improvements:

| Horizon | Baseline (paired median) | Strict gate (paired median) |
|---|---|---|
| 21d | -1.21pp | **-0.64pp** (better) |
| 63d | -1.41pp | **-1.50pp** (worse) |
| 126d | -5.31pp | **-5.61pp** (worse) |

So the unpaired reading and the paired reading do not merely differ in
magnitude here — they point in opposite directions at 63d and 126d, which is
where the old conclusion came from.

**The supportable statement: the one-month floor's effect on forward
performance is not distinguishable from noise, and design spec §2.2's
prediction — that a strict positive-1m gate should *hurt*, because
short-horizon returns reverse — is neither confirmed nor refuted by this
study.** It is not that the prediction was tested and failed; it is that this
study cannot resolve an effect this small. Anyone wanting to settle §2.2
needs a design built for it, not a six-cell parameter sweep read off medians.

This is not a case of the gate being inert. Re-classifying every ticker at
every formation date under `min_1m_return=0.0` versus baseline (same method
as the mechanism analysis above), the strict gate changes the eligible
accelerating set on **102 of 102** formation dates and the ranked top-15
cohort on **56 of 102** — far more binding than removing the floor entirely,
which moved the cohort on 7. The gate moves the portfolio on more than half
the dates in the sample and still moves the measured outcome by a median of
exactly zero. That is the finding: a real change in holdings that does not
show up in forward return at this sample size.

The sweep's six configurations are genuinely distinct conditions, not a
baseline-vs-strict-gate binary; there is no single "the informative
comparison," and treating one as such was itself part of the original error.

## 4. Does the fade flag work? — corrected in rounds one, two and three

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
leaders cohorts. It is not directly size-comparable to those two. (These
counts now come from the harness — `run_backtest` reports per-date cohort
sizes — rather than from the ad-hoc analysis that produced them in earlier
drafts.)

**A consequence of that size, which the fading-vs-universe numbers below
require to read correctly: at a mean of 300.4 names against a mean universe
of 861, the fading cohort is about 35% of its own control.** A third of
"universe" *is* "fading", so the difference between them is attenuated toward
zero for a purely mechanical reason, independent of whether the fade label
predicts anything. The un-overlapped comparison (fading versus non-fading,
§2) is the blunter but cleaner instrument: -0.06 / +0.15 / -0.07pp on the
paired median, with fading below non-fading on 54 / 47 / 52 of 102 dates —
the same conclusion, slightly larger magnitudes, same coin-flip hit rates.
No correction to the numbers below is warranted; the caveat is simply that
"fading − universe" understates whatever is there, and what is there is
nothing.

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
47–54 out of 102, which is within noise of a coin flip by the standard set
in §2. The un-overlapped fading-vs-non-fading comparison agrees. There is
nothing here to report as a finding beyond "not distinguishable from noise,
at this sample size, with this methodology."

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
occasionally a data gap). Measured across the 102 formation dates, against
the correct denominator of **912 non-benchmark tickers** (the harness
excludes only the return benchmark, SPY — QQQ remains in the
universe/leaders/accelerating/fading pools):

**Disclosure:** in earlier drafts these counts came from ad-hoc analysis, not
from the harness — design spec §5 asks the study to "report how many were
skipped" and the harness did not. It does now: `run_backtest` emits
`screened`, per-date cohort `sizes` and `skipped`, and prints the summary
line reproduced in §2. The figures below are unchanged by that move; they are
simply reproducible now (skipped per date: minimum 9, maximum 107).

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
document's headline statistic needed a paired companion, and three separate
conclusions were decided by the shortcut before anyone caught it.** §3 shows
a median-of-102-medians can be completely blind to a change (the one-month
gate) that demonstrably alters the ranked cohort on 7 of 102 dates, because
the change never happens to move the 51st/52nd order statistic. §2, §3 and §4
show that comparing two cohorts' separately-aggregated medians (rather than
pairing per formation date and aggregating the differences) can flip the sign
of the conclusion outright — twice between cohorts, once between two
parameter settings. All of it shares a root cause: **median is not linear, so
operations that are safe on means (subtraction, in particular) are not safe
on medians.**

**The strongest evidence for this caveat is the history of the document
itself.** Rounds one and two diagnosed this exact error, named it, explained
the mechanism, and wrote the lesson down — and round three still found a
third live instance of it two sections away, plus an entire 18-cell
robustness table computed the unpaired way. Being able to state the rule is
demonstrably not sufficient to follow it. What was missing was a tool that
made the correct comparison the easy one, which is why round three changed
`run_backtest` rather than only the prose. Anyone extending this backtest
should use `paired[h]` and report hit rate and dispersion (design spec §4.2
already requires this), and should never compare cohorts via the difference
of two independently computed aggregate statistics — the mean is forgiving of
that shortcut, the median is not.

**Statistical power, stated so the headline is not over-read.** Formation
dates step 21 trading days against horizons of up to 126, so roughly
`horizon / step` consecutive dates share most of their forward window:
effective N is about 102, 34 and 17, not 102 three times over. At those
sample sizes the paired accelerating − leaders means (-0.92 / -3.30 /
-5.35pp against standard deviations of 7.5 / 14.5 / 23.7pp) carry standard
errors of roughly 0.7 / 2.5 / 5.8pp, i.e. |t| ≤ 1.4 at every horizon.
**Nothing in this study reaches conventional significance, in either
direction.** Read naively at N=102 the 63d and 126d figures would show t ≈
-2.3 and look decisive; that is precisely the reading the overlap forbids.
The correct summary is that the acceleration score **failed to demonstrate an
edge over the control**, not that it was shown to destroy value. That
distinction does not change the Phase 2 recommendation — a score that cannot
demonstrate an edge over the incumbent rank should not replace the incumbent
rank — but it is the claim the evidence supports, and it is the one this
document makes.

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

**`backtest-results.json` does not round-trip its horizon keys.** The
`cohorts`, `spread_vs_leaders`, `paired` and `per_date` dicts are keyed by
the integer horizons (21, 63, 126); `json.dumps` stringifies them, so a plain
`json.loads` of the artifact yields string keys ("21", "63", "126"), not
ints. Anything reading the artifact must index with strings.

*Resolved in round three:* the JSON previously stored only each cohort's
already-aggregated median/mean per horizon, so the paired comparisons in §2,
§3 and §4 could not be reproduced from it at all — they came from an ad-hoc
script that was never committed. `run_backtest` now persists `paired`
(median, mean, sd, wins, ties per cohort pair) and `per_date` (the raw
per-formation-date series for every cohort) alongside `positions`, so both
within-run pairings and cross-run pairings such as §3's gate comparison are
recomputable from the artifact. This was §6(c)'s recommendation for a future
phase; it was done now instead, because the deliverable's best evidence being
unregenerable is not a defect that should be deferred.

**The parameter sweep never varies cohort size.** Design spec §4.3 lists N
(cohort size) among the parameters the study should settle empirically
alongside `min_recent_return`, `min_1m_return`, recent window, and
volatility normalization. `SWEEP` in `tools/backtest_momentum.py` does not
include an N variant — every run uses the default `n_cohort=15`. This is an
omission relative to the spec, not a finding; whether a smaller or larger
cohort changes the spread (or the gate-sensitivity issue in §3, or the
fading-cohort deviation above) is untested.

**Two producer-side hazards in `vantage/momentum.py`, found at final review
and fixed — flagged here because Phase 2 is the caller that would have hit
them.** Neither changes any number in this document (verified: the full sweep
reproduces identically after the fix), because the backtest harness happens
not to reach either path.

1. **`classify()` could return a non-finite `score`.** A `nan` metric yielded
   `label="steady", score=nan`; an `inf` metric yielded
   `label="accelerating", score=inf`; `volatility=nan` yielded `score=nan`
   and `volatility=inf` yielded `score=0.0`; a negative volatility silently
   inverted the score's sign. `score` is a **sort key**: an `inf` sorts to the
   top of a ranked list and a `nan` makes the ordering undefined. The
   backtest defended itself with an `np.isfinite` check at the consumer, but
   Phase 2's `screener.py` will rank on `score` without inheriting that guard.
   The checks are now at the producer (design spec §5's contract), and the
   consumer-side guard is deliberately kept.
2. **`_paces()` mixed partial benchmarks.** It adjusted per window, so a
   benchmark dict missing one window produced a gap that was neither the
   excess answer nor the raw one, while `benchmark_adjusted` still reported
   `True`. No caller in this study reaches it (`metrics_at` returns all four
   windows or `None`) — but **`screener.py` drops individual metric keys that
   fail its plausibility filter, which produces exactly those partial dicts**,
   so Phase 2 would have hit it on the first implausible reading. A partial
   benchmark now degrades to fully raw returns and says so.

**Other caveats, standard for this kind of study:**
- Overlapping forward windows (21-day formation step against up to 126-day
  forward horizons) mean consecutive formation dates share most of their
  return history — they are not independent observations, and the
  "102 formation dates" figure overstates effective sample size, by roughly
  `horizon / step` (see "Statistical power" above: effective N ≈ 102 / 34 /
  17). This also means the hit-rate and dispersion figures in §2/§3/§4, while
  a large improvement on an unpaired aggregate, are still not a clean
  statistical test — 102 correlated dates carry less information than 102
  independent ones.
- No transaction costs, slippage, or position sizing; cohort returns are
  equal-weighted medians (and, where reported, means) of a hypothetical
  instantaneous entry.
- One market regime (2016–2026, a long bull market punctuated by the 2020
  and 2022 drawdowns), one universe (US large/mid-cap index constituents),
  one country.

`cache/` is git-ignored, so neither the parquet snapshot nor
`backtest-results.json` is committed alongside this document — every number
above was transcribed by hand from the actual run's console output or the
JSON artifact's numeric fields, not regenerated or estimated. Two exceptions,
both flagged where they appear: §3's re-classification of the gate's
mechanism (which name-dates the floor excludes, and which dates the ranked
cohort differs on) and §5's fully-gapless-ticker count come from direct
analysis of the snapshot rather than from the harness, because the harness is
not built to answer either question. Everything else, including every paired
statistic, is now regenerable by re-running `tools/backtest_momentum.py`
against the same snapshot.

## 6. Recommendation for Phase 2

**The score does not beat 12-month momentum in this backtest, and that
result is robust.** It holds on the aggregate median (-0.37 / -3.81 /
-3.93pp), the aggregate mean (-0.92 / -3.30 / -5.35pp), and the paired
per-date median (-1.21 / -1.41 / -5.31pp, with accelerating losing on the
majority of individual dates at every horizon: 60/102, 56/102, 64/102).
Three different ways of measuring "does accelerating beat leaders" agree in
sign at every horizon. All six parameter variants agree too — **zero of 18
variant-horizon combinations showed a positive spread, on the unpaired
measure and on the paired median and paired mean alike: 36 of 36 paired point
estimates negative, with accelerating losing on 54–65 of 102 dates in every
cell** (§3; earlier drafts asserted this pillar from the unpaired column
only, and it has now been checked properly rather than assumed).

**Do not soften this. It should also not be over-extended.** Two things are
being claimed and one is not. What is claimed: the sign is unanimous across
every statistic, horizon and configuration tried. What is *not* claimed:
statistical significance. At an effective sample of ~17–34 independent
observations, no individual figure here — including the ones supporting the
headline — is distinguishable from chance (§1, §5). The honest formulation is
that the acceleration score **failed to demonstrate an edge over the control
it would have to beat to be worth shipping**, not that it was shown to be
harmful. That is a sufficient basis for the recommendation below: a score
that cannot demonstrate an edge over the incumbent rank has not earned the
right to replace it.

Earlier drafts additionally claimed the acceleration score "modestly beats
the plain universe," that the fade flag shows "a small but real,
horizon-growing signal," and that a strict one-month gate "modestly helped."
All three relied on the same invalid unpaired-median comparison and none
survives the paired correction (§2, §3, §4): accelerating-vs-universe and
fading-vs-universe hit rates sit at 46–57% (coin-flip range) with signs that
flip between median and mean within the same horizon, and the strict gate's
paired effect on the accelerating cohort's own forward return is a median of
exactly 0.00pp at all three horizons. **Neither the score's apparent edge
over the universe, nor the fade flag's apparent signal, nor the one-month
gate's apparent effect is distinguishable from noise in this study.** Every
secondary claim once layered on top of the headline has now been withdrawn;
the headline is what is left, and it is the comparison Vantage actually cares
about.

Recommend that **Phase 2 present momentum term structure as description
only** — "this name's recent pace versus its own longer-run pace," framed
as context alongside the existing 12-month rank — **and make no claim that
the acceleration score beats, replaces, or should reorder the trailing
12-month leader ranking, and no claim that either the acceleration score or
the fade flag carries a demonstrated edge over the plain universe.** Do not
use either as a standalone ranking or forward-return signal for surfacing
purposes.

**Before Phase 2 writes any code against `vantage/momentum.py`, read §5's
"two producer-side hazards."** Both were found at final review of this
branch and both are now fixed, but one of them (`_paces` mixing partial
benchmarks) is triggered specifically by `screener.py`'s habit of dropping
individual metric keys that fail its plausibility filter, and the other
(non-finite `score`) is triggered by ranking on `score` — which is exactly
what Phase 2's `accel_leader` list would do. Phase 2 should keep its own
finiteness check at the point of ranking regardless; defense in depth is
correct for a value that decides sort order.

If a future phase wants to revisit prediction more rigorously, it should
(a) do so against a point-in-time (non-survivorship-biased) universe, since
that bias runs in the direction that would make this already-negative
result look better, not worse, than a clean sample would show; (b) sweep
cohort size N, per spec §4.3, which this study did not, and resolve the
fading-cohort's deviation from spec §4.1 (§5) if a ranked cohort is wanted;
and (c) size the study for the question — 102 overlapping formation dates are
~17 independent observations at the 6-month horizon, which cannot resolve
effects of the size this study is looking for, and no amount of careful
aggregation fixes that.

*(c) previously read "build paired per-date comparison into the harness
itself from the start, rather than as a post-hoc script." **That was done in
round three rather than deferred**, for the reason the recommendation itself
gave: a harness that only ever produces separately-aggregated medians will
keep inviting the same mistake — and it did, a third time, in this very
document. `run_backtest` now emits paired medians/means/dispersion, per-date
hit rates against the universe baseline, per-date series for cross-run
pairing, and per-date skipped-ticker counts, per design spec §4.2 and §5.)*
