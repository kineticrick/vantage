# Momentum Term Structure (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a volatility-normalized measure of whether an asset is still working, and empirically test whether it predicts forward returns better than the 12-month rank Vantage uses today.

**Architecture:** One pure library unit (`vantage/momentum.py`) turns a ticker's return term structure into a `Trajectory` — label, score, and supporting figures — with no I/O. Two tooling scripts sit outside the weekly pipeline: one fetches a deep, single-vintage price snapshot, the other runs a cohort backtest over it and sweeps the open parameters. The deliverable is the library plus a written finding.

**Tech Stack:** Python 3.14, pandas 3.0.5, yfinance, pytest. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-08-13-momentum-term-structure-design.md`

## Global Constraints

- Run everything with the project venv: `.venv/bin/python`, `.venv/bin/pytest`.
- **No new runtime dependencies.** `vantage/momentum.py` may import only the stdlib and (for the price-series helpers) pandas, which is already a dependency.
- **`vantage/momentum.py` performs no I/O**: no file reads, no network, no `settings`. It is a pure function of numbers and price series passed to it.
- **Phase 1 changes no existing behavior.** Do not modify `screener.py`, `analyst.py`, `persona.py`, `models.py`, `chat_context.py`, `chat_tools.py`, `report.py`, `run_weekly.py`, or anything under `vantage/web/`. If a task appears to require it, stop and report — that is Phase 2.
- `classify()` never raises. Missing or unusable inputs produce `label="unknown"` and `score=None`.
- **All comparisons are differences of annualized rates, never ratios** (spec §2.1).
- **The `fading` label requires decay at both 3m and 6m** relative to the 12m pace (spec §2.2). A one-month decline never by itself produces `fading`.
- Study data is written to `cache/history/`, never to `cache/` — the weekly cache interleaves batches keyed by fetch date and reading across vintages silently corrupts term structure (spec §3.3).
- All file reads/writes use `encoding="utf-8"`; parquet via pandas.
- Full suite baseline before starting: **116 tests passing** (`.venv/bin/pytest -q`).

---

### Task 1: Trajectory classification core

**Files:**
- Create: `vantage/momentum.py`
- Test: `tests/test_momentum.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `WINDOW_MONTHS: dict[str, int]` — `{"ret_1m": 1, "ret_3m": 3, "ret_6m": 6, "ret_12m": 12}`
  - `annualize(r: float | None, months: int) -> float | None`
  - `MomentumParams(min_recent_return=0.05, min_1m_return=-0.15, recent_window="ret_3m", use_volatility=True)`
  - `Trajectory(label, score, pace_3m, pace_6m, pace_12m, volatility, drawdown_from_high, disagrees, benchmark_adjusted)`
  - `classify(metrics, benchmark_metrics=None, volatility=None, drawdown=None, params=None) -> Trajectory`

- [ ] **Step 1: Write the failing test**

Create `tests/test_momentum.py`:

```python
import pytest
from vantage.momentum import (WINDOW_MONTHS, MomentumParams, Trajectory,
                              annualize, classify)

def _m(r1, r3, r6, r12):
    return {"ret_1m": r1, "ret_3m": r3, "ret_6m": r6, "ret_12m": r12}

def test_annualize_scales_windows():
    assert annualize(0.30, 3) == pytest.approx(1.30 ** 4 - 1)
    assert annualize(0.10, 6) == pytest.approx(1.10 ** 2 - 1)
    assert annualize(0.40, 12) == pytest.approx(0.40)
    assert annualize(None, 3) is None

def test_annualize_guards_total_loss():
    # (1+r) <= 0 would raise or go complex under a fractional exponent
    assert annualize(-1.0, 3) is None
    assert annualize(-1.5, 3) is None

def test_accelerating_when_recent_pace_exceeds_long_run():
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.5)
    assert t.label == "accelerating"
    assert t.pace_3m == pytest.approx(1.30 ** 4 - 1)
    assert t.pace_12m == pytest.approx(0.40)
    assert t.score == pytest.approx((1.30 ** 4 - 1 - 0.40) / 0.5)

def test_fading_requires_both_3m_and_6m_decay():
    t = classify(_m(-0.02, 0.02, 0.10, 0.60), volatility=0.4)
    assert t.label == "fading"

def test_3m_decay_alone_is_not_fading():
    # 3m pace below the 12m pace, but 6m pace well above it -> not fading
    t = classify(_m(-0.02, 0.05, 0.60, 0.50), volatility=0.4)
    assert t.label == "steady"

def test_one_month_decline_alone_never_fades():
    # a weak month against a strong, still-accelerating 3m/6m
    t = classify(_m(-0.06, 0.40, 0.30, 0.35), volatility=0.5)
    assert t.label != "fading"

def test_near_zero_long_run_base_does_not_explode():
    # regression: a ratio formulation scored this kind of name at 200+
    t = classify(_m(0.09, 0.29, 0.20, 0.008), volatility=0.4)
    assert t.score is not None
    assert abs(t.score) < 20

def test_recovering_loser_is_not_accelerating():
    # down on the year, merely less bad lately -> not promise
    t = classify(_m(0.02, 0.06, -0.15, -0.25), volatility=0.4)
    assert t.label != "accelerating"

def test_weak_recent_return_fails_the_strength_gate():
    t = classify(_m(0.01, 0.01, 0.05, 0.30), volatility=0.4)
    assert t.label != "accelerating"

def test_collapsing_month_fails_the_soft_floor():
    t = classify(_m(-0.30, 0.30, 0.35, 0.40), volatility=0.5)
    assert t.label != "accelerating"

def test_volatility_normalization_orders_equal_gaps():
    calm = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.2)
    wild = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.8)
    assert calm.score > wild.score
    assert calm.label == wild.label == "accelerating"

def test_benchmark_subtracts_market_pace():
    raw = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.5)
    rel = classify(_m(0.05, 0.30, 0.35, 0.40),
                   benchmark_metrics=_m(0.02, 0.10, 0.18, 0.25), volatility=0.5)
    assert rel.score < raw.score
    assert rel.benchmark_adjusted is True
    assert raw.benchmark_adjusted is False

def test_missing_window_is_unknown_not_an_exception():
    t = classify({"ret_1m": 0.05, "ret_3m": 0.30}, volatility=0.5)
    assert t.label == "unknown" and t.score is None

def test_zero_or_missing_volatility_yields_no_score_but_keeps_label():
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.0)
    assert t.score is None
    assert t.label in {"accelerating", "steady", "fading"}
    assert classify(_m(0.05, 0.30, 0.35, 0.40), volatility=None).score is None

def test_volatility_can_be_disabled():
    p = MomentumParams(use_volatility=False)
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=None, params=p)
    assert t.score == pytest.approx(1.30 ** 4 - 1 - 0.40)

def test_disagrees_flags_accelerating_far_below_its_high():
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.5, drawdown=-0.35)
    assert t.label == "accelerating" and t.disagrees is True

def test_disagrees_flags_fading_at_its_high():
    t = classify(_m(-0.02, 0.02, 0.10, 0.60), volatility=0.4, drawdown=-0.01)
    assert t.label == "fading" and t.disagrees is True

def test_no_disagreement_when_story_is_consistent():
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.5, drawdown=-0.02)
    assert t.disagrees is False

def test_classify_never_raises_on_garbage():
    for bad in ({}, {"ret_3m": None, "ret_12m": None}, {"ret_1m": "x"}):
        assert classify(bad).label == "unknown"

def test_recent_window_is_configurable():
    p = MomentumParams(recent_window="ret_6m")
    t = classify(_m(0.05, 0.30, 0.35, 0.40), volatility=0.5, params=p)
    assert t.score == pytest.approx((1.35 ** 2 - 1 - 0.40) / 0.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_momentum.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vantage.momentum'`

- [ ] **Step 3: Write the implementation**

Create `vantage/momentum.py`:

```python
"""Return term structure: is an asset still working, or did it already work?

Vantage ranks on the trailing 12-month return, which describes the past. This
unit compares an asset's recent pace against its own long-run pace to say
whether it is accelerating or rolling over.

Two decisions shape everything here (see the design spec):

* Comparisons are DIFFERENCES of annualized rates, never ratios. A ratio blows
  up when the long-run base is near zero, and ranks a flat year with one good
  quarter above everything else.
* One month is not evidence of fading. Momentum is conventionally formed on
  12-minus-1 month returns precisely because short-horizon returns tend to
  reverse rather than continue, so `fading` requires decay at BOTH 3m and 6m.

Pure: no I/O, no settings, no network. Callers supply the numbers.
"""
from dataclasses import dataclass

WINDOW_MONTHS = {"ret_1m": 1, "ret_3m": 3, "ret_6m": 6, "ret_12m": 12}

# A label is contradicted by where the price actually sits relative to its own
# 52-week high; these bounds decide when to say so out loud.
_DISAGREE_ACCEL_DRAWDOWN = -0.20
_DISAGREE_FADE_DRAWDOWN = -0.05


@dataclass
class MomentumParams:
    min_recent_return: float = 0.05    # absolute strength gate on the recent window
    min_1m_return: float = -0.15       # soft floor: exclude active collapse, do not
                                       # require a positive month (see module docstring)
    recent_window: str = "ret_3m"
    use_volatility: bool = True


@dataclass
class Trajectory:
    label: str = "unknown"             # accelerating | steady | fading | unknown
    score: float | None = None
    pace_3m: float | None = None
    pace_6m: float | None = None
    pace_12m: float | None = None
    volatility: float | None = None
    drawdown_from_high: float | None = None
    disagrees: bool = False
    benchmark_adjusted: bool = False


def annualize(r, months):
    """Scale a window return to an annual rate. None when undefined."""
    if r is None:
        return None
    try:
        base = 1.0 + float(r)
    except (TypeError, ValueError):
        return None
    if base <= 0.0:          # total loss: a fractional exponent would go complex
        return None
    return base ** (12.0 / months) - 1.0


def _paces(metrics, benchmark_metrics):
    """Annualized excess pace per window, or None if any required one is missing."""
    out = {}
    for key, months in WINDOW_MONTHS.items():
        a = annualize(metrics.get(key), months)
        if a is None:
            return None
        if benchmark_metrics:
            b = annualize(benchmark_metrics.get(key), months)
            if b is not None:
                a = a - b
        out[key] = a
    return out


def classify(metrics, benchmark_metrics=None, volatility=None, drawdown=None,
             params=None) -> Trajectory:
    """Label and score a ticker's term structure. Never raises."""
    p = params or MomentumParams()
    metrics = metrics if isinstance(metrics, dict) else {}
    adjusted = bool(benchmark_metrics)

    paces = _paces(metrics, benchmark_metrics)
    if paces is None:
        return Trajectory(volatility=volatility, drawdown_from_high=drawdown,
                          benchmark_adjusted=adjusted)

    recent = paces[p.recent_window]
    long_run = paces["ret_12m"]
    gap = recent - long_run

    score = None
    if p.use_volatility:
        if volatility:                       # zero or None -> no score
            score = gap / volatility
    else:
        score = gap

    label = "steady"
    if paces["ret_3m"] < long_run and paces["ret_6m"] < long_run:
        label = "fading"
    elif gap > 0 and _passes_gates(metrics, p):
        label = "accelerating"

    disagrees = False
    if drawdown is not None:
        disagrees = ((label == "accelerating" and drawdown < _DISAGREE_ACCEL_DRAWDOWN)
                     or (label == "fading" and drawdown > _DISAGREE_FADE_DRAWDOWN))

    return Trajectory(label=label, score=score, pace_3m=paces["ret_3m"],
                      pace_6m=paces["ret_6m"], pace_12m=paces["ret_12m"],
                      volatility=volatility, drawdown_from_high=drawdown,
                      disagrees=disagrees, benchmark_adjusted=adjusted)


def _passes_gates(metrics, p) -> bool:
    """Real absolute strength, not merely a smaller decline than before."""
    recent = metrics.get(p.recent_window)
    r1 = metrics.get("ret_1m")
    r12 = metrics.get("ret_12m")
    try:
        return (recent is not None and recent >= p.min_recent_return
                and r12 is not None and r12 > 0
                and r1 is not None and r1 >= p.min_1m_return)
    except TypeError:
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_momentum.py -q`
Expected: PASS (21 tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: PASS — 116 existing + 21 new = 137, no regressions.

- [ ] **Step 6: Commit**

```bash
git add vantage/momentum.py tests/test_momentum.py
git commit -m "feat(momentum): term-structure trajectory classification"
```

---

### Task 2: Price-series helpers

The classifier takes volatility and drawdown as arguments; these compute them. Separate task because they need a price series rather than the metrics dict, and they have their own failure modes.

**Files:**
- Modify: `vantage/momentum.py` (append)
- Test: `tests/test_momentum.py` (append)

**Interfaces:**
- Consumes: nothing from Task 1's functions.
- Produces:
  - `realized_volatility(prices, lookback=126) -> float | None` — annualized stdev of daily log returns
  - `drawdown_from_high(prices, lookback=252) -> float | None` — `<= 0.0`
  - `single_day_share(prices, lookback=63) -> float | None` — largest single session's move as a share of the window's net move

- [ ] **Step 1: Write the failing test**

Append to `tests/test_momentum.py`:

```python
import numpy as np
import pandas as pd
from vantage.momentum import (realized_volatility, drawdown_from_high,
                              single_day_share)

def _series(values):
    idx = pd.date_range("2025-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx, dtype="float64")

def test_realized_volatility_of_constant_growth_is_zero():
    prices = _series([100.0 * (1.01 ** i) for i in range(200)])
    assert realized_volatility(prices) == pytest.approx(0.0, abs=1e-9)

def test_realized_volatility_scales_with_dispersion():
    rng = np.random.default_rng(0)
    calm = _series(100.0 * np.exp(np.cumsum(rng.normal(0, 0.005, 200))))
    wild = _series(100.0 * np.exp(np.cumsum(rng.normal(0, 0.020, 200))))
    assert realized_volatility(wild) > realized_volatility(calm)

def test_realized_volatility_annualizes():
    # daily log-return stdev s -> annualized s * sqrt(252)
    rng = np.random.default_rng(1)
    daily = rng.normal(0, 0.01, 5000)
    prices = _series(100.0 * np.exp(np.cumsum(daily)))
    v = realized_volatility(prices, lookback=5000)
    assert v == pytest.approx(np.std(daily, ddof=1) * np.sqrt(252), rel=0.05)

def test_realized_volatility_short_series_is_none():
    assert realized_volatility(_series([100.0, 101.0])) is None

def test_drawdown_from_high_measures_distance_below_peak():
    prices = _series([100.0] * 10 + [200.0] + [150.0])
    assert drawdown_from_high(prices) == pytest.approx(-0.25)

def test_drawdown_from_high_at_the_high_is_zero():
    prices = _series([100.0, 120.0, 150.0])
    assert drawdown_from_high(prices) == pytest.approx(0.0)

def test_drawdown_from_high_empty_is_none():
    assert drawdown_from_high(_series([])) is None

def test_single_day_share_of_one_gap_move():
    # one +10% session, flat either side: that day IS the whole move
    prices = _series([100.0] * 5 + [110.0] * 5)
    assert single_day_share(prices) == pytest.approx(1.0, rel=1e-6)

def test_single_day_share_exceeds_one_when_a_day_beats_the_net_move():
    # +20% in a day, then giving half back: the day outran the net result
    prices = _series([100.0] * 3 + [120.0] + [110.0] * 3)
    assert single_day_share(prices) > 1.0

def test_single_day_share_flat_window_is_none():
    assert single_day_share(_series([100.0] * 10)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_momentum.py -q`
Expected: FAIL — `ImportError: cannot import name 'realized_volatility'`

- [ ] **Step 3: Write the implementation**

Append to `vantage/momentum.py` (and add `import numpy as np` / `import pandas as pd` at the top):

```python
# --- price-series helpers ---------------------------------------------------
# These need the series itself, not just the window returns, so they live
# beside classify() rather than inside it — the caller passes their results in.

TRADING_DAYS = 252


def realized_volatility(prices, lookback=126):
    """Annualized stdev of daily log returns. None if too short to measure."""
    s = _tail(prices, lookback)
    if s is None or len(s) < 20:
        return None
    logret = np.diff(np.log(s.to_numpy(dtype="float64")))
    if len(logret) < 2:
        return None
    return float(np.std(logret, ddof=1) * np.sqrt(TRADING_DAYS))


def drawdown_from_high(prices, lookback=TRADING_DAYS):
    """How far below its own trailing high the last price sits. <= 0.0."""
    s = _tail(prices, lookback)
    if s is None or len(s) == 0:
        return None
    peak = float(s.max())
    if peak <= 0:
        return None
    return float(s.iloc[-1]) / peak - 1.0


def single_day_share(prices, lookback=63):
    """Largest single session's move as a share of the window's net move.

    Guards against one earnings gap manufacturing a quarter of 'acceleration'.
    Can exceed 1.0 when a single day outran the net result.
    """
    s = _tail(prices, lookback)
    if s is None or len(s) < 2:
        return None
    arr = s.to_numpy(dtype="float64")
    net = arr[-1] / arr[0] - 1.0
    if net == 0:
        return None
    biggest = float(np.max(np.abs(np.diff(arr) / arr[:-1])))
    return biggest / abs(net)


def _tail(prices, lookback):
    if prices is None:
        return None
    s = pd.Series(prices).dropna()
    return s.iloc[-lookback:] if lookback else s
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_momentum.py -q`
Expected: PASS (31 tests)

- [ ] **Step 5: Commit**

```bash
git add vantage/momentum.py tests/test_momentum.py
git commit -m "feat(momentum): realized volatility, drawdown, single-day share"
```

---

### Task 3: Sector breadth

Distinguishes a lone accelerator (idiosyncratic — an earnings surprise, a rumor) from a whole sector turning (a theme, which is what Vantage exists to find).

**Files:**
- Modify: `vantage/momentum.py` (append)
- Test: `tests/test_momentum.py` (append)

**Interfaces:**
- Consumes: `Trajectory` from Task 1.
- Produces: `sector_breadth(trajectories, sectors) -> dict[str, dict]`, each value `{"accelerating_share", "fading_share", "median_score", "count"}`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_momentum.py`:

```python
from vantage.momentum import sector_breadth

def _traj(label, score):
    return Trajectory(label=label, score=score)

def test_sector_breadth_computes_shares_and_median():
    trajectories = {
        "AAA": _traj("accelerating", 2.0),
        "BBB": _traj("accelerating", 4.0),
        "CCC": _traj("fading", -1.0),
        "DDD": _traj("steady", 0.5),
    }
    sectors = {"AAA": "Tech", "BBB": "Tech", "CCC": "Tech", "DDD": "Energy"}
    out = sector_breadth(trajectories, sectors)
    assert out["Tech"]["count"] == 3
    assert out["Tech"]["accelerating_share"] == pytest.approx(2 / 3)
    assert out["Tech"]["fading_share"] == pytest.approx(1 / 3)
    assert out["Tech"]["median_score"] == pytest.approx(2.0)   # median of 2, 4, -1
    assert out["Energy"]["count"] == 1
    assert out["Energy"]["accelerating_share"] == pytest.approx(0.0)

def test_sector_breadth_ignores_unknown_and_missing_sector():
    trajectories = {"AAA": _traj("accelerating", 1.0), "ZZZ": _traj("unknown", None)}
    out = sector_breadth(trajectories, {"AAA": "Tech"})   # ZZZ has no sector
    assert set(out) == {"Tech"}
    assert out["Tech"]["count"] == 1

def test_sector_breadth_handles_all_scoreless_sector():
    trajectories = {"AAA": _traj("steady", None), "BBB": _traj("steady", None)}
    out = sector_breadth(trajectories, {"AAA": "Utilities", "BBB": "Utilities"})
    assert out["Utilities"]["median_score"] is None
    assert out["Utilities"]["count"] == 2

def test_sector_breadth_empty_input():
    assert sector_breadth({}, {}) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_momentum.py -q`
Expected: FAIL — `ImportError: cannot import name 'sector_breadth'`

- [ ] **Step 3: Write the implementation**

Append to `vantage/momentum.py` (add `from statistics import median` to the imports):

```python
def sector_breadth(trajectories, sectors) -> dict:
    """Per-sector share of accelerating vs fading names.

    One name accelerating is idiosyncratic; a sector accelerating in breadth is
    a theme. Names with an unknown label, or with no sector, are excluded.
    """
    buckets = {}
    for ticker, t in (trajectories or {}).items():
        sector = (sectors or {}).get(ticker)
        if not sector or getattr(t, "label", "unknown") == "unknown":
            continue
        buckets.setdefault(sector, []).append(t)
    out = {}
    for sector, ts in buckets.items():
        scores = [t.score for t in ts if t.score is not None]
        n = len(ts)
        out[sector] = {
            "count": n,
            "accelerating_share": sum(t.label == "accelerating" for t in ts) / n,
            "fading_share": sum(t.label == "fading" for t in ts) / n,
            "median_score": median(scores) if scores else None,
        }
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_momentum.py -q`
Expected: PASS (35 tests)

- [ ] **Step 5: Commit**

```bash
git add vantage/momentum.py tests/test_momentum.py
git commit -m "feat(momentum): sector breadth of acceleration"
```

---

### Task 4: Deep history snapshot tool

**Files:**
- Create: `tools/fetch_history.py`
- Test: `tests/test_fetch_history.py`

**Interfaces:**
- Consumes: `vantage.universe.load_universe`.
- Produces:
  - `BENCHMARKS = ("SPY", "QQQ")`
  - `fetch_history(tickers, out_dir, period="10y", batch_size=100, _downloader=None, log=print) -> Path` — writes one parquet of daily Close prices plus a JSON manifest, returns the parquet path.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fetch_history.py`:

```python
import json
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from fetch_history import fetch_history, BENCHMARKS

def _fake_download(tickers, period):
    idx = pd.date_range("2020-01-01", periods=60, freq="B")
    cols = pd.MultiIndex.from_product([["Close", "Volume"], tickers])
    data = {(f, t): [100.0 + i for i in range(60)] for f in ("Close", "Volume")
            for t in tickers}
    return pd.DataFrame(data, index=idx, columns=cols)

def test_fetch_history_writes_wide_close_frame(tmp_path):
    path = fetch_history(["AAA", "BBB"], tmp_path, batch_size=1,
                         _downloader=_fake_download, log=lambda *a: None)
    df = pd.read_parquet(path)
    assert list(df.columns) == ["AAA", "BBB"]
    assert len(df) == 60
    assert df["AAA"].iloc[-1] == 159.0

def test_fetch_history_writes_manifest(tmp_path):
    path = fetch_history(["AAA"], tmp_path, _downloader=_fake_download,
                         log=lambda *a: None)
    manifest = json.loads((Path(path).parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["period"] == "10y"
    assert manifest["tickers"] == 1
    assert manifest["last_date"] == "2020-03-24"
    assert manifest["parquet"] == Path(path).name

def test_fetch_history_survives_a_failing_batch(tmp_path):
    def flaky(tickers, period):
        if "BAD" in tickers:
            raise RuntimeError("network down")
        return _fake_download(tickers, period)
    path = fetch_history(["AAA", "BAD"], tmp_path, batch_size=1,
                         _downloader=flaky, log=lambda *a: None)
    df = pd.read_parquet(path)
    assert list(df.columns) == ["AAA"]

def test_benchmarks_are_declared():
    assert "SPY" in BENCHMARKS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_fetch_history.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetch_history'`

- [ ] **Step 3: Write the implementation**

Create `tools/fetch_history.py`:

```python
"""Fetch a deep, single-vintage price history for the backtest.

The weekly pipeline caches 2 years keyed by fetch date, and `cache/` therefore
holds batches from several different days. Reading across those vintages
silently corrupts a term structure — the same ticker's 12-month return can
differ by hundreds of percentage points depending on which batch answers. The
study needs one dated snapshot, so this writes somewhere else entirely.

Run:  .venv/bin/python tools/fetch_history.py
Tooling only; the weekly pipeline never touches this.
"""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vantage.universe import load_universe  # noqa: E402

BENCHMARKS = ("SPY", "QQQ")


def _default_downloader(tickers, period):
    import yfinance as yf
    return yf.download(tickers, period=period, auto_adjust=True,
                       progress=False, group_by="column")


def fetch_history(tickers, out_dir, period="10y", batch_size=100,
                  _downloader=None, log=print) -> Path:
    downloader = _downloader or _default_downloader
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    closes = {}
    for i in range(0, len(tickers), batch_size):
        batch = list(tickers[i:i + batch_size])
        try:
            df = downloader(batch, period)
        except Exception as e:          # one bad batch must not end the run
            log(f"  batch {i // batch_size} failed: {e}")
            continue
        for t in batch:
            try:
                s = df[("Close", t)].dropna() if isinstance(df.columns, pd.MultiIndex) \
                    else df["Close"].dropna()
            except KeyError:
                continue
            if len(s):
                closes[t] = s
        log(f"  {min(i + batch_size, len(tickers))}/{len(tickers)} …")

    if not closes:
        raise RuntimeError("fetch_history produced no price series")

    frame = pd.DataFrame(closes).sort_index()
    stamp = date.today().isoformat()
    path = out_dir / f"prices-{stamp}.parquet"
    frame.to_parquet(path)
    (out_dir / "manifest.json").write_text(json.dumps({
        "fetched": stamp,
        "period": period,
        "tickers": len(frame.columns),
        "first_date": str(frame.index[0].date()),
        "last_date": str(frame.index[-1].date()),
        "parquet": path.name,
    }, indent=2), encoding="utf-8")
    log(f"wrote {path} — {len(frame.columns)} tickers, {len(frame)} sessions")
    return path


if __name__ == "__main__":
    from vantage.settings import load_settings
    s = load_settings()
    universe = load_universe(s.config_dir / "universe.txt")
    fetch_history(list(universe) + list(BENCHMARKS), s.cache_dir / "history")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_fetch_history.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/fetch_history.py tests/test_fetch_history.py
git commit -m "feat(tools): deep single-vintage history snapshot for the backtest"
```

---

### Task 5: Backtest harness

Pure functions over a price DataFrame, so cohort formation and forward measurement are testable on synthetic series whose answers are known by construction. The CLI in Task 6 supplies real data.

**Files:**
- Create: `tools/backtest_momentum.py`
- Test: `tests/test_backtest_momentum.py`

**Interfaces:**
- Consumes: `vantage.momentum` (`classify`, `MomentumParams`, `realized_volatility`, `drawdown_from_high`, `WINDOW_MONTHS`).
- Produces:
  - `WINDOW_DAYS = {"ret_1m": 21, "ret_3m": 63, "ret_6m": 126, "ret_12m": 252}`
  - `formation_positions(n_rows, lookback=252, forward=126, step=21) -> list[int]`
  - `metrics_at(values, pos) -> dict | None`
  - `forward_return(values, pos, horizon) -> float | None`
  - `run_period(prices, pos, params, n_cohort=15, benchmark="SPY", horizons=(21, 63, 126)) -> dict`
  - `run_backtest(prices, params, n_cohort=15, benchmark="SPY", horizons=(21, 63, 126), step=21) -> dict`

- [ ] **Step 1: Write the failing test**

Create `tests/test_backtest_momentum.py`:

```python
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from backtest_momentum import (WINDOW_DAYS, formation_positions, metrics_at,
                               forward_return, run_period, run_backtest)
from vantage.momentum import MomentumParams

def _ramp(n, daily):
    return 100.0 * np.cumprod(np.full(n, 1.0 + daily))

def _frame(cols, n=700):
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.DataFrame({k: v for k, v in cols.items()}, index=idx)

def test_formation_positions_respect_lookback_and_forward():
    pos = formation_positions(700, lookback=252, forward=126, step=21)
    assert pos[0] >= 252
    assert max(pos) <= 700 - 126 - 1
    assert all(b - a == 21 for a, b in zip(pos, pos[1:]))

def test_formation_positions_empty_when_history_too_short():
    assert formation_positions(200, lookback=252, forward=126) == []

def test_metrics_at_measures_backwards_from_position():
    vals = _ramp(400, 0.001)
    m = metrics_at(vals, 399)
    assert set(m) == set(WINDOW_DAYS)
    assert m["ret_1m"] == pytest.approx(1.001 ** 21 - 1, rel=1e-9)
    assert m["ret_12m"] == pytest.approx(1.001 ** 252 - 1, rel=1e-9)

def test_metrics_at_returns_none_without_enough_history():
    assert metrics_at(_ramp(100, 0.001), 99) is None

def test_forward_return_looks_ahead():
    vals = _ramp(400, 0.002)
    assert forward_return(vals, 100, 63) == pytest.approx(1.002 ** 63 - 1, rel=1e-9)
    assert forward_return(vals, 399, 63) is None      # runs off the end

def test_run_period_ranks_accelerator_above_leader():
    # ACCEL: flat for a year, then a hard recent ramp -> big pace gap
    # LEADER: huge steady year, no recent change -> top 12m rank, no gap
    n = 500
    accel = 100.0 * np.cumprod(np.concatenate([np.full(n - 63, 1.0001),
                                               np.full(63, 1.006)]))
    leader = 100.0 * np.cumprod(np.full(n, 1.004))
    bench = 100.0 * np.cumprod(np.full(n, 1.0002))
    prices = _frame({"ACCEL": accel, "LEADER": leader, "SPY": bench}, n=n)
    out = run_period(prices, n - 127, MomentumParams(), n_cohort=1)
    assert out["accelerating"] == ["ACCEL"]
    assert out["leaders"] == ["LEADER"]

def test_run_period_reports_forward_returns_per_cohort():
    n = 500
    accel = 100.0 * np.cumprod(np.concatenate([np.full(n - 63, 1.0001),
                                               np.full(63, 1.006)]))
    leader = 100.0 * np.cumprod(np.full(n, 1.004))
    bench = 100.0 * np.cumprod(np.full(n, 1.0002))
    prices = _frame({"ACCEL": accel, "LEADER": leader, "SPY": bench}, n=n)
    out = run_period(prices, 300, MomentumParams(), n_cohort=1)
    assert 63 in out["forward"]
    assert set(out["forward"][63]) >= {"accelerating", "leaders", "universe"}

def test_run_backtest_aggregates_across_periods():
    n = 700
    rng = np.random.default_rng(3)
    cols = {f"T{i}": 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
            for i in range(12)}
    cols["SPY"] = 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.006, n)))
    out = run_backtest(_frame(cols, n=n), MomentumParams(), n_cohort=3)
    assert out["periods"] > 0
    for horizon in (21, 63, 126):
        assert "accelerating" in out["cohorts"][horizon]
        assert "median" in out["cohorts"][horizon]["accelerating"]
    assert "spread_vs_leaders" in out

def test_run_backtest_on_short_history_reports_zero_periods():
    prices = _frame({"AAA": _ramp(100, 0.001), "SPY": _ramp(100, 0.0005)}, n=100)
    out = run_backtest(prices, MomentumParams())
    assert out["periods"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_backtest_momentum.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest_momentum'`

- [ ] **Step 3: Write the implementation**

Create `tools/backtest_momentum.py`:

```python
"""Does the trajectory score predict forward returns better than 12m rank?

Forms cohorts at past dates and measures what happened next. The 12-month
leader cohort is the control: it is exactly what Vantage does today, so the
headline number is the spread between the accelerating cohort and it.

Read the caveats in the generated report before believing anything here. The
universe is today's index membership, so the study is survivorship-biased.

Run:  .venv/bin/python tools/backtest_momentum.py
Tooling only.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vantage.momentum import (MomentumParams, classify, drawdown_from_high,  # noqa: E402
                              realized_volatility)

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


def run_period(prices, pos, params, n_cohort=15, benchmark="SPY",
               horizons=(21, 63, 126)) -> dict:
    """Form cohorts at one date and measure what happened next."""
    arrays = {c: prices[c].to_numpy(dtype="float64") for c in prices.columns}
    bench_metrics = metrics_at(arrays[benchmark], pos) if benchmark in arrays else None

    scored, leaders, fading, universe = [], [], [], []
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
        universe.append(ticker)
        leaders.append((ticker, m["ret_12m"]))
        if t.label == "accelerating" and t.score is not None:
            scored.append((ticker, t.score))
        elif t.label == "fading":
            fading.append(ticker)

    scored.sort(key=lambda kv: -kv[1])
    leaders.sort(key=lambda kv: -kv[1])
    cohorts = {
        "accelerating": [t for t, _ in scored[:n_cohort]],
        "leaders": [t for t, _ in leaders[:n_cohort]],
        "fading": fading[:n_cohort],
        "universe": universe,
    }

    forward = {}
    for h in horizons:
        forward[h] = {}
        for name, members in cohorts.items():
            rs = [forward_return(arrays[t], pos, h) for t in members]
            rs = [r for r in rs if r is not None]
            forward[h][name] = float(np.median(rs)) if rs else None
    return {**cohorts, "forward": forward, "pos": pos}


def run_backtest(prices, params, n_cohort=15, benchmark="SPY",
                 horizons=(21, 63, 126), step=21) -> dict:
    positions = formation_positions(len(prices), forward=max(horizons), step=step)
    periods = [run_period(prices, p, params, n_cohort, benchmark, horizons)
               for p in positions]
    out = {"periods": len(periods), "cohorts": {}, "spread_vs_leaders": {}}
    for h in horizons:
        out["cohorts"][h] = {}
        for name in ("accelerating", "leaders", "fading", "universe"):
            vals = [p["forward"][h][name] for p in periods
                    if p["forward"][h].get(name) is not None]
            out["cohorts"][h][name] = {
                "median": float(np.median(vals)) if vals else None,
                "mean": float(np.mean(vals)) if vals else None,
                "periods": len(vals),
            }
        a = out["cohorts"][h]["accelerating"]["median"]
        b = out["cohorts"][h]["leaders"]["median"]
        out["spread_vs_leaders"][h] = (a - b) if (a is not None and b is not None) else None
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_backtest_momentum.py -q`
Expected: PASS (9 tests). If `test_run_period_ranks_accelerator_above_leader` fails because LEADER also qualifies as accelerating, check the gates — a perfectly steady ramp has `pace_3m == pace_12m`, so `gap == 0` and it must not be labeled accelerating.

- [ ] **Step 5: Run the full suite and commit**

Run: `.venv/bin/pytest -q`
Expected: PASS — 116 + 21 + 10 + 4 + 4 + 9 = 164.

```bash
git add tools/backtest_momentum.py tests/test_backtest_momentum.py
git commit -m "feat(tools): momentum backtest harness with 12m-leader control"
```

---

### Task 6: Run the study and write the finding

This is the deliverable. It is a research task, not a coding task: the output is a document with numbers in it and an honest recommendation.

**Files:**
- Modify: `tools/backtest_momentum.py` (add the `__main__` CLI and the parameter sweep)
- Create: `docs/superpowers/findings/2026-08-13-momentum-backtest.md`
- Modify: `README.md`

- [ ] **Step 1: Fetch the history**

Run (slow — ~915 tickers plus benchmarks, several minutes; run it in the background):

```bash
.venv/bin/python tools/fetch_history.py
```

Expected: `cache/history/prices-<date>.parquet` plus `manifest.json`. Confirm the manifest's `first_date` is roughly ten years back and `tickers` is close to 917. Report the actual numbers — if coverage is far below the universe size, say so; it changes how much the study can claim.

- [ ] **Step 2: Add the CLI and parameter sweep**

Append to `tools/backtest_momentum.py`:

```python
SWEEP = [
    ("baseline", MomentumParams()),
    ("strict 1m gate", MomentumParams(min_1m_return=0.0)),
    ("no 1m gate", MomentumParams(min_1m_return=-1.0)),
    ("6m recent window", MomentumParams(recent_window="ret_6m")),
    ("no vol normalization", MomentumParams(use_volatility=False)),
    ("strength floor 15%", MomentumParams(min_recent_return=0.15)),
]


def main(argv=None):
    from vantage.settings import load_settings
    s = load_settings()
    hist = sorted((s.cache_dir / "history").glob("prices-*.parquet"))
    if not hist:
        print("No history snapshot. Run tools/fetch_history.py first.")
        return 1
    prices = pd.read_parquet(hist[-1]).sort_index()
    print(f"{hist[-1].name}: {len(prices.columns)} tickers, {len(prices)} sessions")
    results = {}
    for label, params in SWEEP:
        out = run_backtest(prices, params)
        results[label] = out
        print(f"\n=== {label} — {out['periods']} formation dates ===")
        for h in (21, 63, 126):
            c = out["cohorts"][h]
            fmt = lambda v: "n/a" if v is None else f"{v:+.2%}"
            print(f"  {h:>3}d fwd  accel {fmt(c['accelerating']['median'])}"
                  f"  leaders {fmt(c['leaders']['median'])}"
                  f"  universe {fmt(c['universe']['median'])}"
                  f"  fading {fmt(c['fading']['median'])}"
                  f"  spread {fmt(out['spread_vs_leaders'][h])}")
    Path("cache/history/backtest-results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run the study**

```bash
.venv/bin/python tools/backtest_momentum.py
```

Capture the full output. Every number in the report must come from this run.

- [ ] **Step 4: Write the finding**

Create `docs/superpowers/findings/2026-08-13-momentum-backtest.md` containing:

1. **Headline** — one sentence: does the trajectory score beat the 12-month leader rank, and by how much, at which horizon.
2. **The table** — median forward return by cohort (accelerating / leaders / fading / universe) at 1, 3, and 6 months, with the number of formation dates.
3. **Parameter sweep** — what each variant did to the spread. Specifically answer the §2.2 prediction from the spec: *does a strict positive-1m gate help or hurt?* The reversal argument predicts it hurts. Report which way it actually went, whichever that is.
4. **Does the fade flag work?** — did the fading cohort underperform the universe?
5. **Caveats, stated plainly, not buried:** survivorship bias (the universe is today's index membership, so everything delisted or removed is silently excluded — this is the largest threat to validity); overlapping forward windows make consecutive periods non-independent; no transaction costs or position sizing; one regime, one universe, one country.
6. **Recommendation for Phase 2** — either "the score predicts; weight it thus," or "it does not beat 12-month momentum; Phase 2 presents term structure as description and makes no forward-promise claims." **A negative result is a valid and expected outcome — write it plainly if that is what the data says.**

- [ ] **Step 5: Update the README**

Add a short "Momentum term structure" note under the existing tooling section: what `vantage/momentum.py` computes, that `tools/fetch_history.py` and `tools/backtest_momentum.py` are tooling-only and never run in the weekly pipeline, and a pointer to the finding document. Do not claim any behavior change in the brief or dashboard — Phase 1 ships none.

- [ ] **Step 6: Commit**

```bash
git add tools/backtest_momentum.py docs/superpowers/findings/ README.md
git commit -m "docs: momentum backtest finding and phase-1 tooling notes"
```

Note: `cache/` is git-ignored, so the parquet snapshot and `backtest-results.json` are intentionally not committed. The finding document must therefore contain the numbers themselves, not merely point at the JSON.

---

## Self-Review Notes

Spec coverage against `docs/superpowers/specs/2026-08-13-momentum-term-structure-design.md`:

- §2.1 differences not ratios → Task 1 (`test_near_zero_long_run_base_does_not_explode`)
- §2.2 one month is not fading → Task 1 (`test_fading_requires_both_3m_and_6m_decay`, `test_3m_decay_alone_is_not_fading`, `test_one_month_decline_alone_never_fades`); tested empirically in Task 6 step 4 item 3
- §2.3 strength gates → Task 1 (`test_recovering_loser_is_not_accelerating`)
- §2.4 ranked top-N → Task 5 (`run_period` ranks and slices; no threshold anywhere)
- §2.5 volatility normalization → Tasks 1 and 2
- §2.6 excess over benchmark → Task 1 (`test_benchmark_subtracts_market_pace`), Task 4 (`BENCHMARKS`)
- §3.1 `momentum.py` incl. `single_day_share` → Tasks 1, 2
- §3.2 sector breadth → Task 3
- §3.3 deep single-vintage fetch → Task 4
- §4 the backtest, cohorts, sweep, caveats → Tasks 5, 6
- §5 error handling → Task 1 (`test_classify_never_raises_on_garbage`, missing-window and zero-volatility tests), Task 4 (failing batch)
- §6 testing → each task's test steps
- §7 out of scope → enforced by the Global Constraint forbidding edits to existing modules

Type consistency: `MomentumParams`, `Trajectory`, and `classify`'s signature are defined in Task 1 and used unchanged in Tasks 3 and 5; `run_period`/`run_backtest` take `n_cohort` (not `n`) consistently in both the tests and the implementation.
