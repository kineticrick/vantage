# Momentum Term Structure — Measurement and Validation (Phase 1) — Design

**Date:** 2026-08-13
**Status:** Design — pending user review
**Project root:** `/home/kineticrick/code/python/vantage`

## 1. Purpose

Vantage ranks the market on one number: the trailing 12-month return. It computes
`ret_1m`, `ret_3m`, `ret_6m` as well, and then discards their shape. The result is
a brief that leads with last year's winners regardless of whether they are still
working. On the 2026-08-11 signal set, the top five leaders — MU (+632%),
WDC (+486%), STX (+450%), VICR (+350%), CIEN (+308%) — were **all** declining over
the trailing month, while the two genuinely accelerating names, PBF and ATI, were
filed near the bottom of the summary as "non-AI movers."

This phase builds and **validates** a measure of whether an asset is still
working. It deliberately stops short of wiring anything into the brief, the chat,
or the dashboard: that is Phase 2, and its design depends on what this phase
finds.

### Success criteria
- A pure, well-tested unit that turns a ticker's return term structure into a
  trajectory: a label, a volatility-normalized score, and the supporting figures.
- A sector-level view distinguishing a lone accelerator from a whole sector turning.
- An offline backtest producing a **written, quantitative finding** on whether the
  score predicts forward returns better than the 12-month rank Vantage uses today.
- The finding is reported honestly, including the case where the score adds
  nothing. A negative result is a successful outcome of this phase.

### Explicit non-goal
No change to `screener.py`, `analyst.py`, `persona.py`, `Brief`, the chat, the
report renderers, or the web layer. Phase 1 ships a library and a study, not a
behavior change.

## 2. The methodological decisions

These are the choices that determine whether the measure is meaningful. Each was
made against evidence rather than intuition, and each is stated here so it can be
argued with.

### 2.1 Differences, not ratios

An obvious formulation is "recent pace ÷ long-run pace." A probe over the real
universe showed this is unusable: when the 12-month return is near zero the
denominator collapses and the score explodes. The entire top of that ranked list
was names with a ~0% year (LII at +0.8%/12m scored 210), not accelerating names.

**All comparisons are differences of annualized rates, never ratios.**

### 2.2 One month is the wrong window for "fading"

The naive reading — MU is down 7.3% over a month, therefore MU is fading — runs
against the momentum literature, where the standard factor is formed on 12-minus-1
or 12-minus-2 month returns, *skipping* the most recent month precisely because
short-horizon returns exhibit reversal rather than continuation. A one-month
decline after a large run may be the least informative window available.

Therefore:
- **3-month is the primary recent window.**
- The `fading` label requires decay at **both** 3m and 6m relative to the 12m pace.
- 1-month is computed and reported but does not by itself drive a label.

This creates a tension with the strength gate below, which the backtest resolves
empirically rather than by argument (§4.3).

### 2.3 Strength gates, not bare acceleration

Without an absolute-strength gate, the ranking fills with names that are merely
*less bad* lately — a stock down 24.9% over 12 months whose last quarter was
flat scores as "accelerating." That is recovery, not promise. Eligibility for the
accelerating list requires genuine recent absolute strength.

### 2.4 A ranked list, not a threshold

Gated difference scores still qualified 36–38% of the universe in the probe. There
is no defensible cutoff value for "accelerating enough," and no user asks which
stocks exceed acceleration 4.2. The output is a **ranked top-N**.

### 2.5 Volatility normalization

A +20% month on a name that habitually swings 20% is noise; the same move on a
steady compounder is a regime change. Raw pace gaps rank the most volatile names
highest. Scores are therefore expressed in units of the asset's own realized
volatility.

### 2.6 Excess over benchmark

In a tape where everything is up 30%, "accelerating" means little. Returns are
measured as excess over a benchmark (SPY, with QQQ recorded for reference) so the
measure reflects the asset rather than the market.

## 3. Architecture

Three units. The first is a library; the other two are tooling that never runs in
the weekly pipeline.

### 3.1 `vantage/momentum.py` (new) — the trajectory unit

A pure function of numbers. No I/O, no network, no settings.

```python
@dataclass
class Trajectory:
    label: str                 # "accelerating" | "steady" | "fading" | "unknown"
    score: float | None        # vol-normalized pace gap; None when not computable
    pace_3m: float | None      # annualized excess pace, 3-month window
    pace_6m: float | None
    pace_12m: float | None
    volatility: float | None   # annualized realized vol, trailing 6m
    drawdown_from_high: float | None   # <= 0.0; distance below trailing 52w high
    disagrees: bool            # label and drawdown tell different stories
```

Core entry point:

```python
def classify(metrics, benchmark_metrics=None, volatility=None,
             drawdown_from_high=None, params=None) -> Trajectory
```

- `metrics` is the existing dict (`ret_1m`/`ret_3m`/`ret_6m`/`ret_12m`).
- `benchmark_metrics` is the same shape for SPY; when absent, excess returns
  degrade to raw returns and the Trajectory records that it was unadjusted.
- Missing windows yield `label="unknown"`, `score=None` — never an exception.

**Score.** With `ann(r, months) = (1+r)**(12/months) - 1`:

```
pace_w   = ann(r_w) - ann(bench_w)          # annualized excess pace
gap      = pace_3m - pace_12m               # difference, never a ratio (§2.1)
score    = gap / volatility                 # in units of the asset's own vol (§2.5)
```

**Labels.**
- `accelerating` — passes the strength gates and `score > 0`.
- `fading` — `pace_3m < pace_12m` **and** `pace_6m < pace_12m` (§2.2).
- `steady` — everything else.

**Strength gates** (parameterized via `params`, calibrated in §4.3):
- `ret_3m >= min_recent_return`
- `ret_12m > 0` — the long-run base must be positive for "still working" to mean
  anything
- `ret_1m >= min_1m_return`, a soft floor excluding actively collapsing names
  rather than requiring a positive month (§2.2)

**Drawdown from 52-week high** is supplied by the caller (it needs the price
series, not just the metrics) and is used for the `disagrees` flag: a name labeled
`accelerating` while sitting far below its own high, or labeled `fading` while
sitting at highs, is contradictory and worth surfacing rather than smoothing over.

Helpers for callers that do hold price series:

```python
def realized_volatility(prices, lookback=126) -> float | None
def drawdown_from_high(prices, lookback=252) -> float | None
def single_day_share(prices, lookback=63) -> float | None
```

`single_day_share` reports the largest single session's share of the window's
total move, guarding against one earnings gap manufacturing a quarter of
"acceleration" — the same class of artifact the existing `max_plausible_return`
filter catches for spin-offs.

### 3.2 Sector breadth

```python
def sector_breadth(trajectories_by_ticker, sectors) -> dict
```

Per sector: the share of its names labeled `accelerating`, the share `fading`, the
median score, and the count. This answers a question the current sector momentum
(median 12m return) cannot: is a name accelerating alone, or is its whole sector
turning? A lone accelerator is idiosyncratic — an earnings surprise, a rumor. A
sector accelerating in breadth is a theme, which is what Vantage exists to find.

Lives in `vantage/momentum.py` alongside `classify`; it is the same concept
aggregated, and splitting it into its own module would separate things that change
together.

### 3.3 `tools/fetch_history.py` (new) — deep history, tooling only

The weekly pipeline fetches `period="2y"`, which supports only a handful of
non-overlapping forward windows — too thin for the study to say anything.

This tool fetches a longer history (default 10 years) for the universe plus the
benchmarks, and writes it to `cache/history/` **separately from the weekly price
cache**, so it can never be confused with pipeline data. It is slow (~915 tickers)
and run manually.

The separation is deliberate: the existing `cache/` already interleaves batches
from several fetch dates keyed by `date.today()`, and a probe that read across
those vintages silently produced corrupted term structures (a ticker's 12-month
return differed by 350 percentage points depending on which vintage answered).
History for the study must be a single, self-describing, dated snapshot.

### 3.4 `tools/backtest_momentum.py` (new) — the study

See §4.

## 4. The backtest

### 4.1 Construction

At each **formation date** `t` on a monthly schedule across the available history:

1. Compute each ticker's metrics using only data at or before `t`.
2. Compute `Trajectory` for each, plus benchmark metrics at `t`.
3. Form cohorts of equal size N:
   - **A — accelerating:** top N by `score` among gated names.
   - **B — 12m leaders:** top N by trailing 12-month return. *This is the control:
     it is exactly what Vantage does today.*
   - **C — universe:** all names, as a baseline.
   - **D — fading:** names labeled `fading`, to test whether the fade flag
     predicts underperformance.
4. Measure forward returns from `t` over 1, 3, and 6 months.

### 4.2 What is reported

For each cohort and horizon: mean and median forward return, hit rate versus the
universe baseline, and dispersion. Plus the headline number — **the A−B spread**,
which is the only question that matters: does the trajectory score beat the rank
Vantage already uses?

The report states the number of formation dates, and flags that overlapping
forward windows make observations non-independent, so consecutive periods are not
separate evidence.

### 4.3 Parameters the study settles

Rather than defending gate values by argument, the backtest sweeps them and
reports the result:
- `min_recent_return` — the absolute strength floor.
- `min_1m_return` — whether requiring a positive month helps or hurts. §2.2 argues
  a strict positive gate should *hurt* if short-horizon reversal is real; this is
  a directly testable prediction and the study should report it either way.
- Recent window: 3m versus 6m as the primary.
- Volatility normalization on versus off.
- N (cohort size).

### 4.4 Caveats the report must state

- **Survivorship bias.** `config/universe.txt` is *today's* index membership.
  Backtesting it over ten years silently excludes everything that was removed or
  delisted, which biases results optimistic. This is the single largest threat to
  the finding's validity and must be stated in the report, not buried.
- Overlapping forward windows reduce effective sample size.
- No transaction costs, slippage, or position sizing.
- One market regime, one universe, one country.

The deliverable is an honest measurement, not a trading system.

### 4.5 Deliverable

`docs/superpowers/findings/2026-08-13-momentum-backtest.md`: the numbers, the
chosen parameters with the evidence for them, the caveats above, and a plain
recommendation for Phase 2 — either "the score predicts, weight it this much," or
"it does not beat 12-month momentum; Phase 2 should present the term structure as
description and make no forward-promise claims."

## 5. Error handling

- Any ticker missing a required window yields `label="unknown"`, never an exception.
- Zero or unavailable volatility yields `score=None` and excludes the name from
  the accelerating ranking; it still receives a label from the pace comparison.
- A missing benchmark degrades to raw (unadjusted) returns, recorded on the
  Trajectory so downstream consumers know.
- `classify` never raises. The study skips tickers with insufficient history at a
  given formation date and reports how many were skipped.

## 6. Testing

`vantage/momentum.py` is pure, so it is tested exhaustively without network or
fixtures:
- Known metric inputs produce known labels — accelerating, fading, steady, and the
  boundary between them.
- The `fading` label requires **both** 3m and 6m decay: a name with 3m decay but 6m
  strength is not `fading` (§2.2).
- Ratio-explosion regression: a near-zero 12-month base must not produce an
  extreme score (§2.1).
- "Less bad" rejection: a name with a negative 12-month return does not qualify as
  accelerating regardless of recent improvement (§2.3).
- Volatility normalization: two names with identical pace gaps and different
  volatilities rank in the expected order.
- Missing windows, zero volatility, and absent benchmark each degrade as specified
  rather than raising.
- `disagrees` fires on both contradictions.
- `sector_breadth` aggregates correctly, including a sector with one name.

`realized_volatility`, `drawdown_from_high`, and `single_day_share` are tested
against constructed price series with hand-computed answers.

The backtest harness is tested on synthetic price series whose forward returns are
known by construction, so cohort formation and forward measurement are verified
without touching real data.

## 7. Out of scope (Phase 2)

Wiring the validated score through `screener.py` (a `trajectory` field on `Signal`
and a second `accel_leader` ranked list), `persona.py` (assessing forward promise
as a standing duty), a new `Brief` field, `chat_context` and `chat_tools` (which
today drop the term structure and force the analyst to rebuild it with per-ticker
tool calls), the report renderers, and the dashboard. Phase 2 gets its own spec,
written against this phase's finding.
