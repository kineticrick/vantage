# Finding: does trajectory discriminate *among* leaders, and does sector breadth predict?

**Date:** 2026-08-14
**Parent study:** `docs/superpowers/findings/2026-08-13-momentum-backtest.md`
**Tooling:** `tools/backtest_conditional.py` → `tools/analyze_conditional.py`
**Snapshot:** `cache/history/prices-2026-08-13.parquet` — 913 tickers
(912 non-benchmark), 2,513 sessions, 2016-08-15 → 2026-08-13.
**Sectors:** `cache/sectors.json` — 915 tickers, 12 sectors.
**Run:** `.venv/bin/python tools/backtest_conditional.py`, defaults
(`MomentumParams()`, `top_n=30`, `cohort_n=15`, `benchmark="SPY"`,
`horizons=(21, 63, 126)`, `step=21`) — 102 formation dates, 2017-08-15
through 2026-01-23.

`vantage/momentum.py` was not modified by this study.

## 0. Headline

**Both hypotheses came out null, and the coordinator's pre-registered
prediction — that both would — held.**

- **Experiment 1 (conditional):** among the top 30 by trailing 12-month
  return, ranking by trajectory score and racing the top 15 against the bottom
  15 produces paired medians of **-0.36 / +0.81 / -0.92pp** at 21/63/126 days,
  with the high-trajectory half winning on **50 / 54 / 50 of 102** formation
  dates. The sign is not stable across horizons, the median and the mean
  disagree in sign at 126d, and no hit rate is distinguishable from a coin
  flip (|z| ≤ 0.34 at effective N). **Trajectory does not discriminate among
  leaders.**
- **Experiment 2 (sector breadth):** sectors ranked by `accelerating_share`,
  top 3 against bottom 3, give paired medians of **-0.22 / -0.77 / -0.58pp**
  with the high-breadth side winning **48 / 45 / 45 of 102** dates. Ranked
  instead by `median_score`: **+0.23 / -0.35 / +0.01pp**, winning **53 / 47 /
  51 of 102**. **Sector acceleration breadth does not predict sector forward
  returns**, on either ordering.
- **Zero of the 30 pre-registered comparisons reaches |z| ≥ 1.96 or
  |t| ≥ 1.96** at the effective sample size. The largest is a hit rate of
  43/102 (z = -1.58) — and it points the *wrong* way for the hypothesis.

**The only thing in this study that is nominally significant is a post-hoc
positive control, and it belongs to the incumbent.** The top-30 12-month
leader cohort beats the plain universe by paired medians of **+1.55 / +2.92 /
+6.10pp**, winning on **65 / 65 / 73 of 102** dates (21d z = +2.77, two-sided
p ≈ 0.006; 126d t = +2.20, p ≈ 0.04). That replicates the parent study's one
resolvable effect, on a different cohort definition (top 30, not top 15). It
is stated here with its multiple-comparisons context immediately attached, in
§5, not in a footnote: **it does not clear a Bonferroni threshold over this
study's own 33 tests** (which would require |z| ≥ 3.17), and it is one
comparison out of 66 run across the two phases of this project.

## 1. The two pre-registered hypotheses

Stated as they were before the run, and unaltered afterwards.

**H1 — conditional.** The parent study asked "does acceleration beat 12-month
rank across the whole market" and answered no. It did not ask the conditional
question: *given* a stock is already a 12-month leader, does its trajectory
tell you which leaders do better? At each formation date, take the top 30 by
trailing 12-month return. Among those 30, rank by trajectory `score` and form
two cohorts of 15 — `leaders_hi_traj` (highest scores) and `leaders_lo_traj`
(lowest). Compare forward returns paired per date at 21/63/126 days. If
trajectory discriminates within leaders, hi beats lo. Leaders whose `score` is
`None` or non-finite are excluded from the ranking, and the number dropped is
reported per date.

*Secondary cross-check (not the primary):* split the same top 30 by **label**
into `leaders_accelerating` and `leaders_fading`. Sizes vary per date and are
reported.

**H2 — sector breadth.** `sector_breadth()` was built and never validated. At
each formation date, classify every ticker, compute `sector_breadth` over the
full universe, rank sectors by `accelerating_share`, and form `hi_breadth` (all
names in the top 3 sectors) and `lo_breadth` (all names in the bottom 3).
Compare each against the other and against the universe, paired per date, at
all three horizons. Repeat the ranking by `median_score` as a second ordering
of the same idea. Exclude the `Unknown` sector and any sector with fewer than
10 classified names at a given date.

**The coordinator's pre-registered prediction: both null.**

## 2. Method, in plain language

Identical formation grid and screen to the parent study: 102 formation dates
stepping 21 trading days, a ticker admitted at a date only if all four trailing
windows (1m/3m/6m/12m) are usable, forward return measured as the cohort's
equal-weighted **median** at each horizon. SPY is the benchmark and is excluded
from every cohort; QQQ has no entry in `cache/sectors.json`, so it is
automatically outside every sector cohort.

Universe per date: **min 805, median 861.5, max 903** of 912 screened
(skipped: min 9, max 107) — identical to the parent study, as it must be, since
the screen is the same code.

**Every cross-cohort comparison in this document is paired per formation
date.** The parent study's central methodological lesson is that a difference
of two separately-aggregated medians is not the median of the per-date
differences, and that it published that error three separate times. This
harness therefore computes no aggregate cross-cohort difference at all — there
is a test asserting that no such key exists in its output. The per-cohort
aggregate medians in `backtest-conditional-results.json` are for orientation
only and must not be subtracted from one another.

**Statistical context, applied identically to every row.** Formation dates step
21 trading days against horizons up to 126, so consecutive dates share most of
their forward window and effective N is roughly **102 / 34 / 17**, not 102
three times. Every `z` and `t` below is computed at that effective N. A fair
coin over 102/34/17 tosses lands between 40–60%, 33–67% and 26–74% about 95% of
the time.

## 3. Experiment 1 — trajectory within the leaders

### 3.1 Drop counts — the qualification that did not materialize

Leaders excluded from the score ranking because `score` was `None` or
non-finite, per date: **minimum 0, median 0, maximum 0, of 30.**

**Not one leader was dropped on any of the 102 formation dates.** So both
cohorts are genuinely drawn from a full top 30, both are exactly 15 names on
every date, and their union is exactly the top 30. The pre-registration
required this to be reported precisely because a large drop count would have
qualified the result; it does not, and the result needs no such qualification.

(The harness still guards the case: if drops ever left fewer than 30 rankable
leaders, both halves shrink to `len(scored) // 2` rather than overlapping, since
`scored[:15]` and `scored[-15:]` over fewer than 30 names would share members
and drive the measured difference toward zero while still looking like two
15-name cohorts. The guard is tested and never fired here.)

Cohort sizes per date:

| Cohort | min | median | mean | max | empty on |
|---|---|---|---|---|---|
| `leaders_top30` | 30 | 30 | 30.0 | 30 | 0 dates |
| `leaders_hi_traj` | 15 | 15 | 15.0 | 15 | 0 dates |
| `leaders_lo_traj` | 15 | 15 | 15.0 | 15 | 0 dates |
| `leaders_accelerating` | 3 | 15 | 14.6 | 27 | 0 dates |
| `leaders_fading` | 0 | 10 | 10.4 | 26 | **1 date** |

The one date with no fading leader is why the secondary comparison runs on 101
dates rather than 102.

### 3.2 Primary result — `leaders_hi_traj` − `leaders_lo_traj`, paired

| Horizon | Paired median | Paired mean | Std dev | Hi wins on | Hit-rate z | Mean t |
|---|---|---|---|---|---|---|
| 21d | -0.36pp | -0.51pp | 5.80pp | 50 / 102 (49.0%) | -0.20 | -0.89 |
| 63d | +0.81pp | +0.05pp | 14.14pp | 54 / 102 (52.9%) | +0.34 | +0.02 |
| 126d | -0.92pp | +1.28pp | 23.38pp | 50 / 102 (49.0%) | -0.08 | +0.22 |

**Null on every reading available.** The sign flips across horizons on the
median (−, +, −). The median and mean disagree in sign at 126d. Hit rates are
49.0%, 52.9% and 49.0% against a coin-flip baseline, all deep inside the band
for their own effective sample. Dispersion dwarfs the point estimates at every
horizon (a -0.92pp median against a 23.38pp standard deviation at 126d).

This is *not* the pattern the parent study called evidence. There, the case
rested on 36 of 36 paired point estimates sharing a sign across three
statistics, three horizons and six configurations. Here six point estimates
across three horizons do not even agree with each other.

### 3.3 Each half against the full top 30

Context, not a separate hypothesis — and mechanically near-mirrored, since the
two halves partition the top 30:

| Comparison | 21d | 63d | 126d |
|---|---|---|---|
| `hi_traj` − `top30` median | -0.12pp | +0.28pp | -0.17pp |
| `hi_traj` − `top30` wins | 50/102 | 54/102 | 50/102 |
| `lo_traj` − `top30` median | +0.13pp | -0.24pp | +0.19pp |
| `lo_traj` − `top30` wins | 52/102 | 48/102 | 52/102 |

Neither half is distinguishable from simply holding all 30. If trajectory
carried information within the leader set, one of these two rows would separate
from the other; they do not.

### 3.4 Secondary cross-check — the same 30 split by label

| Horizon | Paired median | Paired mean | Std dev | Accel wins on | z | t |
|---|---|---|---|---|---|---|
| 21d | -0.54pp | +0.22pp | 8.04pp | 50 / 101 (49.5%) | -0.10 | +0.27 |
| 63d | **+2.68pp** | +0.21pp | 17.86pp | 53 / 101 (52.5%) | +0.29 | +0.07 |
| 126d | -0.59pp | +1.70pp | 26.23pp | 49 / 101 (48.5%) | -0.12 | +0.27 |

The 63d paired median of **+2.68pp** is the largest single figure in either
experiment and it is worth saying explicitly why it is not a result: its own
paired mean is +0.21pp, an order of magnitude smaller, and the accelerating
side wins on 53 of 101 dates (z = +0.29). A median that large beside a mean
that small means the typical date's advantage is not backed by the average
date's — and at 21d and 126d the median and mean point in opposite directions
outright. Cohort sizes also vary from 3 to 27 names per date on the
accelerating side and 0 to 26 on the fading side, so the comparison is between
two moving targets. It is a cross-check and it agrees with the primary: null.

## 4. Experiment 2 — sector acceleration breadth

### 4.1 What was ranked

11 sectors were eligible on every one of the 102 dates (`Unknown` — a single
ticker, FISV — excluded by design; the 10-classified-name floor never bound on
any real sector). Top-3 and bottom-3 never overlapped on any date.

Cohort sizes per date:

| Cohort | min | median | mean | max |
|---|---|---|---|---|
| `hi_breadth_accel` | 115 | 254 | 252.3 | 427 |
| `lo_breadth_accel` | 107 | 192.5 | 197.7 | 412 |
| `hi_breadth_score` | 109 | 215.5 | 226.0 | 414 |
| `lo_breadth_score` | 108 | 201.5 | 224.5 | 427 |

**These are large cohorts — roughly a quarter to a third of the universe each,
and together about half of it.** That means `hi_breadth − universe` and
`lo_breadth − universe` are each a cohort measured partly against itself, and
are mechanically attenuated toward zero for reasons independent of whether
breadth predicts anything. This is exactly the hazard the parent study
documented for its `fading` cohort (35% of its own control), and the fix is the
same: **`hi_breadth − lo_breadth` is the un-overlapped comparison and the one
to read.** The against-universe rows are reported because the pre-registration
asked for them, with the attenuation named.

How often each sector landed in the top 3, by `accelerating_share`:
Technology 40, Industrials 39, Utilities 32, Financial Services 30,
Healthcare 29, Energy 27, Basic Materials 26, Communication Services 24,
Real Estate 23, Consumer Cyclical 18, Consumer Defensive 18. Bottom 3:
Energy 50, Utilities 49, Real Estate 46, Basic Materials 28, Financial
Services 24, Consumer Defensive 24, Communication Services 21, Healthcare 18,
Technology 16, Industrials 16, Consumer Cyclical 14. **No sector dominates
either end**, so this is not a disguised bet on one or two sectors — which is
what would have made the test uninterpretable.

### 4.2 Ranked by `accelerating_share`

| Comparison | Horizon | Paired median | Paired mean | Std dev | First wins | z | t |
|---|---|---|---|---|---|---|---|
| hi − lo | 21d | -0.22pp | -0.12pp | 3.86pp | 48/102 (47.1%) | -0.59 | -0.32 |
| hi − lo | 63d | -0.77pp | -0.44pp | 5.87pp | 45/102 (44.1%) | -0.69 | -0.44 |
| hi − lo | 126d | -0.58pp | -0.22pp | 8.10pp | 45/102 (44.1%) | -0.49 | -0.11 |
| hi − universe | 21d | -0.22pp | -0.07pp | 2.20pp | 43/102 (42.2%) | -1.58 | -0.30 |
| hi − universe | 63d | -0.14pp | -0.20pp | 3.61pp | 49/102 (48.0%) | -0.23 | -0.32 |
| hi − universe | 126d | -0.40pp | -0.37pp | 4.40pp | 44/102 (43.1%) | -0.57 | -0.35 |
| lo − universe | 21d | +0.06pp | +0.06pp | 2.22pp | 53/102 (52.0%) | +0.40 | +0.26 |
| lo − universe | 63d | +0.58pp | +0.25pp | 3.53pp | 55/102 (53.9%) | +0.46 | +0.41 |
| lo − universe | 126d | +0.00pp | -0.15pp | 5.69pp | 51/102 (50.0%) | +0.00 | -0.11 |

**Null — and one thing in it must be named rather than buried.** The
`hi − lo` and `hi − universe` rows are negative on the median *and* the mean at
all three horizons: 12 of 12 point estimates share a sign, and the sign is the
**opposite** of the hypothesis. High acceleration breadth was followed by
slightly *worse* sector returns, not better.

The parent study treated exactly this kind of unanimity (36 of 36) as its
strongest evidence, so the consistency cannot be waved away on principle. Three
things stop it from being a finding here, and they are stated together so the
reader can weigh them:

1. **Magnitude.** The largest is -0.77pp on a 5.87pp standard deviation. The
   parent's unanimous estimates ran -1.21 to -5.61pp.
2. **Count.** 12 point estimates over 3 nested horizons and 2 overlapping
   comparisons, versus 36 over 6 distinct parameter configurations.
3. **The second ordering does not agree.** `median_score` (§4.3) is the same
   idea ranked a different way and shows no sign consistency at all. If high
   breadth genuinely preceded underperformance, the second ordering of breadth
   ought to see some of it.

Every hit rate here sits between 42.2% and 53.9%, inside the coin-flip band for
its horizon. The honest statement is: **no effect was demonstrated in either
direction, and the study is not powered to claim that high breadth is actively
bad.** It is named here because pre-registering a test and then declining to
report an inconvenient consistency in its output is precisely the failure mode
this project has been correcting for two rounds.

### 4.3 Ranked by `median_score`

| Comparison | Horizon | Paired median | Paired mean | Std dev | First wins | z | t |
|---|---|---|---|---|---|---|---|
| hi − lo | 21d | +0.23pp | -0.08pp | 3.72pp | 53/102 (52.0%) | +0.40 | -0.21 |
| hi − lo | 63d | -0.35pp | -0.25pp | 6.41pp | 47/102 (46.1%) | -0.46 | -0.23 |
| hi − lo | 126d | +0.01pp | +0.71pp | 9.02pp | 51/102 (50.0%) | +0.00 | +0.33 |
| hi − universe | 21d | +0.07pp | +0.06pp | 2.42pp | 52/102 (51.0%) | +0.20 | +0.25 |
| hi − universe | 63d | -0.31pp | +0.12pp | 4.49pp | 47/102 (46.1%) | -0.46 | +0.16 |
| hi − universe | 126d | -0.12pp | +0.40pp | 5.89pp | 50/102 (49.0%) | -0.08 | +0.28 |
| lo − universe | 21d | -0.11pp | +0.14pp | 2.07pp | 48/102 (47.1%) | -0.59 | +0.67 |
| lo − universe | 63d | +0.33pp | +0.37pp | 3.29pp | 56/102 (54.9%) | +0.57 | +0.66 |
| lo − universe | 126d | +0.26pp | -0.31pp | 4.98pp | 52/102 (51.0%) | +0.08 | -0.26 |

**Null, and messier than §4.2:** median and mean disagree in sign in 5 of 9
rows, the `hi − lo` median changes sign twice across three horizons, and every
hit rate is between 46.1% and 54.9%. A paired median of **+0.01pp** at 126d is
about as close to literally nothing as this harness can produce.

### 4.4 How independent are the two orderings?

Measured directly: the two rankings select the **same 1.91 of 3 top sectors**
on the average date (identical on 21 dates, disjoint on 3) and the same 1.85 of
3 bottom sectors. They are correlated orderings, not independent ones — the
pre-registration's "second, independent ordering" is optimistic, and §5's
multiple-comparisons arithmetic accounts for it.

Both rankings are moderately persistent date to date (1.58 and 1.65 of 3 top
sectors carried over from the previous formation date, 21 trading days
earlier), so `sector_breadth` is measuring *something* stable about sectors. It
just does not predict their forward returns.

## 5. Multiple comparisons — the count, and what follows from it

**Counted explicitly, across both phases of this project:**

| Phase | Comparisons *reported* | Note |
|---|---|---|
| Parent study — parameter sweep | 18 | 6 variants × 3 horizons, `accelerating − leaders` |
| Parent study — other baseline pairs | 12 | 4 cohort pairs × 3 horizons |
| Parent study — §3 cross-run gate pairing | 3 | strict vs baseline, 3 horizons |
| **Parent subtotal** | **33** | (its harness *computed* 5 × 6 × 3 = 90) |
| This study — pre-registered | 30 | 10 cohort pairs × 3 horizons |
| This study — post-hoc positive control | 3 | `leaders_top30 − universe`, 3 horizons |
| **This study subtotal** | **33** | |
| **Project total, reported** | **66** | each also reporting 3 statistics |

**At conventional thresholds, roughly 1 in 20 independent tests produces a
nominally significant result by chance.** Over 66 reported comparisons the
chance expectation is about **3.3 false positives** — before counting that each
comparison reports three statistics (median, mean, hit rate), which is a
further researcher degree of freedom.

**Observed across the project: exactly 3 nominally significant results.** All
three are the same comparison — the trailing 12-month rank against the plain
universe — measured on the same snapshot and largely overlapping dates: the
parent's `leaders − universe` at 63d (71/102, z ≈ +2.29), and this study's
`leaders_top30 − universe` at 21d (65/102, z = +2.77) and 126d (t = +2.20).

Two readings of that, and both belong beside the number:

- **The deflationary one.** Three nominal hits out of 66 is *exactly* the
  chance expectation. Nothing about the count itself argues for a real effect.
  Neither of this study's two clears a Bonferroni threshold over this study's
  own 33 tests (|z| ≥ 3.17 required); the 21d control at z = +2.77 comes
  closest and does not reach it.
- **The one that survives it.** Chance false positives are scattered across
  comparisons and directions. These three are concentrated on one comparison,
  in one direction, and replicate across two studies with different cohort
  definitions (top 15 versus top 30). That concentration — not any individual
  p-value — is what distinguishes them, and it is the same standard the parent
  study applied to its own headline.

**None of this touches the 30 pre-registered tests in this study. Zero of them
reaches |z| ≥ 1.96 or |t| ≥ 1.96.** Nothing needed correcting for
multiplicity, because nothing came close.

The 30 pre-registered tests are also fewer than 30 *independent* tests: three
horizons are measured on the same dates and the same cohorts, `hi − top30` and
`lo − top30` are near-mirror images of one partition, the two sector orderings
share ~1.9 of 3 selected sectors, and the sector cohorts overlap the universe
they are compared against. A rough effective count is closer to a dozen. That
cuts both ways — it means less multiplicity to correct for, and it means the
nulls are less independent corroboration than the raw count suggests.

## 6. Caveats

**The sector labels are an anachronism, and this is the largest new threat to
validity in Experiment 2.** `cache/sectors.json` holds *today's* sector
classification, applied unchanged to formation dates as far back as 2017. A
company that has since been reclassified — and index providers do reclassify,
sometimes wholesale, as with the 2018 creation of Communication Services out of
Technology and Consumer Discretionary — is bucketed here by what it is now, not
what it was then. This is the same family of error as the survivorship bias the
parent study documents: information from the end of the sample leaking into
decisions at the start of it. It biases Experiment 2 in an unknown direction,
and it is unfixable without point-in-time sector history that this project does
not have. Experiment 1 does not use sectors and is unaffected.

**Everything inherited from the parent study still applies**, and none of it is
weakened by this being a follow-up:

- **Survivorship bias.** The universe is today's index membership; anything
  delisted or removed over the ten-year window is silently absent. Every number
  here is optimistic relative to a point-in-time universe.
- **The effective universe grows over time** — 805 usable tickers at the
  earliest formation date, 903 at the largest, stabilizing around mid-2021. Any
  apparent time trend could be partly an artifact of that.
- **Overlapping forward windows.** 21-day formation steps against horizons up
  to 126 days mean consecutive dates share most of their forward window;
  effective N is ~102 / 34 / 17, not 102 three times. This is applied to every
  z and t above rather than mentioned and then ignored.
- **Never subtract aggregates.** This harness does not expose an aggregate
  cross-cohort difference at all, and a test asserts the key's absence.
- **No transaction costs, slippage or position sizing**; cohort returns are
  equal-weighted medians of a hypothetical instantaneous entry.
- **One regime, one universe, one country** (2016–2026, US large/mid-cap).
- **The three anomalous sessions in this snapshot** (2026-07-21, 2026-07-22,
  2026-07-31, with 519–653 of 913 tickers NaN) are not sampled by this study's
  21-day grid either, for the same reason and with the same luck-of-alignment
  caveat.
- **`backtest-conditional-results.json` does not round-trip its horizon keys** —
  `json.dumps` stringifies the integer horizons, so anything reading the
  artifact must index with `"21"`, `"63"`, `"126"`.

**Specific to this study:**

- **The sector cohorts sit inside their own control.** `hi_breadth` and
  `lo_breadth` are each ~25–30% of the universe, so the against-universe rows
  in §4.2 and §4.3 are attenuated toward zero mechanically. `hi − lo` is the
  clean comparison.
- **No parameter sweep.** Both designs were pre-registered at
  `MomentumParams()` defaults and were run only there. Whether a different
  `recent_window`, gate or volatility setting would change these nulls is
  untested. The parent's sweep found no configuration that flipped a sign, but
  that is evidence about a different question.
- **Cohort size was not swept** here either (top 30 → two 15s; top 3 → bottom 3
  sectors). A different conditioning depth is a different test, and running
  several would have multiplied the comparison count.
- **The positive control was not pre-registered.** It was added to check that
  the harness can detect anything at all, is labeled post-hoc everywhere it
  appears, and is counted in §5's tally. A null study from an instrument with
  no demonstrated sensitivity is not informative; that is the only reason it is
  here.
- `cache/` is git-ignored, so neither the snapshot nor the results artifact is
  committed. Every number above is read from the run's console output or from
  `cache/history/backtest-conditional-results.json`, and every number is
  regenerable by re-running the two tools against the same snapshot.

## 7. Recommendation for Phase 2

**The recommendation stands unchanged from the parent study.** Present momentum
term structure as **description only** — "this name's recent pace versus its
own longer-run pace," framed as context alongside the existing 12-month rank.
**Ship no trajectory labels, no acceleration ranking, and no sector-breadth
signal.** Do not use the score, the fade flag, or `sector_breadth` as a
standalone ranking or forward-return signal for surfacing purposes.

Three things this study adds to that recommendation rather than changing it:

1. **The conditional escape hatch is closed.** The most natural response to the
   parent finding was "fine, it doesn't beat the 12-month rank across the
   market — but surely it sorts the leaders." It does not. That was the user's
   actual question, it was tested directly and cleanly (zero drops, exact
   15-name halves, full top 30 on all 102 dates), and the answer is no.
2. **`sector_breadth` is now validated as non-predictive, which is a real
   result about a real function.** It was built and shipped unvalidated. It may
   still be worth *displaying* — it is a stable, interpretable description of
   how broad a sector's move is, and it persists sensibly date to date — but
   this study is now on record that it does not predict sector returns on
   either ordering, and any UI that surfaces it must not imply that it does.
   Wording that says "N of M names in this sector are accelerating" is
   descriptive and defensible; wording that says a sector is "turning" or
   "leading" is a forecast this evidence does not support.
3. **The incumbent got a second, independent replication.** The top-30 12-month
   leader cohort beats the universe by +1.55 / +2.92 / +6.10pp on paired
   medians, winning 65 / 65 / 73 of 102 dates — the parent found the same with
   a top-15 cohort. Read with §5's multiple-comparisons context, this is the
   only effect either phase can resolve at all, and it belongs to the ranking
   Vantage already ships. That is a reason to leave the incumbent alone, not a
   licence to build on top of it.

If a future phase wants to revisit any of this, the parent study's advice
still governs — point-in-time universe, sweep cohort size, and size the study
for the question — with one addition from this one: **point-in-time sector
membership** would be required before any sector-level result is worth
believing, for the reason in §6.
