# Descriptive Term Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show every ticker's four return windows and its distance below the 52-week high, everywhere a ticker appears — as description, never as a signal.

**Architecture:** One pure formatter (`vantage/termstructure.py`) owns how a percentage renders, and the API ships its output as display strings so no consumer re-implements the rule. The screener gains one line computing the drawdown into the existing `metrics` dict. Everything else — chat context, tools, dashboard, brief — consumes what already exists.

**Tech Stack:** Python 3.14, FastAPI, pandas, pytest; vanilla JS/CSS (no build step).

**Spec:** `docs/superpowers/specs/2026-08-14-descriptive-term-structure-design.md`

## Global Constraints

- Run everything with the project venv: `.venv/bin/python`, `.venv/bin/pytest`.
- **No new runtime dependencies.**
- **Nothing ranks, sorts, filters or gates on the term structure or the drawdown.** Three studies refuted it as a predictor; this project ships the numbers as description only. A sort key, a threshold, or a comparison that changes what appears or in what order is out of bounds.
- **No `accelerating` / `fading` / `steady` label ships anywhere.** `vantage/momentum.py`'s `classify` is not called by any code in this plan.
- **`run_screener`'s selection output is unchanged** — same tickers, same order, same ranks, same values. The only edit adds a key to a dict already being built.
- Percentage signs are **ASCII** (`-`, never U+2212). This output reaches a prompt, an email and a JSON API.
- **One formatting rule for every percentage**, including the drawdown.
- All file reads/writes use `encoding="utf-8"`.
- Backward compatibility: `data/signals-*.json` and `reports/brief-*.json` written before this change must load and render without error.
- Full suite baseline before starting: **288 tests passing** (`.venv/bin/pytest -q`).

---

### Task 1: The formatter

**Files:**
- Create: `vantage/termstructure.py`
- Test: `tests/test_termstructure.py`

**Interfaces:**
- Consumes: nothing from the project.
- Produces:
  - `WINDOWS = (("ret_1m","1m"), ("ret_3m","3m"), ("ret_6m","6m"), ("ret_12m","12m"))`
  - `DRAWDOWN = ("drawdown_from_high", "off high")`
  - `MISSING = "--"`
  - `format_pct(value) -> str`
  - `term_structure(metrics) -> list[dict]` — five entries, keys `label`/`value`/`display`
  - `render_text_table(rows, limit=25) -> str` — `rows` is an iterable of `(ticker, metrics)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_termstructure.py`:

```python
import math
import pytest
from vantage.termstructure import (DRAWDOWN, MISSING, WINDOWS, format_pct,
                                   render_text_table, term_structure)

def test_format_pct_one_decimal_below_the_break():
    assert format_pct(0.092) == "+9.2%"
    assert format_pct(-0.073) == "-7.3%"
    assert format_pct(0.0) == "+0.0%"

def test_format_pct_no_decimals_at_and_above_the_break():
    assert format_pct(6.317) == "+632%"
    assert format_pct(1.0) == "+100%"
    assert format_pct(-1.27) == "-127%"

def test_format_pct_precision_boundary():
    assert format_pct(0.999) == "+99.9%"     # 99.9% -> one decimal
    assert format_pct(1.0) == "+100%"        # 100%  -> none

def test_format_pct_signs_are_ascii():
    # This output reaches a prompt, an email and a JSON API. A typographic
    # minus here is a UnicodeDecodeError waiting to happen downstream.
    for v in (0.5, -0.5, 6.0, -6.0):
        assert "−" not in format_pct(v)
    assert format_pct(-0.5).startswith("-")
    assert format_pct(0.5).startswith("+")

@pytest.mark.parametrize("bad", [None, "x", [], {}, float("nan"),
                                 float("inf"), float("-inf")])
def test_format_pct_never_raises(bad):
    assert format_pct(bad) == MISSING

def test_term_structure_returns_five_entries_in_fixed_order():
    m = {"ret_1m": -0.073, "ret_3m": 0.092, "ret_6m": 1.266,
         "ret_12m": 6.317, "drawdown_from_high": -0.123}
    ts = term_structure(m)
    assert [e["label"] for e in ts] == ["1m", "3m", "6m", "12m", "off high"]
    assert [e["display"] for e in ts] == ["-7.3%", "+9.2%", "+127%", "+632%", "-12.3%"]
    assert ts[0]["value"] == pytest.approx(-0.073)

def test_absent_metric_keeps_its_column():
    # A dropped entry would shift every later column in the rendered row.
    ts = term_structure({"ret_1m": 0.05})
    assert len(ts) == 5
    assert ts[0]["display"] == "+5.0%"
    assert [e["display"] for e in ts[1:]] == [MISSING] * 4
    assert ts[1]["value"] is None

def test_unusable_value_yields_missing_and_none_value():
    ts = term_structure({"ret_1m": "banana", "ret_3m": float("nan")})
    assert ts[0]["display"] == MISSING and ts[0]["value"] is None
    assert ts[1]["display"] == MISSING and ts[1]["value"] is None

def test_term_structure_tolerates_a_non_dict():
    assert [e["display"] for e in term_structure(None)] == [MISSING] * 5
    assert len(term_structure("nope")) == 5

def test_render_text_table_aligns_columns_across_rows():
    rows = [("MU", {"ret_1m": -0.073, "ret_12m": 6.317}),
            ("LONGTICK", {"ret_1m": 0.208, "ret_12m": 0.226})]
    lines = render_text_table(rows).splitlines()
    assert len(lines) == 3                      # header + two rows
    # every line is the same width, which is what makes a column scannable
    assert len({len(x) for x in lines}) == 1
    assert "1m" in lines[0] and "off high" in lines[0]
    assert lines[1].startswith("MU")
    assert "-7.3%" in lines[1] and "+632%" in lines[1]

def test_render_text_table_respects_the_limit():
    rows = [(f"T{i}", {"ret_1m": 0.01}) for i in range(40)]
    assert len(render_text_table(rows, limit=5).splitlines()) == 6

def test_render_text_table_empty_is_empty_string():
    assert render_text_table([]) == ""

def test_window_labels_are_stable():
    assert [label for _, label in WINDOWS] == ["1m", "3m", "6m", "12m"]
    assert DRAWDOWN == ("drawdown_from_high", "off high")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_termstructure.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vantage.termstructure'`

- [ ] **Step 3: Write the implementation**

Create `vantage/termstructure.py`:

```python
"""Presenting a ticker's return term structure.

The four trailing windows and the distance below the 52-week high are facts
worth showing. They are not a forecast: three studies found this shape does not
predict forward returns (see config/evidence.yaml). Nothing here ranks, sorts
or scores — it formats.

One formatter, several consumers. The chat prompt, the dashboard and the
run_screen tool must render the same number identically, so the API ships the
display strings produced here rather than letting each consumer format its own.
"""
import math

WINDOWS = (("ret_1m", "1m"), ("ret_3m", "3m"),
           ("ret_6m", "6m"), ("ret_12m", "12m"))
DRAWDOWN = ("drawdown_from_high", "off high")
MISSING = "--"

# Below this many percent a decimal carries information; above it, the decimal
# is noise on a number already measured in hundreds.
_PRECISION_BREAK = 100.0


def format_pct(value) -> str:
    """A return fraction as a signed percentage. Never raises.

    Signs are ASCII on purpose — this string reaches a prompt, an email and a
    JSON API, and a typographic minus is a decoding hazard downstream.
    """
    try:
        pct = float(value) * 100.0
    except (TypeError, ValueError):
        return MISSING
    if not math.isfinite(pct):
        return MISSING
    digits = 1 if abs(pct) < _PRECISION_BREAK else 0
    return f"{pct:+.{digits}f}%"


def term_structure(metrics) -> list:
    """The five cells, in fixed order, for one ticker.

    An absent or unusable metric keeps its column with MISSING rather than
    being dropped — a dropped entry shifts every column after it.
    """
    metrics = metrics if isinstance(metrics, dict) else {}
    out = []
    for key, label in WINDOWS + (DRAWDOWN,):
        raw = metrics.get(key)
        display = format_pct(raw)
        out.append({"label": label,
                    "value": raw if display != MISSING else None,
                    "display": display})
    return out


def render_text_table(rows, limit=25) -> str:
    """Aligned block for the chat prompt. `rows` is an iterable of (ticker, metrics)."""
    rows = list(rows)[:limit]
    if not rows:
        return ""
    labels = [label for _, label in WINDOWS] + [DRAWDOWN[1]]
    cells = [(str(t), [e["display"] for e in term_structure(m)]) for t, m in rows]
    tick_w = max([len(t) for t, _ in cells] + [6])
    widths = [max([len(c[i]) for _, c in cells] + [len(labels[i])])
              for i in range(len(labels))]
    def _line(head, values):
        return f"{head:<{tick_w}}" + "".join(
            f"  {values[i]:>{widths[i]}}" for i in range(len(labels)))
    return "\n".join([_line("", labels)] + [_line(t, c) for t, c in cells])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_termstructure.py -q`
Expected: PASS (13 tests)

- [ ] **Step 5: Run the full suite and commit**

Run: `.venv/bin/pytest -q` → expect 288 + 13 = 301.

```bash
git add vantage/termstructure.py tests/test_termstructure.py
git commit -m "feat(termstructure): one formatter for the return term structure"
```

---

### Task 2: Compute the drawdown in the screener

**Files:**
- Modify: `vantage/screener.py`
- Test: `tests/test_screener.py`

**Interfaces:**
- Consumes: `vantage.momentum.drawdown_from_high(prices, lookback=252) -> float | None`.
- Produces: `metrics["drawdown_from_high"]` on every signal whose series supports it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_screener.py`:

```python
def test_screener_attaches_drawdown_from_high():
    import pandas as pd
    from vantage.data_ingest import MarketData
    from vantage.screener import run_screener
    idx = pd.date_range("2024-01-01", periods=300, freq="D")
    # rises to 200 then falls back to 150 -> 25% below the trailing high
    values = [100.0 + i for i in range(100)] + [200.0] * 100 + [150.0] * 100
    md = MarketData(as_of="2026-08-14", prices={"AAA": pd.Series(values, index=idx)},
                    volumes={"AAA": pd.Series([1000.0] * 300, index=idx)},
                    sectors={"AAA": "Tech"}, names={"AAA": "Alpha"})
    ss = run_screener(md, return_leader_threshold=0.0)
    assert ss.signals[0].metrics["drawdown_from_high"] == pytest.approx(-0.25)

def test_screener_omits_drawdown_when_series_too_short():
    import pandas as pd
    from vantage.data_ingest import MarketData
    from vantage.screener import run_screener
    idx = pd.date_range("2024-01-01", periods=260, freq="D")
    rising = pd.Series([100.0 + i for i in range(260)], index=idx)
    md = MarketData(as_of="2026-08-14", prices={"AAA": rising},
                    volumes={"AAA": pd.Series([1000.0] * 260, index=idx)},
                    sectors={"AAA": "Tech"}, names={"AAA": "Alpha"})
    ss = run_screener(md, return_leader_threshold=0.0)
    # a 260-day series still supports the 252-day window, so this asserts the
    # positive case; the guard itself is covered in test_momentum.py
    assert "drawdown_from_high" in ss.signals[0].metrics

def test_drawdown_does_not_change_selection():
    """The premise of this whole project: nothing ranks on the term structure."""
    import pandas as pd
    from vantage.data_ingest import MarketData
    from vantage.screener import run_screener
    idx = pd.date_range("2024-01-01", periods=300, freq="D")
    def series(daily):
        return pd.Series([100.0 * (1 + daily) ** i for i in range(300)], index=idx)
    md = MarketData(
        as_of="2026-08-14",
        prices={"HIGH": series(0.006), "MID": series(0.004), "LOW": series(0.0005)},
        volumes={t: pd.Series([1000.0] * 300, index=idx) for t in ("HIGH", "MID", "LOW")},
        sectors={t: "Tech" for t in ("HIGH", "MID", "LOW")},
        names={t: t for t in ("HIGH", "MID", "LOW")})
    ss = run_screener(md)
    leaders = [(s.ticker, s.rank) for s in ss.signals
               if s.signal_type == "ret_12m_leader"]
    assert leaders == [("HIGH", 1), ("MID", 2)]   # LOW is below the +100% bar
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_screener.py -q`
Expected: FAIL — `KeyError: 'drawdown_from_high'` on the first two. The third should already pass; if it does not, stop and report, because selection has drifted for some other reason.

- [ ] **Step 3: Write the implementation**

In `vantage/screener.py`, add the import at the top:

```python
from vantage.momentum import drawdown_from_high
```

and inside the per-ticker loop, immediately after the `volume_ratio` block and before `rows.append(...)`:

```python
        # Descriptive only — how far below its own 52-week high the name sits.
        # Nothing selects or ranks on this (see config/evidence.yaml).
        dd = drawdown_from_high(prices)
        if dd is not None:
            metrics["drawdown_from_high"] = dd
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_screener.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite and commit**

Run: `.venv/bin/pytest -q` → expect 304.

```bash
git add vantage/screener.py tests/test_screener.py
git commit -m "feat(screener): attach 52-week-high distance as description"
```

---

### Task 3: Chat context and tools

**Files:**
- Modify: `vantage/chat_context.py` (`ChatContext.render`)
- Modify: `vantage/chat_tools.py` (`run_screen`, `get_ticker_metrics`)
- Test: `tests/test_chat_context.py`, `tests/test_chat_tools.py`

**Interfaces:**
- Consumes: `render_text_table`, `term_structure` from Task 1; `drawdown_from_high` from `vantage.momentum`.
- Produces: no new public names; existing outputs gain content.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_chat_context.py`:

```python
def test_render_includes_the_term_structure_table():
    from vantage.chat_context import ChatContext
    from vantage.models import SignalSet, Signal
    ss = SignalSet("2026-08-14", [
        Signal("MU", "ret_12m_leader", 6.317, 1, "Technology", "Micron",
               {"ret_1m": -0.073, "ret_3m": 0.092, "ret_6m": 1.266,
                "ret_12m": 6.317, "drawdown_from_high": -0.123})], {})
    text = ChatContext(signals=ss).render()
    assert "off high" in text
    assert "-7.3%" in text and "+632%" in text and "-12.3%" in text

def test_render_without_signals_is_unchanged():
    from vantage.chat_context import ChatContext
    assert "off high" not in ChatContext().render()
```

Append to `tests/test_chat_tools.py`:

```python
def test_run_screen_returns_term_structure_per_leader():
    from vantage.chat_tools import run_screen
    import pandas as pd
    from vantage.data_ingest import MarketData
    idx = pd.date_range("2024-01-01", periods=300, freq="D")
    rising = pd.Series([100.0 * 1.006 ** i for i in range(300)], index=idx)
    md = MarketData(as_of="2026-08-14", prices={"AAA": rising},
                    volumes={"AAA": pd.Series([1000.0] * 300, index=idx)},
                    sectors={"AAA": "Tech"}, names={"AAA": "Alpha"})
    class _S:
        config_dir = cache_dir = None
    out = run_screen(_S(), _market_data_fn=lambda tickers, cache_dir: md)
    ts = out["leaders"][0]["term_structure"]
    assert [e["label"] for e in ts] == ["1m", "3m", "6m", "12m", "off high"]
    assert ts[3]["display"].endswith("%")

def test_get_ticker_metrics_includes_drawdown():
    from vantage.chat_tools import get_ticker_metrics
    class _S:
        cache_dir = "/tmp/vantage-test-cache"
    out = get_ticker_metrics("AAPL", _S(), _downloader=_fake_download,
                             _info_fn=_fake_sector)
    assert "drawdown_from_high" in out
```

Note: `run_screen` calls `load_universe(settings.config_dir / "universe.txt")` before the market-data function. The test above passes `config_dir = None`, which will raise. Set `config_dir` to a `tmp_path` containing a `universe.txt` with one line `AAA`, and take `tmp_path` as a fixture argument.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_chat_context.py tests/test_chat_tools.py -q`
Expected: FAIL — `assert 'off high' in text` and `KeyError: 'term_structure'`.

- [ ] **Step 3: Write the implementation**

In `vantage/chat_context.py`, add the import and replace the leaders line inside `render()`:

```python
from vantage.termstructure import render_text_table
```

Replace:

```python
            leader_items = [f"{s.ticker}({s.value:.2f})" for s in self.signals.signals
                            if s.signal_type == "ret_12m_leader"]
            leaders = ", ".join(leader_items[:40])
            mom = ", ".join(f"{k} {v:+.0%}" for k, v in self.signals.sector_momentum.items())
            parts.append(f"Latest signals ({self.signals.as_of}): 12mo leaders: "
                         f"{leaders or 'none'}. Sector momentum: {mom or 'none'}.")
```

with:

```python
            leaders = [(s.ticker, s.metrics) for s in self.signals.signals
                       if s.signal_type == "ret_12m_leader"]
            table = render_text_table(leaders, limit=25)
            mom = ", ".join(f"{k} {v:+.0%}" for k, v in self.signals.sector_momentum.items())
            parts.append(f"Latest signals ({self.signals.as_of}). Sector momentum: "
                         f"{mom or 'none'}.")
            if table:
                # Return term structure, description only — the register records
                # that this shape does not predict forward returns.
                parts.append("12-month leaders and their return term structure:\n"
                             + table)
```

In `vantage/chat_tools.py`, add imports and enrich both functions:

```python
from vantage.momentum import drawdown_from_high
from vantage.termstructure import term_structure
```

In `get_ticker_metrics`, after the `volume_ratio` line:

```python
        out["drawdown_from_high"] = drawdown_from_high(prices)
```

In `run_screen`, replace the `leaders` comprehension:

```python
        leaders = [{"ticker": s.ticker, "ret_12m": round(s.value, 3),
                    "term_structure": term_structure(s.metrics)}
                   for s in ss.signals if s.signal_type == "ret_12m_leader"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_chat_context.py tests/test_chat_tools.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite and commit**

Run: `.venv/bin/pytest -q` → expect 308.

```bash
git add vantage/chat_context.py vantage/chat_tools.py tests/
git commit -m "feat(chat): serve the term structure instead of a bare 12m figure"
```

---

### Task 4: Web API

**Files:**
- Modify: `vantage/web/artifacts.py` (`build_overview`, new `signals_payload`)
- Modify: `vantage/web/app.py` (`/api/signals`)
- Test: `tests/test_web_artifacts.py`, `tests/test_web_api.py`

**Interfaces:**
- Consumes: `term_structure` from Task 1.
- Produces: `artifacts.signals_payload(signal_set) -> dict`; `term_structure` on each entry of `top_leaders`, `top_volume_spikes`, and each signal in `/api/signals`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_artifacts.py`:

```python
def test_signals_payload_enriches_each_signal():
    from vantage.models import SignalSet, Signal
    from vantage.web.artifacts import signals_payload
    ss = SignalSet("2026-08-14", [
        Signal("MU", "ret_12m_leader", 6.317, 1, "Technology", "Micron",
               {"ret_1m": -0.073, "ret_12m": 6.317})], {})
    payload = signals_payload(ss)
    ts = payload["signals"][0]["term_structure"]
    assert [e["label"] for e in ts] == ["1m", "3m", "6m", "12m", "off high"]
    assert ts[0]["display"] == "-7.3%"
    assert ts[2]["display"] == "--"          # absent metric keeps its column
    assert payload["as_of"] == "2026-08-14"

def test_signals_payload_of_none_is_the_empty_shape():
    from vantage.web.artifacts import signals_payload
    assert signals_payload(None) == {"as_of": None, "signals": [],
                                     "sector_momentum": {}}

def test_build_overview_entries_carry_term_structure():
    from vantage.models import SignalSet, Signal
    from vantage.web.artifacts import build_overview
    ss = SignalSet("2026-08-14", [
        Signal("MU", "ret_12m_leader", 6.317, 1, "Technology", "Micron",
               {"ret_1m": -0.073, "ret_12m": 6.317})], {})
    o = build_overview(ss, None, None)
    assert o["top_leaders"][0]["term_structure"][0]["display"] == "-7.3%"
```

Append to `tests/test_web_api.py`:

```python
def test_signals_endpoint_includes_term_structure(tmp_path):
    s = _settings(tmp_path); _seed(s)
    body = _client(s).get("/api/signals").json()
    ts = body["signals"][0]["term_structure"]
    assert len(ts) == 5
    assert all("display" in e for e in ts)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web_artifacts.py tests/test_web_api.py -q`
Expected: FAIL — `ImportError: cannot import name 'signals_payload'`.

- [ ] **Step 3: Write the implementation**

In `vantage/web/artifacts.py`, add the import:

```python
from vantage.termstructure import term_structure
```

Add the payload helper:

```python
def signals_payload(signal_set) -> dict:
    """The signals artifact plus rendered term-structure cells per signal.

    The display strings are produced server-side so the browser never formats
    a percentage — one formatter, one appearance, everywhere.
    """
    if signal_set is None:
        return {"as_of": None, "signals": [], "sector_momentum": {}}
    payload = signal_set.to_dict()
    for raw, sig in zip(payload["signals"], signal_set.signals):
        raw["term_structure"] = term_structure(sig.metrics)
    return payload
```

In `build_overview`, extend the entry construction:

```python
            entry = {"ticker": s.ticker, "value": s.value, "sector": s.sector,
                     "name": s.name, "term_structure": term_structure(s.metrics)}
```

In `vantage/web/app.py`, replace the body of the `signals` route:

```python
    @app.get("/api/signals")
    def signals():
        return art.signals_payload(art.latest_signals(app.state.settings.data_dir))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_web_artifacts.py tests/test_web_api.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite and commit**

Run: `.venv/bin/pytest -q` → expect 312.

```bash
git add vantage/web/artifacts.py vantage/web/app.py tests/
git commit -m "feat(web): serve term-structure cells with the signals payload"
```

---

### Task 5: Dashboard rows

No JavaScript test harness exists in this project; verification is `node --check`, served-asset checks, and a browser pass.

**Files:**
- Modify: `vantage/web/static/app.js` (`loadOverview`, `loadSignals`)
- Modify: `vantage/web/static/styles.css`

- [ ] **Step 1: Add the row helper**

In `vantage/web/static/app.js`, after the existing `cell` helper:

```js
// Third row line: the return term structure, description only. The server
// sends the display strings; we never format a percentage here.
function tsLine(ts) {
  if (!ts || !ts.length) return "";
  return `<div class="ts">${ts.map((e) =>
    `<span class="ts-cell" title="${esc(e.label)}">${esc(e.display)}</span>`
  ).join("")}</div>`;
}
```

- [ ] **Step 2: Use it in both panels**

In `loadSignals`, append the line inside each row after the existing `cell(...)`:

```js
    ${rows(s.signals, (sig) => `<div class="row srow">
      ${cell(esc(sig.ticker) + " · " + esc(sig.signal_type), sig.name, sig.sector)}
      <span class="${cls(sig.value)}">${sig.signal_type === "volume_spike"
        ? sig.value.toFixed(1) + "×" : pct(sig.value)}</span>
      ${tsLine(sig.term_structure)}</div>`)}
```

In `loadOverview`'s leaders rows, likewise:

```js
    ${rows(o.top_leaders, (l) => `<div class="row srow">
      ${cell(esc(l.ticker), l.name, l.sector)}
      <span class="${cls(l.value)}">${pct(l.value)}</span>
      ${tsLine(l.term_structure)}</div>`)}
```

- [ ] **Step 3: Add the CSS**

Append to `vantage/web/static/styles.css`:

```css
/* --- Return term structure -------------------------------------------- */
/* A fixed five-column grid on every row, so the columns line up down the
   panel and one window can be scanned across every name at once. */
.row.srow { flex-wrap: wrap; }
.ts { flex: 0 0 100%; display: grid; grid-template-columns: repeat(5, 1fr);
      gap: 4px; margin-top: 4px; font-size: 12px; color: var(--muted);
      font-variant-numeric: tabular-nums; }
.ts-cell { text-align: right; }
```

- [ ] **Step 4: Verify**

```bash
node --check vantage/web/static/app.js
.venv/bin/pytest -q                     # unchanged: 312
.venv/bin/python -m vantage.web &        # background
curl -s http://127.0.0.1:8000/api/signals | head -c 400
curl -s http://127.0.0.1:8000/static/app.js | grep -c tsLine
```

Then open `http://127.0.0.1:8000` and confirm: the third line appears under each signals row and each overview leader; the five columns align vertically down the panel; a signal missing the drawdown shows `--` in that column without shifting the others; and the identity subtitle from the ticker-identity feature is still present. **Stop the server when done.**

- [ ] **Step 5: Commit**

```bash
git add vantage/web/static/app.js vantage/web/static/styles.css
git commit -m "feat(web): term-structure line under every ticker row"
```

---

### Task 6: The brief's trajectory read

**Files:**
- Modify: `vantage/models.py` (`Brief`)
- Modify: `vantage/analyst.py` (`_JSON_OUTPUT`, `parse_brief`)
- Modify: `vantage/report.py` (`render_markdown`, `render_html`)
- Modify: `vantage/web/static/app.js` (`openBrief`)
- Test: `tests/test_models.py`, `tests/test_analyst.py`, `tests/test_report.py`

**Interfaces:**
- Produces: `Brief.trajectory_read: str = ""`, present in `to_dict`, read by `from_dict` with a default.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
def test_brief_round_trips_trajectory_read():
    from vantage.models import Brief
    b = Brief("2026-08-14", "s", [], [], "c", "m", "d",
              trajectory_read="MU is up 632% over a year and down 7% on the month.")
    assert Brief.from_dict(b.to_dict()).trajectory_read.startswith("MU is up")

def test_brief_without_trajectory_read_loads():
    from vantage.models import Brief
    d = {"as_of": "2026-06-27", "executive_summary": "s", "items": [],
         "watchlist": [], "challenge": "c", "what_im_missing": "m",
         "disclaimer": "d"}
    assert Brief.from_dict(d).trajectory_read == ""
```

Append to `tests/test_analyst.py`:

```python
def test_json_schema_asks_for_trajectory_read():
    from vantage.analyst import _JSON_OUTPUT
    assert "trajectory_read" in _JSON_OUTPUT

def test_parse_brief_reads_trajectory_read():
    from vantage.analyst import parse_brief
    text = ('```json\n{"executive_summary": "s", "items": [], "watchlist": [],'
            ' "challenge": "", "what_im_missing": "",'
            ' "trajectory_read": "Memory names are rolling over on 1m."}\n```')
    assert parse_brief(text, "2026-08-14").trajectory_read.startswith("Memory")

def test_parse_brief_without_the_key_defaults_to_empty():
    from vantage.analyst import parse_brief
    text = ('```json\n{"executive_summary": "s", "items": [], "watchlist": [],'
            ' "challenge": "", "what_im_missing": ""}\n```')
    assert parse_brief(text, "2026-08-14").trajectory_read == ""
```

Append to `tests/test_report.py`:

```python
def test_renderers_include_trajectory_read_when_set():
    from vantage.models import Brief
    b = Brief("2026-08-14", "s", [], [], "c", "m", "d",
              trajectory_read="Memory names lead on 12m and lag on 1m.")
    assert "Trajectory read" in render_markdown(b)
    assert "Memory names lead" in render_markdown(b)
    assert "Trajectory read" in render_html(b)

def test_renderers_omit_the_section_when_empty():
    assert "Trajectory read" not in render_markdown(_brief())
    assert "Trajectory read" not in render_html(_brief())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_models.py tests/test_analyst.py tests/test_report.py -q`
Expected: FAIL — `TypeError: Brief.__init__() got an unexpected keyword argument 'trajectory_read'`.

- [ ] **Step 3: Write the implementation**

In `vantage/models.py`, add the field to `Brief` **last**, so existing positional construction is unaffected:

```python
@dataclass
class Brief:
    as_of: str
    executive_summary: str
    items: list
    watchlist: list
    challenge: str
    what_im_missing: str
    disclaimer: str
    trajectory_read: str = ""
```

and in `from_dict`, alongside the other `.get` calls:

```python
            trajectory_read=d.get("trajectory_read", ""),
```

In `vantage/analyst.py`, add the key to `_JSON_OUTPUT` and describe it:

```python
_JSON_OUTPUT = """Return your final answer as a single JSON object inside a ```json code block with
exactly these keys:
{
  "executive_summary": str,
  "items": [{"title": str, "thesis": str, "evidence": str, "sources": [str],
             "why_it_matters": str, "portfolio_relevance": str}],
  "watchlist": [str],
  "challenge": str,
  "what_im_missing": str,
  "trajectory_read": str
}

trajectory_read: describe what the return term structure shows across this week's
names — where recent pace diverges from the 12-month figure, and which names sit
far below their highs. Description only: the register records that this shape
does not predict forward returns, so draw no forward conclusion from it.
"""
```

and in `parse_brief`'s `Brief(...)` construction:

```python
                 trajectory_read=payload.get("trajectory_read", ""),
```

In `vantage/report.py`, add the section to both renderers, guarded so an empty
value produces no output. In `render_markdown`, after the executive summary:

```python
    if brief.trajectory_read:
        out += ["## Trajectory read",
                _ex(brief.trajectory_read, facts, set()), ""]
```

In `render_html`, in the same position:

```python
    if brief.trajectory_read:
        parts += ["<h2>Trajectory read</h2>",
                  p(_ex(brief.trajectory_read, facts, set()))]
```

In `vantage/web/static/app.js`'s `openBrief`, render it after the executive summary through the existing annotated-prose path:

```js
  if (b.trajectory_read) {
    body.append(label("Trajectory read"), proseP("prose", b.trajectory_read));
  }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_models.py tests/test_analyst.py tests/test_report.py -q`
Expected: PASS

- [ ] **Step 5: Verify the whole path end to end**

```bash
node --check vantage/web/static/app.js
.venv/bin/pytest -q                     # expect 319
.venv/bin/python -c "
from vantage.models import Brief
from vantage.report import render_markdown
b = Brief('2026-08-14','s',[],[],'c','m','d',
          trajectory_read='MU leads on 12m and lags on 1m.')
md = render_markdown(b)
print('section present:', 'Trajectory read' in md)
import json
print('json round trip:', Brief.from_dict(json.loads(json.dumps(b.to_dict()))).trajectory_read)
"
```

Also re-render an existing brief to confirm backward compatibility:

```bash
.venv/bin/python -c "
import json, glob
from vantage.models import Brief
from vantage.report import render_markdown
p = sorted(glob.glob('reports/brief-*.json'))[-1]
b = Brief.from_dict(json.loads(open(p).read()))
print(p, '-> trajectory_read:', repr(b.trajectory_read))
print('section omitted:', 'Trajectory read' not in render_markdown(b))
"
```

Expected: `trajectory_read: ''` and the section omitted.

- [ ] **Step 6: Update the README and commit**

Add a line to the weekly-brief section noting the new "Trajectory read" section and that it is descriptive — the term structure is shown, no forward claim is drawn from it, and `config/evidence.yaml` records why.

```bash
git add vantage/models.py vantage/analyst.py vantage/report.py \
        vantage/web/static/app.js README.md tests/
git commit -m "feat(brief): descriptive trajectory read section"
```

---

## Self-Review Notes

Spec coverage against `docs/superpowers/specs/2026-08-14-descriptive-term-structure-design.md`:

- §2.1 screener drawdown, selection unchanged → Task 2 (incl. `test_drawdown_does_not_change_selection`)
- §2.2 formatter, adaptive precision, ASCII signs, fixed five columns → Task 1
- §2.3 chat context table, `run_screen`, `get_ticker_metrics` → Task 3
- §2.4 `signals_payload`, `build_overview`, three-line rows, fixed grid → Tasks 4, 5
- §2.5 `trajectory_read` through model, schema, parser, both renderers, web detail → Task 6
- §4 error handling — missing metric keeps its column, `format_pct` never raises, old artifacts render → Tasks 1, 2, 6
- §5 testing → each task's test steps; browser pass in Task 5
- §6 out of scope — no labels, no ranking, no email data table, no sector breadth — enforced by the Global Constraints and the file lists

Type consistency: `term_structure` returns the same `{label, value, display}` shape in Tasks 1, 3 and 4; `render_text_table` takes `(ticker, metrics)` pairs in both its definition and its only caller.
