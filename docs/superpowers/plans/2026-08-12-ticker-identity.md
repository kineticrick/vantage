# Ticker Identity (Name + Sector) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the company name and sector next to every ticker reference in the Vantage web dashboard and the emailed brief.

**Architecture:** One new resolver unit (`vantage/tickers.py`) owns the ticker→facts map and the rules for spotting a ticker in prose. The yfinance `.info` call that `data_ingest` already makes for sector starts keeping the company name too, cached in the existing `cache/sectors.json`. Two consumers render it: the dashboard (structured rows get a `name · sector` subtitle; prose gets dotted-underline hover tooltips) and the report renderers (inline expansion on first mention per section, since mail clients can't be trusted with CSS tooltips).

**Tech Stack:** Python 3.14, FastAPI, pandas, yfinance, pytest; vanilla JS/CSS (no frontend framework or build step).

**Spec:** `docs/superpowers/specs/2026-08-12-ticker-identity-design.md`

## Global Constraints

- Run everything with the project venv: `.venv/bin/python`, `.venv/bin/pytest`.
- **No new runtime dependencies.** The name comes from the `yfinance` `.info` call already being made.
- The facts cache file stays at `cache/sectors.json` (name deliberately kept; 915 existing entries must remain valid). Entries grow from `{"sector", "fetched"}` to `{"sector", "name", "fetched"}`.
- **Never build user-facing text with `innerHTML`.** Prose goes through DOM text nodes (`textContent` / `createTextNode`). This preserves the XSS posture from commits `5107bda` and `dd94d10`.
- Backward compatibility: `data/signals-*.json` and `reports/brief-*.json` written before this change must still load.
- `reports/brief-*.json` is never annotated — it stays the raw structured source of truth. Annotation happens at render time only and must not mutate the `Brief` object.
- All file reads/writes of artifacts use `encoding="utf-8"` (existing convention).
- The stoplist and price-cue rule live in `vantage/tickers.py` and are the single source of truth; the frontend receives the verdict via the `common_word` flag on `/api/tickers`.
- Full suite baseline before starting: **67 tests passing** (`.venv/bin/pytest -q`).
- **Environment note (2026-08-12):** the system upgraded to Python 3.14.4 and removed 3.13, which broke the original venv. It was rebuilt with `virtualenv -p /usr/bin/python3.14 .venv` (plain `python3 -m venv` fails — `python3.14-venv` is not installed) and `pip install -r requirements.txt`. This pulled **pandas 3.0.5** (was 2.x). The full suite passes on it. If a task hits a pandas API that changed in 3.0, fix the call site rather than pinning pandas back.

---

### Task 1: Ticker facts resolver

**Files:**
- Create: `vantage/tickers.py`
- Test: `tests/test_tickers.py`

**Interfaces:**
- Consumes: `vantage.models.PortfolioContext`, `vantage.models.Holding` (both exist).
- Produces:
  - `TickerFacts(ticker: str, name: str | None = None, sector: str | None = None)` with method `subtitle(sep: str = " · ") -> str`
  - `load_cache_facts(cache_dir) -> dict[str, TickerFacts]`
  - `load_facts(cache_dir, portfolio=None) -> dict[str, TickerFacts]`
  - `resolve(ticker: str, facts: dict) -> TickerFacts`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tickers.py`:

```python
import json
from vantage.models import PortfolioContext, Holding
from vantage.tickers import TickerFacts, load_cache_facts, load_facts, resolve

def _write_cache(tmp_path, data):
    (tmp_path / "sectors.json").write_text(json.dumps(data), encoding="utf-8")
    return tmp_path

def test_subtitle_joins_known_parts():
    assert TickerFacts("MU", "Micron Technology", "Technology").subtitle() == \
        "Micron Technology · Technology"
    assert TickerFacts("MU", "Micron Technology").subtitle() == "Micron Technology"
    assert TickerFacts("MU", None, "Technology").subtitle() == "Technology"
    assert TickerFacts("MU").subtitle() == ""
    assert TickerFacts("MU", "Micron Technology", "Technology").subtitle(sep=", ") == \
        "Micron Technology, Technology"

def test_load_cache_facts_reads_name_and_sector(tmp_path):
    _write_cache(tmp_path, {"MU": {"sector": "Technology",
                                   "name": "Micron Technology",
                                   "fetched": "2026-08-11"}})
    facts = load_cache_facts(tmp_path)
    assert facts["MU"].name == "Micron Technology"
    assert facts["MU"].sector == "Technology"
    assert facts["MU"].ticker == "MU"

def test_load_cache_facts_tolerates_legacy_entries_without_name(tmp_path):
    _write_cache(tmp_path, {"AOS": {"sector": "Industrials", "fetched": "2026-08-11"}})
    facts = load_cache_facts(tmp_path)
    assert facts["AOS"].sector == "Industrials"
    assert facts["AOS"].name is None

def test_load_cache_facts_missing_or_corrupt_returns_empty(tmp_path):
    assert load_cache_facts(tmp_path) == {}
    (tmp_path / "sectors.json").write_text("{not json", encoding="utf-8")
    assert load_cache_facts(tmp_path) == {}

def test_load_facts_layers_portfolio_over_cache(tmp_path):
    _write_cache(tmp_path, {"NVDA": {"sector": "Tech", "name": "NVIDIA Corp",
                                     "fetched": "2026-08-11"}})
    pf = PortfolioContext(available=True, holdings=[
        Holding("NVDA", "NVIDIA Corporation", 10, 100, sector="Technology"),
        Holding("SMH", "VanEck Semiconductor ETF", 5, 50, sector="Technology"),
    ])
    facts = load_facts(tmp_path, portfolio=pf)
    # portfolio wins where it has a value
    assert facts["NVDA"].name == "NVIDIA Corporation"
    assert facts["NVDA"].sector == "Technology"
    # portfolio adds tickers the cache never had (ETFs)
    assert facts["SMH"].name == "VanEck Semiconductor ETF"

def test_load_facts_portfolio_gap_falls_back_to_cache(tmp_path):
    _write_cache(tmp_path, {"NVDA": {"sector": "Technology", "name": "NVIDIA Corp",
                                     "fetched": "2026-08-11"}})
    pf = PortfolioContext(available=True,
                          holdings=[Holding("NVDA", "", 10, 100, sector=None)])
    facts = load_facts(tmp_path, portfolio=pf)
    assert facts["NVDA"].name == "NVIDIA Corp"
    assert facts["NVDA"].sector == "Technology"

def test_load_facts_ignores_unavailable_portfolio(tmp_path):
    _write_cache(tmp_path, {"MU": {"sector": "Technology", "name": "Micron",
                                   "fetched": "2026-08-11"}})
    pf = PortfolioContext(available=False, note="db down")
    assert load_facts(tmp_path, portfolio=pf)["MU"].name == "Micron"

def test_resolve_unknown_ticker_returns_bare_facts():
    f = resolve("ZZZZ", {})
    assert f.ticker == "ZZZZ" and f.name is None and f.sector is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_tickers.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vantage.tickers'`

- [ ] **Step 3: Write minimal implementation**

Create `vantage/tickers.py`:

```python
"""Ticker identity: what a symbol's company name and sector are.

Single source of truth for turning a bare symbol into something a human
recognizes. Facts come from two places, highest priority first: the user's
Wake holdings (authoritative for what they own, and the only source that
names their ETFs) and the yfinance-derived cache written by data_ingest.
"""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TickerFacts:
    ticker: str
    name: str | None = None
    sector: str | None = None

    def subtitle(self, sep: str = " · ") -> str:
        """Human label from whatever is known; empty string if nothing is."""
        return sep.join(p for p in (self.name, self.sector) if p)


def _cache_path(cache_dir) -> Path:
    # Filename kept as sectors.json so the existing cache stays valid.
    return Path(cache_dir) / "sectors.json"


def load_cache_facts(cache_dir) -> dict:
    p = _cache_path(cache_dir)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    if not isinstance(raw, dict):
        # Valid JSON but not an object (e.g. "[]" or "null") is still corrupt
        # from this cache's perspective.
        return {}
    return {t: TickerFacts(ticker=t, name=e.get("name"), sector=e.get("sector"))
            for t, e in raw.items() if isinstance(e, dict)}


def load_facts(cache_dir, portfolio=None) -> dict:
    """Cache facts, overlaid with portfolio holdings where those know better."""
    facts = load_cache_facts(cache_dir)
    if portfolio is not None and getattr(portfolio, "available", False):
        for h in portfolio.holdings:
            if not h.ticker:
                continue
            cached = facts.get(h.ticker)
            facts[h.ticker] = TickerFacts(
                ticker=h.ticker,
                name=h.name or (cached.name if cached else None),
                sector=h.sector or (cached.sector if cached else None),
            )
    return facts


def resolve(ticker, facts) -> TickerFacts:
    """Never raises — an unknown ticker resolves to bare facts."""
    return facts.get(ticker) or TickerFacts(ticker=ticker)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_tickers.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add vantage/tickers.py tests/test_tickers.py
git commit -m "feat(tickers): ticker facts resolver over cache + portfolio holdings"
```

---

### Task 2: Prose ticker detection and inline expansion

**Files:**
- Modify: `vantage/tickers.py` (append; do not touch Task 1 functions)
- Test: `tests/test_tickers.py` (append)

**Interfaces:**
- Consumes: `TickerFacts`, `resolve` from Task 1.
- Produces:
  - `COMMON_WORD_TICKERS: frozenset[str]`
  - `TICKER_RE: re.Pattern` — the shared symbol shape
  - `is_common_word(ticker: str) -> bool`
  - `find_mentions(text: str, facts: dict) -> list[tuple[int, int, str]]` — `(start, end, ticker)` for accepted mentions
  - `expand_first_mention(text: str, facts: dict, seen: set | None = None) -> str`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tickers.py`:

```python
from vantage.tickers import (COMMON_WORD_TICKERS, is_common_word,
                             find_mentions, expand_first_mention)

_FACTS = {
    "MU": TickerFacts("MU", "Micron Technology", "Technology"),
    "WDC": TickerFacts("WDC", "Western Digital", "Technology"),
    "ALL": TickerFacts("ALL", "Allstate Corp", "Financial Services"),
    "BRK-B": TickerFacts("BRK-B", "Berkshire Hathaway", "Financial Services"),
    "NONAME": TickerFacts("NONAME"),
}

def test_is_common_word():
    assert is_common_word("ALL") and is_common_word("IT") and is_common_word("ON")
    assert not is_common_word("MU") and not is_common_word("NVDA")

def test_find_mentions_only_known_tickers():
    found = [t for _, _, t in find_mentions("MU and WDC led; ZZZZ did not", _FACTS)]
    assert found == ["MU", "WDC"]

def test_find_mentions_skips_common_words_without_price_cue():
    assert find_mentions("This is ALL of the story", _FACTS) == []

def test_find_mentions_accepts_common_word_with_price_cue():
    assert [t for _, _, t in find_mentions("ALL +32% on the year", _FACTS)] == ["ALL"]
    assert [t for _, _, t in find_mentions("ALL $214 a share", _FACTS)] == ["ALL"]

def test_find_mentions_handles_dotted_class_shares():
    assert [t for _, _, t in find_mentions("BRK-B lagged", _FACTS)] == ["BRK-B"]

def test_expand_first_mention_expands_once():
    out = expand_first_mention("MU rose, then MU fell", _FACTS)
    assert out == "MU (Micron Technology, Technology) rose, then MU fell"

def test_expand_first_mention_shares_seen_across_calls():
    seen = set()
    a = expand_first_mention("MU rose", _FACTS, seen)
    b = expand_first_mention("MU fell", _FACTS, seen)
    assert "Micron Technology" in a
    assert b == "MU fell"

def test_expand_first_mention_fresh_seen_expands_again():
    a = expand_first_mention("MU rose", _FACTS, set())
    b = expand_first_mention("MU fell", _FACTS, set())
    assert "Micron Technology" in a and "Micron Technology" in b

def test_expand_first_mention_skips_ticker_with_no_facts():
    assert expand_first_mention("NONAME moved", _FACTS) == "NONAME moved"

def test_expand_first_mention_leaves_unknown_text_untouched():
    assert expand_first_mention("nothing to see here", _FACTS) == "nothing to see here"

def test_expand_first_mention_handles_empty_text():
    assert expand_first_mention("", _FACTS) == ""
    assert expand_first_mention(None, _FACTS) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_tickers.py -q`
Expected: FAIL — `ImportError: cannot import name 'COMMON_WORD_TICKERS'`

- [ ] **Step 3: Write minimal implementation**

Append to `vantage/tickers.py` (and add `import re` to the imports at the top):

```python
# --- Prose detection -------------------------------------------------------
# Tickers that are also ordinary English words. Annotating these on sight
# would light up normal prose ("it", "all", "on"), so they are skipped unless
# the surrounding text carries a price/percent cue. Biased toward
# under-annotating: a missed tooltip is invisible, a wrong one is a bug.
COMMON_WORD_TICKERS = frozenset({
    "ALL", "ANY", "ARE", "BIG", "CAR", "CARS", "CAT", "EAT", "EDIT", "FAST",
    "FIX", "FOR", "FUN", "GO", "GOOD", "HAS", "HE", "IT", "JOB", "KEY", "LOVE",
    "MAIN", "NEW", "NOW", "ON", "ONE", "OPEN", "OUT", "PLAY", "REAL", "RUN",
    "SEE", "SO", "TRUE", "TWO", "UP", "WELL", "YOU",
})

# A symbol: 1-5 uppercase alphanumerics, optionally a class suffix (BRK-B).
TICKER_RE = re.compile(r"\b[A-Z][A-Z0-9]{0,4}(?:-[A-Z])?\b")

# A price/percent cue immediately after a symbol: "+32%", "$214", "is 12".
_CUE_RE = re.compile(r"^\s*(?:is\s+|at\s+)?[+\-]?\$?\d")


def is_common_word(ticker) -> bool:
    return str(ticker).upper() in COMMON_WORD_TICKERS


def _has_price_cue(text, end) -> bool:
    return bool(_CUE_RE.match(text[end:end + 12]))


def find_mentions(text, facts) -> list:
    """Spans of ticker mentions we are confident about, left to right."""
    text = text or ""
    out = []
    for m in TICKER_RE.finditer(text):
        t = m.group(0)
        if t not in facts:
            continue
        if is_common_word(t) and not _has_price_cue(text, m.end()):
            continue
        out.append((m.start(), m.end(), t))
    return out


def expand_first_mention(text, facts, seen=None) -> str:
    """Append "(Name, Sector)" after the first mention of each ticker.

    `seen` is shared across calls that belong to the same section, so a name
    is not repeated within one section but is reintroduced in the next.
    """
    text = text or ""
    seen = seen if seen is not None else set()
    parts, last = [], 0
    for start, end, t in find_mentions(text, facts):
        if t in seen:
            continue
        detail = resolve(t, facts).subtitle(sep=", ")
        if not detail:
            continue
        seen.add(t)
        parts.append(text[last:end])
        parts.append(f" ({detail})")
        last = end
    parts.append(text[last:])
    return "".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_tickers.py -q`
Expected: PASS (19 tests total in this file)

- [ ] **Step 5: Commit**

```bash
git add vantage/tickers.py tests/test_tickers.py
git commit -m "feat(tickers): conservative prose detection + inline first-mention expansion"
```

---

### Task 3: Capture company name during market-data fetch

Renames the sector-only injection seam to an info seam and threads `name` through `MarketData` → `Signal` → `signals-*.json`. Existing callers and tests that pass `_sector_fn` must be updated in the same commit or the suite breaks.

**Files:**
- Modify: `vantage/data_ingest.py:23-29` (`_default_sector_fn`), `:61-73` (`_sector_for`), `:75-111` (`fetch_market_data`), `:11-16` (`MarketData`)
- Modify: `vantage/models.py:5-12` (`Signal`)
- Modify: `vantage/screener.py:34-72`
- Modify: `vantage/chat_tools.py:5-13`
- Modify: `tests/test_data_ingest.py` (9 `_sector_fn` references)
- Modify: `tests/test_chat_tools.py:33,44`
- Test: `tests/test_data_ingest.py`, `tests/test_screener.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: nothing from Tasks 1-2.
- Produces:
  - `MarketData(as_of, prices, volumes, sectors, names)` — `names: dict[str, str | None]`
  - `fetch_market_data(tickers, cache_dir, batch_size=100, period="2y", _downloader=None, _info_fn=None)`
  - `_default_info_fn(ticker) -> dict` with keys `{"sector", "name"}`
  - `Signal(ticker, signal_type, value, rank, sector=None, name=None, metrics={})` — `name` inserted **after** `sector`, before `metrics`
  - `get_ticker_metrics(ticker, settings, _downloader=None, _info_fn=None) -> dict` now includes a `"name"` key

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_data_ingest.py`:

```python
def _fake_info(ticker):
    return {"AAPL": {"sector": "Technology", "name": "Apple Inc."},
            "MU": {"sector": "Technology", "name": "Micron Technology"}}.get(
                ticker, {"sector": "Unknown", "name": None})

def test_fetch_market_data_captures_names(tmp_path):
    md = fetch_market_data(["AAPL", "MU"], cache_dir=tmp_path, batch_size=2,
                           _downloader=_fake_download, _info_fn=_fake_info)
    assert md.names["AAPL"] == "Apple Inc."
    assert md.sectors["MU"] == "Technology"

def test_name_survives_cache_round_trip(tmp_path):
    fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1,
                      _downloader=_fake_download, _info_fn=_fake_info)
    md2 = fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1,
                            _downloader=_fake_download, _info_fn=_fake_info)
    assert md2.names["AAPL"] == "Apple Inc."

def test_legacy_cache_entry_without_name_is_refetched(tmp_path):
    import json
    from datetime import date
    # A fresh-by-age entry from before names existed.
    (tmp_path / "sectors.json").write_text(json.dumps(
        {"AAPL": {"sector": "Technology", "fetched": date.today().isoformat()}}))
    calls = {"n": 0}
    def counting_info(t):
        calls["n"] += 1
        return _fake_info(t)
    md = fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1,
                           _downloader=_fake_download, _info_fn=counting_info)
    assert calls["n"] == 1              # missing name => stale, re-fetched
    assert md.names["AAPL"] == "Apple Inc."
```

Append to `tests/test_screener.py`:

```python
def test_screener_carries_name_onto_signals():
    from vantage.data_ingest import MarketData
    from vantage.screener import run_screener
    import pandas as pd
    idx = pd.date_range("2024-01-01", periods=300, freq="D")
    rising = pd.Series([100.0 + i for i in range(300)], index=idx)
    md = MarketData(as_of="2026-08-12", prices={"MU": rising},
                    volumes={"MU": pd.Series([1000.0] * 300, index=idx)},
                    sectors={"MU": "Technology"},
                    names={"MU": "Micron Technology"})
    ss = run_screener(md)
    assert ss.signals[0].name == "Micron Technology"
    assert ss.signals[0].sector == "Technology"
```

Append to `tests/test_models.py`:

```python
def test_signal_loads_from_legacy_json_without_name(tmp_path):
    import json
    from vantage.models import SignalSet
    p = tmp_path / "signals-2026-06-27.json"
    p.write_text(json.dumps({
        "as_of": "2026-06-27",
        "signals": [{"ticker": "MU", "signal_type": "ret_12m_leader",
                     "value": 1.4, "rank": 1, "sector": "Technology",
                     "metrics": {}}],
        "sector_momentum": {}}))
    ss = SignalSet.load(p)
    assert ss.signals[0].ticker == "MU"
    assert ss.signals[0].name is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_data_ingest.py tests/test_screener.py tests/test_models.py -q`
Expected: FAIL — `TypeError: fetch_market_data() got an unexpected keyword argument '_info_fn'`, `MarketData() got an unexpected keyword argument 'names'`, and `AttributeError: 'Signal' object has no attribute 'name'`

- [ ] **Step 3: Write the implementation**

In `vantage/models.py`, add `name` to `Signal` **after** `sector` (positional callers pass at most 5 args, so this is safe):

```python
@dataclass
class Signal:
    ticker: str
    signal_type: str
    value: float
    rank: int
    sector: str | None = None
    name: str | None = None
    metrics: dict = field(default_factory=dict)
```

In `vantage/data_ingest.py`, replace `_default_sector_fn` (lines 23-29):

```python
def _default_info_fn(ticker):
    """Sector and company name from one .info call (the name used to be discarded)."""
    import yfinance as yf
    try:
        info = yf.Ticker(ticker).info
        return {"sector": info.get("sector") or "Unknown",
                "name": info.get("longName") or info.get("shortName") or None}
    except Exception:
        return {"sector": "Unknown", "name": None}
```

Add `names` to `MarketData`:

```python
@dataclass
class MarketData:
    as_of: str
    prices: dict = field(default_factory=dict)
    volumes: dict = field(default_factory=dict)
    sectors: dict = field(default_factory=dict)
    names: dict = field(default_factory=dict)
```

Replace `_sector_for` with `_facts_for` (note the extra staleness condition):

```python
def _facts_for(ticker, cache, info_fn, today):
    """Cached {sector, name}, re-fetching when absent, aged out, or name-less."""
    entry = cache.get(ticker)
    # An entry predating company names is stale regardless of age — this is how
    # the cache self-heals without a migration step.
    if entry and "name" in entry:
        try:
            age = (today - date.fromisoformat(entry["fetched"])).days
            if age < SECTOR_TTL_DAYS:
                return entry
        except (ValueError, KeyError, TypeError):
            pass  # malformed entry — re-fetch below
    info = info_fn(ticker)
    cache[ticker] = {"sector": info.get("sector") or "Unknown",
                     "name": info.get("name"), "fetched": today.isoformat()}
    return cache[ticker]
```

Update `fetch_market_data`: rename the parameter, and collect names.

```python
def fetch_market_data(tickers, cache_dir, batch_size=100, period="2y",
                      _downloader=None, _info_fn=None) -> MarketData:
```

Inside it, replace the `sector_fn` line, the accumulator line, the per-ticker assignment, and the return:

```python
    info_fn = _info_fn or _default_info_fn
    ...
    prices, volumes, sectors, names = {}, {}, {}, {}
    ...
            facts = _facts_for(t, sector_cache, info_fn, today)
            sectors[t] = facts.get("sector") or "Unknown"
            names[t] = facts.get("name")
    ...
    return MarketData(as_of=today.isoformat(), prices=prices, volumes=volumes,
                      sectors=sectors, names=names)
```

In `vantage/screener.py`, carry the name through. The `rows` tuples become 4-wide:

```python
        rows.append((ticker, market_data.sectors.get(ticker, "Unknown"),
                     market_data.names.get(ticker), metrics))
```

Update the sort key to index 3, both unpack sites, and both `Signal(...)` constructions:

```python
    rows.sort(key=lambda r: r[3].get("ret_12m", float("-inf")), reverse=True)

    signals = []
    rank = 0
    for ticker, sector, name, metrics in rows:
        ret12 = metrics.get("ret_12m")
        if ret12 is not None and ret12 >= return_leader_threshold:
            rank += 1
            signals.append(Signal(ticker=ticker, signal_type="ret_12m_leader",
                                  value=ret12, rank=rank, sector=sector,
                                  name=name, metrics=metrics))
        vr = metrics.get("volume_ratio")
        if vr is not None and vr >= volume_spike_ratio:
            signals.append(Signal(ticker=ticker, signal_type="volume_spike",
                                  value=vr, rank=0, sector=sector, name=name,
                                  metrics=metrics))
```

And the sector-momentum loop:

```python
    for _, sector, _name, metrics in rows:
```

In `vantage/chat_tools.py`, rename the seam and surface the name so the chat analyst can say it:

```python
def get_ticker_metrics(ticker, settings, _downloader=None, _info_fn=None) -> dict:
    ...
        md = fetch_market_data([ticker], cache_dir=settings.cache_dir,
                               _downloader=_downloader, _info_fn=_info_fn)
    ...
        out = {"ticker": ticker, "name": md.names.get(ticker),
               "sector": md.sectors.get(ticker, "Unknown")}
```

- [ ] **Step 4: Update the existing tests that use the old seam**

In `tests/test_data_ingest.py`, replace the `_fake_sector` helper and all 9 `_sector_fn=` call sites. The helper becomes:

```python
def _fake_sector(ticker):
    return {"sector": {"AAPL": "Technology", "MU": "Technology"}.get(ticker, "Unknown"),
            "name": {"AAPL": "Apple Inc.", "MU": "Micron Technology"}.get(ticker)}
```

Then `sed`-style rename every `_sector_fn=` to `_info_fn=` in that file, and in the sector-caching test rename `counting_sector` usage accordingly. In `tests/test_chat_tools.py:33,44`, change `_sector_fn=_fake_sector` to `_info_fn=_fake_sector` and update that file's `_fake_sector` helper to return the same dict shape.

Run: `.venv/bin/pytest tests/test_data_ingest.py tests/test_chat_tools.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: PASS — 67 original + 4 new tests, no failures. If `tests/test_web_refresh.py` or `tests/test_run_weekly.py` fail on the `MarketData` constructor, add `names={}` to their fixtures.

- [ ] **Step 6: Commit**

```bash
git add vantage/data_ingest.py vantage/models.py vantage/screener.py \
        vantage/chat_tools.py tests/
git commit -m "feat(data): keep company name from the .info call already made"
```

---

### Task 4: Backfill tool for the 915 cached tickers

Existing cache entries were written today (2026-08-11) and are age-fresh until ~2026-09-10, so without this they would show sectors but no names for a month.

**Files:**
- Create: `tools/backfill_ticker_names.py`
- Test: `tests/test_backfill_names.py`

**Interfaces:**
- Consumes: `vantage.data_ingest._default_info_fn`, `SECTOR_TTL_DAYS`.
- Produces: `backfill(cache_dir, info_fn=None, save_every=25, log=print) -> dict` returning `{"filled": int, "skipped": int, "failed": int}`

- [ ] **Step 1: Write the failing test**

Create `tests/test_backfill_names.py`:

```python
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from backfill_ticker_names import backfill

def _cache(tmp_path, data):
    (tmp_path / "sectors.json").write_text(json.dumps(data), encoding="utf-8")

def test_backfill_fills_only_missing_names(tmp_path):
    _cache(tmp_path, {"MU": {"sector": "Technology", "fetched": "2026-08-11"},
                      "AAPL": {"sector": "Technology", "name": "Apple Inc.",
                               "fetched": "2026-08-11"}})
    calls = []
    def info_fn(t):
        calls.append(t)
        return {"sector": "Technology", "name": "Micron Technology"}
    stats = backfill(tmp_path, info_fn=info_fn, log=lambda *a: None)
    assert calls == ["MU"]                      # AAPL already had a name
    assert stats == {"filled": 1, "skipped": 1, "failed": 0}
    saved = json.loads((tmp_path / "sectors.json").read_text())
    assert saved["MU"]["name"] == "Micron Technology"
    assert saved["MU"]["sector"] == "Technology"
    assert saved["AAPL"]["name"] == "Apple Inc."

def test_backfill_survives_a_failing_ticker(tmp_path):
    _cache(tmp_path, {"BAD": {"sector": "Technology", "fetched": "2026-08-11"},
                      "MU": {"sector": "Technology", "fetched": "2026-08-11"}})
    def info_fn(t):
        if t == "BAD":
            raise RuntimeError("network down")
        return {"sector": "Technology", "name": "Micron Technology"}
    stats = backfill(tmp_path, info_fn=info_fn, log=lambda *a: None)
    assert stats["failed"] == 1 and stats["filled"] == 1
    saved = json.loads((tmp_path / "sectors.json").read_text())
    assert saved["MU"]["name"] == "Micron Technology"

def test_backfill_on_missing_cache_is_a_noop(tmp_path):
    assert backfill(tmp_path, info_fn=lambda t: {}, log=lambda *a: None) == \
        {"filled": 0, "skipped": 0, "failed": 0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_backfill_names.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backfill_ticker_names'`

- [ ] **Step 3: Write the implementation**

Create `tools/backfill_ticker_names.py`:

```python
"""Fill company names into cache/sectors.json for already-cached tickers.

Entries written before names existed are age-fresh for 30 days, so they would
not re-fetch on their own. This walks them once. Writes incrementally, so it
is safe to interrupt and re-run — completed tickers are skipped.

Run:  .venv/bin/python tools/backfill_ticker_names.py
Tooling only; the weekly pipeline never needs it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vantage.data_ingest import _default_info_fn  # noqa: E402


def _cache_path(cache_dir):
    return Path(cache_dir) / "sectors.json"


def backfill(cache_dir, info_fn=None, save_every=25, log=print) -> dict:
    info_fn = info_fn or _default_info_fn
    path = _cache_path(cache_dir)
    if not path.exists():
        log(f"No cache at {path}; nothing to do.")
        return {"filled": 0, "skipped": 0, "failed": 0}
    cache = json.loads(path.read_text(encoding="utf-8"))
    todo = [t for t, e in cache.items() if isinstance(e, dict) and "name" not in e]
    stats = {"filled": 0, "skipped": len(cache) - len(todo), "failed": 0}
    log(f"{len(todo)} of {len(cache)} tickers need names.")
    for n, ticker in enumerate(todo, 1):
        try:
            info = info_fn(ticker)
            cache[ticker]["name"] = info.get("name")
            if info.get("sector"):
                cache[ticker]["sector"] = info["sector"]
            stats["filled"] += 1
        except Exception as e:  # one bad ticker must never end the run
            log(f"  {ticker}: {e}")
            stats["failed"] += 1
        if n % save_every == 0:
            path.write_text(json.dumps(cache), encoding="utf-8")
            log(f"  {n}/{len(todo)} …")
    path.write_text(json.dumps(cache), encoding="utf-8")
    log(f"Done: {stats}")
    return stats


if __name__ == "__main__":
    from vantage.settings import load_settings
    backfill(load_settings().cache_dir)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_backfill_names.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/backfill_ticker_names.py tests/test_backfill_names.py
git commit -m "feat(tools): backfill company names into the existing facts cache"
```

---

### Task 5: Inline expansion in the emailed brief

**Files:**
- Modify: `vantage/report.py:5-22` (`render_markdown`), `:30-51` (`render_html`), `:53-77` (save functions)
- Modify: `run_weekly.py:29-56`
- Test: `tests/test_report.py`, `tests/test_run_weekly.py`

**Interfaces:**
- Consumes: `expand_first_mention` from Task 2, `load_facts` from Task 1.
- Produces:
  - `render_markdown(brief, facts=None) -> str`
  - `render_html(brief, facts=None) -> str`
  - `save_markdown(brief, reports_dir, facts=None)`, `save_html(brief, reports_dir, facts=None)`, `save_report(brief, reports_dir, facts=None) -> Path`
  - `save_brief_json` is unchanged and takes no `facts`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report.py`:

```python
from vantage.tickers import TickerFacts

_FACTS = {"MU": TickerFacts("MU", "Micron Technology", "Technology"),
          "NVDA": TickerFacts("NVDA", "NVIDIA Corporation", "Technology"),
          "WDC": TickerFacts("WDC", "Western Digital", "Technology")}

def test_render_markdown_without_facts_is_unchanged():
    assert render_markdown(_brief()) == render_markdown(_brief(), facts=None)

def test_render_markdown_expands_first_mention():
    md = render_markdown(_brief(), facts=_FACTS)
    assert "MU (Micron Technology, Technology)" in md
    assert "WDC (Western Digital, Technology)" in md      # challenge section
    assert "NVDA (NVIDIA Corporation, Technology)" in md  # watchlist

def test_render_html_expands_and_still_escapes():
    from vantage.models import Brief, BriefItem
    b = Brief(as_of="2026-06-26", executive_summary="MU <script>x</script> up",
              items=[], watchlist=[], challenge="", what_im_missing="",
              disclaimer="d")
    html = render_html(b, facts=_FACTS)
    assert "MU (Micron Technology, Technology)" in html
    assert "<script>" not in html and "&lt;script&gt;" in html

def test_expansion_resets_between_sections():
    from vantage.models import Brief
    b = Brief(as_of="2026-06-26", executive_summary="MU leads",
              items=[], watchlist=[], challenge="MU again",
              what_im_missing="", disclaimer="d")
    md = render_markdown(b, facts=_FACTS)
    assert md.count("MU (Micron Technology, Technology)") == 2

def test_save_report_annotates_md_and_html_but_not_json(tmp_path):
    import json
    save_report(_brief(), tmp_path, facts=_FACTS)
    md = (tmp_path / "brief-2026-06-26.md").read_text(encoding="utf-8")
    html = (tmp_path / "brief-2026-06-26.html").read_text(encoding="utf-8")
    raw = json.loads((tmp_path / "brief-2026-06-26.json").read_text(encoding="utf-8"))
    assert "Micron Technology" in md and "Micron Technology" in html
    assert "Micron Technology" not in json.dumps(raw)

def test_rendering_does_not_mutate_the_brief():
    b = _brief()
    before = b.items[0].evidence
    render_markdown(b, facts=_FACTS)
    assert b.items[0].evidence == before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_report.py -q`
Expected: FAIL — `TypeError: render_markdown() got an unexpected keyword argument 'facts'`

- [ ] **Step 3: Write the implementation**

In `vantage/report.py`, add the import and a helper, then thread `facts` through. Each section builds its own `seen` set; a brief item shares one set across its four fields so the name is not repeated four times in one item.

```python
from vantage.tickers import expand_first_mention

def _ex(text, facts, seen):
    """Expand ticker mentions in one field, or pass the text through untouched."""
    if not facts:
        return str(text)
    return expand_first_mention(str(text), facts, seen)
```

`render_markdown` becomes:

```python
def render_markdown(brief, facts=None) -> str:
    out = [f"# Blind-Spot Radar — Weekly Brief ({brief.as_of})", ""]
    out += ["## Executive summary",
            _ex(brief.executive_summary, facts, set()), ""]
    out.append("## Notable items")
    for i in brief.items:
        seen = set()  # one item = one section, so names don't repeat per field
        out += [f"### {i.title}",
                f"**Thesis:** {_ex(i.thesis, facts, seen)}",
                f"**Evidence:** {_ex(i.evidence, facts, seen)}",
                f"**Why it matters:** {_ex(i.why_it_matters, facts, seen)}",
                f"**Portfolio relevance:** {_ex(i.portfolio_relevance, facts, seen)}"]
        if i.sources:
            out.append("**Sources:** " + ", ".join(i.sources))
        out.append("")
    out += ["## Challenge & coaching", _ex(brief.challenge, facts, set()), ""]
    out += ["## What I might be missing", _ex(brief.what_im_missing, facts, set()), ""]
    wl_seen = set()
    out += ["## Watchlist",
            ", ".join(_ex(w, facts, wl_seen) for w in brief.watchlist) or "—", ""]
    out += ["---", f"_{brief.disclaimer}_"]
    return "\n".join(out)
```

`render_html` takes the same treatment. Expansion happens **before** `escape()` — `p()` already escapes, so the order is preserved automatically:

```python
def render_html(brief, facts=None) -> str:
    def p(s): return f"<p>{escape(str(s))}</p>"
    parts = ['<!DOCTYPE html>',
             '<html><head><meta charset="utf-8"></head><body>',
             f"<h1>Blind-Spot Radar — Weekly Brief ({escape(brief.as_of)})</h1>",
             "<h2>Executive summary</h2>",
             p(_ex(brief.executive_summary, facts, set())),
             "<h2>Notable items</h2>"]
    for i in brief.items:
        seen = set()
        parts.append(f"<h3>{escape(i.title)}</h3>")
        parts.append(p(f"Thesis: {_ex(i.thesis, facts, seen)}"))
        parts.append(p(f"Evidence: {_ex(i.evidence, facts, seen)}"))
        parts.append(p(f"Why it matters: {_ex(i.why_it_matters, facts, seen)}"))
        parts.append(p(f"Portfolio relevance: {_ex(i.portfolio_relevance, facts, seen)}"))
        if i.sources:
            links = " ".join(_safe_link(s) for s in i.sources)
            parts.append(f"<p>Sources: {links}</p>")
    wl_seen = set()
    parts += ["<h2>Challenge &amp; coaching</h2>", p(_ex(brief.challenge, facts, set())),
              "<h2>What I might be missing</h2>", p(_ex(brief.what_im_missing, facts, set())),
              "<h2>Watchlist</h2>",
              p(", ".join(_ex(w, facts, wl_seen) for w in brief.watchlist) or "—"),
              "<hr>", f"<p><em>{escape(brief.disclaimer)}</em></p>",
              "</body></html>"]
    return "\n".join(parts)
```

Thread `facts` through the savers (`save_brief_json` stays as-is):

```python
def save_markdown(brief, reports_dir, facts=None) -> Path:
    path = Path(reports_dir) / f"brief-{brief.as_of}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(brief, facts), encoding="utf-8")
    return path

def save_html(brief, reports_dir, facts=None) -> Path:
    path = Path(reports_dir) / f"brief-{brief.as_of}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(brief, facts), encoding="utf-8")
    return path

def save_report(brief, reports_dir, facts=None) -> Path:
    """Write the brief as Markdown, HTML, and JSON. Return the Markdown path.

    Markdown and HTML get inline ticker expansion; the JSON stays raw so the
    web layer can apply its own (tooltip) treatment.
    """
    md_path = save_markdown(brief, reports_dir, facts)
    save_html(brief, reports_dir, facts)
    save_brief_json(brief, reports_dir)
    return md_path
```

In `run_weekly.py`, build the facts map after the portfolio loads and pass it to both render sites:

```python
from vantage.tickers import load_facts
...
    facts = load_facts(s.cache_dir, portfolio)
    path = save_report(brief, s.reports_dir, facts=facts)  # writes .md, .html, .json
    html = render_html(brief, facts=facts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_report.py tests/test_run_weekly.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vantage/report.py run_weekly.py tests/test_report.py
git commit -m "feat(report): expand ticker names on first mention in md/html briefs"
```

---

### Task 6: Web API — names on rows, `/api/tickers` for prose

**Files:**
- Modify: `vantage/web/artifacts.py:28-60` (`build_overview`)
- Modify: `vantage/web/app.py` (new route)
- Test: `tests/test_web_artifacts.py`, `tests/test_web_api.py`

**Interfaces:**
- Consumes: `load_facts`, `resolve`, `is_common_word`, `TICKER_RE` from Tasks 1-2.
- Produces:
  - `artifacts.relevant_ticker_facts(facts, signal_set, portfolio, brief) -> dict[str, dict]` where each value is `{"name", "sector", "common_word"}`
  - `GET /api/tickers` returning that dict
  - `build_overview` entries in `top_leaders` / `top_volume_spikes` gain a `"name"` key

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web_artifacts.py`:

```python
def test_build_overview_includes_names():
    from vantage.models import SignalSet, Signal
    from vantage.web.artifacts import build_overview
    ss = SignalSet("2026-08-12",
                   [Signal("MU", "ret_12m_leader", 6.3, 1, "Technology",
                           "Micron Technology")], {})
    o = build_overview(ss, None, None)
    assert o["top_leaders"][0]["name"] == "Micron Technology"
    assert o["top_leaders"][0]["sector"] == "Technology"

def test_relevant_ticker_facts_scopes_and_flags():
    from vantage.models import SignalSet, Signal, Brief, PortfolioContext, Holding
    from vantage.tickers import TickerFacts
    from vantage.web.artifacts import relevant_ticker_facts
    facts = {"MU": TickerFacts("MU", "Micron Technology", "Technology"),
             "ALL": TickerFacts("ALL", "Allstate Corp", "Financial Services"),
             "SMH": TickerFacts("SMH", "VanEck Semiconductor ETF", "Technology"),
             "ZZZZ": TickerFacts("ZZZZ", "Never Mentioned Inc", "Utilities")}
    ss = SignalSet("2026-08-12", [Signal("MU", "ret_12m_leader", 6.3, 1)], {})
    pf = PortfolioContext(available=True,
                          holdings=[Holding("SMH", "VanEck Semiconductor ETF", 1, 1)])
    b = Brief("2026-08-12", "ALL of the moves", [], [], "", "", "d")
    out = relevant_ticker_facts(facts, ss, pf, b)
    assert set(out) == {"MU", "SMH", "ALL"}          # ZZZZ never appears anywhere
    assert out["MU"]["name"] == "Micron Technology"
    assert out["ALL"]["common_word"] is True          # JS applies the cue rule
    assert out["MU"]["common_word"] is False
```

Append to `tests/test_web_api.py`:

```python
def test_tickers_endpoint(tmp_path):
    s = _settings(tmp_path); _seed(s)
    (s.cache_dir / "sectors.json").write_text(json.dumps(
        {"NVDA": {"sector": "Technology", "name": "NVIDIA Corporation",
                  "fetched": "2026-08-11"},
         "MU": {"sector": "Technology", "name": "Micron Technology",
                "fetched": "2026-08-11"}}))
    r = _client(s).get("/api/tickers")
    assert r.status_code == 200
    body = r.json()
    assert body["NVDA"]["name"] == "NVIDIA Corporation"   # in signals + holdings
    assert body["MU"]["sector"] == "Technology"           # in the brief watchlist
    assert body["MU"]["common_word"] is False

def test_tickers_endpoint_empty_when_no_artifacts(tmp_path):
    s = _settings(tmp_path)
    assert _client(s, available=False).get("/api/tickers").json() == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web_artifacts.py tests/test_web_api.py -q`
Expected: FAIL — `ImportError: cannot import name 'relevant_ticker_facts'` and 404 on `/api/tickers`

- [ ] **Step 3: Write the implementation**

In `vantage/web/artifacts.py`, add the import and the new function, and add `"name"` to the overview entry:

```python
from vantage.tickers import TICKER_RE, is_common_word, resolve
```

```python
            entry = {"ticker": s.ticker, "value": s.value, "sector": s.sector,
                     "name": s.name}
```

```python
def _brief_text(brief) -> str:
    """All prose in a brief, concatenated — used to scope the ticker map."""
    parts = [brief.executive_summary or "", brief.challenge or "",
             brief.what_im_missing or "", " ".join(brief.watchlist or [])]
    for i in brief.items:
        parts += [i.title or "", i.thesis or "", i.evidence or "",
                  i.why_it_matters or "", i.portfolio_relevance or ""]
    return " ".join(parts)


def relevant_ticker_facts(facts, signal_set, portfolio, brief) -> dict:
    """Facts for tickers actually on screen — not the whole 900+ universe.

    Narrow scope is the primary defense against annotating English words that
    happen to be tickers: a symbol the user is not looking at is never a
    candidate. The `common_word` flag carries the stoplist verdict to the
    frontend so the JS applies the same rule instead of keeping its own list.
    """
    keys = set()
    if signal_set:
        keys |= {s.ticker for s in signal_set.signals}
    if portfolio is not None and getattr(portfolio, "available", False):
        keys |= {h.ticker for h in portfolio.holdings if h.ticker}
    if brief is not None:
        keys |= {m.group(0) for m in TICKER_RE.finditer(_brief_text(brief))
                 if m.group(0) in facts}
    out = {}
    for t in sorted(keys):
        f = resolve(t, facts)
        out[t] = {"name": f.name, "sector": f.sector,
                  "common_word": is_common_word(t)}
    return out
```

In `vantage/web/app.py`, add the route after `/api/briefs/{as_of}`:

```python
    @app.get("/api/tickers")
    def tickers():
        from vantage.tickers import load_facts
        s = app.state.settings
        pf = app.state.portfolio_loader(s.portfolio_analysis_path)
        ss = art.latest_signals(s.data_dir)
        briefs = art.list_briefs(s.reports_dir)
        latest = art.load_brief(s.reports_dir, briefs[0]["as_of"]) if briefs else None
        return art.relevant_ticker_facts(load_facts(s.cache_dir, pf), ss, pf, latest)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_web_artifacts.py tests/test_web_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vantage/web/artifacts.py vantage/web/app.py tests/test_web_artifacts.py \
        tests/test_web_api.py
git commit -m "feat(web): serve ticker names on rows and a scoped /api/tickers map"
```

---

### Task 7: Dashboard structured rows

Renders the `name · sector` subtitle beneath the ticker in the Overview, Signals, and Portfolio panels. No JS test harness exists in this project, so verification is a browser check.

**Files:**
- Modify: `vantage/web/static/app.js:13-49` (`loadOverview`, `loadPortfolio`, `loadSignals`)
- Modify: `vantage/web/static/styles.css` (append)

**Interfaces:**
- Consumes: `/api/overview` (now with `name`), `/api/signals` (now with `name`), `/api/portfolio` (already has `name`, `sector`).
- Produces: JS helpers `sub(name, sector) -> string` and `cell(main, name, sector) -> string`, used by all three panels.

- [ ] **Step 1: Add the row helpers**

In `vantage/web/static/app.js`, after the `rows` helper (line 9-11), add:

```js
// Ticker stays the anchor; identity sits beneath it in muted type.
function sub(name, sector) {
  const t = [name, sector].filter(Boolean).join(" · ");
  return t ? `<div class="sub">${esc(t)}</div>` : "";
}

function cell(main, name, sector) {
  return `<div class="cell"><span>${main}</span>${sub(name, sector)}</div>`;
}
```

- [ ] **Step 2: Use them in the three panels**

Overview leaders and sector momentum (sector rows have no subtitle):

```js
    ${rows(o.top_leaders, (l) => `<div class="row">
      ${cell(esc(l.ticker), l.name, l.sector)}
      <span class="${cls(l.value)}">${pct(l.value)}</span></div>`)}
```

Signals:

```js
    ${rows(s.signals, (sig) => `<div class="row">
      ${cell(esc(sig.ticker) + " · " + esc(sig.signal_type), sig.name, sig.sector)}
      <span class="${cls(sig.value)}">${sig.signal_type === "volume_spike"
        ? sig.value.toFixed(1) + "×" : pct(sig.value)}</span></div>`)}
```

Portfolio (replacing the inline `ticker — name` form):

```js
      (h) => `<div class="row">
        ${cell(esc(h.ticker), h.name, h.sector)}
        <span>${pct(h.pct_of_portfolio)}</span></div>`)}
```

- [ ] **Step 3: Add the CSS**

Append to `vantage/web/static/styles.css`:

```css
/* --- Ticker identity ------------------------------------------------- */
/* Two-line row cell: symbol on top as the scannable anchor, company and
   sector beneath. Keeps long names from crowding the value column. */
.row .cell { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.sub { font-size: 12.5px; color: var(--muted); line-height: 1.35;
       overflow-wrap: anywhere; }
```

- [ ] **Step 4: Verify in the browser**

Start the server if it is not already running: `.venv/bin/python -m vantage.web`

Open `http://127.0.0.1:8000` and confirm:
- Overview "Top 12-month leaders" rows show e.g. `MU` with `Micron Technology · Technology` beneath.
- Signals rows show the same beneath `TICKER · signal_type`.
- Portfolio rows show name and sector beneath the ticker.
- A ticker with no cached name shows the ticker alone with no stray `·` separator.

- [ ] **Step 5: Commit**

```bash
git add vantage/web/static/app.js vantage/web/static/styles.css
git commit -m "feat(web): name and sector subtitle under every ticker row"
```

---

### Task 8: Dashboard prose annotation

Dotted-underline tooltips on tickers inside brief prose, watchlist lines, and chat replies. Built with DOM nodes rather than `innerHTML` — this is the constraint that keeps commit `5107bda`'s escaping fix intact.

**Files:**
- Modify: `vantage/web/static/app.js` (facts loading, `annotate`, `openBrief`, chat handler, `loadOverview` lede)
- Modify: `vantage/web/static/styles.css` (append)

**Interfaces:**
- Consumes: `GET /api/tickers` from Task 6, `cell`/`sub` from Task 7.
- Produces: JS `annotate(text) -> DocumentFragment`, module-level `FACTS` object, `loadFacts()` called from `loadData()`.

- [ ] **Step 1: Load the facts map**

In `vantage/web/static/app.js`, add near the top (after the `esc` helper):

```js
// Ticker facts for prose annotation, scoped server-side to what's on screen.
let FACTS = {};
async function loadFacts() {
  try { FACTS = await getJSON("/api/tickers"); } catch (e) { FACTS = {}; }
}
```

And make `loadData` await it first, so panels render with facts available:

```js
async function loadData() {
  await loadFacts();
  loadOverview(); loadPortfolio(); loadSignals(); loadBriefs();
}
```

- [ ] **Step 2: Add the annotator**

```js
// Mirrors vantage/tickers.py: same symbol shape, same price-cue rule. The
// stoplist verdict arrives per-ticker as `common_word` so there is only one
// list, maintained in Python.
const TK_RE = /\b[A-Z][A-Z0-9]{0,4}(?:-[A-Z])?\b/g;
const CUE_RE = /^\s*(?:is\s+|at\s+)?[+\-]?\$?\d/;

function annotate(text) {
  const s = String(text == null ? "" : text);
  const frag = document.createDocumentFragment();
  let last = 0, m;
  TK_RE.lastIndex = 0;
  while ((m = TK_RE.exec(s)) !== null) {
    const f = FACTS[m[0]];
    if (!f) continue;
    const end = m.index + m[0].length;
    if (f.common_word && !CUE_RE.test(s.slice(end, end + 12))) continue;
    const tip = [f.name, f.sector].filter(Boolean).join(" · ");
    if (!tip) continue;
    frag.appendChild(document.createTextNode(s.slice(last, m.index)));
    const span = document.createElement("span");
    span.className = "tk";
    span.textContent = m[0];          // text node, never innerHTML
    span.setAttribute("data-tip", tip);
    span.setAttribute("tabindex", "0");
    frag.appendChild(span);
    last = end;
  }
  frag.appendChild(document.createTextNode(s.slice(last)));
  return frag;
}

// A <p> whose text is annotated. Used wherever prose is rendered.
function proseP(className, text) {
  const p = document.createElement("p");
  p.className = className;
  p.appendChild(annotate(text));
  return p;
}
```

- [ ] **Step 3: Rewrite `openBrief` to build prose via DOM**

Replace the body of `openBrief` after the `const b = data.brief;` guard. The static chrome may stay `innerHTML`; every piece of brief text goes through `annotate`.

```js
  const panel = $("brief-detail");
  panel.style.display = "block";
  panel.innerHTML = `<div class="brief-head"><h2>Brief — ${esc(b.as_of)}</h2>
      <button id="brief-close">Close</button></div><div class="brief-body"></div>`;
  const body = panel.querySelector(".brief-body");

  const label = (t) => {
    const d = document.createElement("div");
    d.className = "label";
    d.textContent = t;
    return d;
  };
  const field = (k, v) => {
    const p = document.createElement("p");
    p.className = "brief-field";
    const key = document.createElement("span");
    key.className = "field-k";
    key.textContent = k;
    p.append(key, annotate(v));
    return p;
  };

  body.append(label("Executive summary"), proseP("prose lede", b.executive_summary));
  for (const i of b.items || []) {
    const div = document.createElement("div");
    div.className = "brief-item";
    const h3 = document.createElement("h3");
    h3.className = "brief-item-title";
    h3.appendChild(annotate(i.title));
    div.append(h3, field("Thesis", i.thesis), field("Evidence", i.evidence),
               field("Why it matters", i.why_it_matters),
               field("Portfolio relevance", i.portfolio_relevance));
    if (i.sources && i.sources.length) {
      const src = document.createElement("p");
      src.className = "brief-sources";
      src.textContent = "Sources: " + i.sources.join(", ");
      div.appendChild(src);
    }
    body.appendChild(div);
  }
  body.append(label("Challenge & coaching"), proseP("prose", b.challenge),
              label("What I might be missing"), proseP("prose", b.what_im_missing),
              label("Watchlist"));
  for (const w of b.watchlist || []) body.appendChild(proseP("prose wl", w));
  if (!(b.watchlist || []).length) body.appendChild(proseP("prose", "—"));

  $("brief-close").addEventListener("click", () => { panel.style.display = "none"; });
  panel.scrollIntoView({ behavior: "smooth" });
```

- [ ] **Step 4: Annotate the overview lede and chat replies**

In `loadOverview`, after setting `innerHTML`, replace the lede's contents:

```js
  const lede = $("overview").querySelector(".prose.lede");
  if (lede) lede.replaceChildren(annotate(lede.textContent));
```

In the chat submit handler, annotate each analyst bubble once its stream finishes (partial tokens would match unpredictably mid-stream). After the `await streamPost(...)` call completes, inside the `try`:

```js
    if (bubble) bubble.replaceChildren(annotate(bubble.textContent));
```

- [ ] **Step 5: Add the tooltip CSS**

Append to `vantage/web/static/styles.css`:

```css
/* Ticker in prose: dotted underline, identity on hover or keyboard focus.
   CSS-only — no positioning library, no JS. */
.tk { border-bottom: 1px dotted var(--muted); cursor: help; position: relative;
      outline: none; }
.tk::after { content: attr(data-tip); position: absolute; left: 0; bottom: 130%;
  white-space: nowrap; background: var(--panel); color: var(--ink);
  border: 1px solid var(--line); border-radius: 6px; padding: 5px 9px;
  font-size: 12.5px; font-style: normal; box-shadow: 0 4px 14px rgba(0,0,0,.35);
  opacity: 0; pointer-events: none; transition: opacity .12s ease; z-index: 30; }
.tk:hover::after, .tk:focus::after { opacity: 1; }
.tk:focus { border-bottom-style: solid; }
.prose.wl { margin-bottom: .5rem; }
```

- [ ] **Step 6: Verify in the browser**

Reload `http://127.0.0.1:8000` and confirm:
- Clicking the 2026-08-11 brief opens the detail; `MU`, `WDC`, `LITE`, `PBF` carry dotted underlines and show `Name · Sector` on hover.
- Tab key reaches an annotated ticker and shows the same tooltip.
- Watchlist lines render one per line with their leading tickers annotated.
- Ask the chat something like "what do you make of MU?" and confirm the reply's tickers are annotated once the response finishes.
- Read a full brief item and confirm **no** ordinary English word is underlined. If one is, add it to `COMMON_WORD_TICKERS` in `vantage/tickers.py` and reload.

- [ ] **Step 7: Commit**

```bash
git add vantage/web/static/app.js vantage/web/static/styles.css
git commit -m "feat(web): ticker tooltips in brief prose, watchlist, and chat"
```

---

### Task 9: Backfill run, README, and end-to-end verification

**Files:**
- Modify: `README.md`
- Run: `tools/backfill_ticker_names.py`

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/pytest -q`
Expected: PASS — 67 original tests plus roughly 35 new ones, no failures.

- [ ] **Step 2: Run the backfill**

Run in the background; it makes ~915 `.info` calls and takes roughly 5-15 minutes:

```bash
.venv/bin/python tools/backfill_ticker_names.py
```

Expected: progress lines every 25 tickers, ending with `Done: {'filled': ~915, 'skipped': 0, 'failed': N}`. A handful of failures is acceptable (delisted symbols such as JLL and NXT); those tickers keep their sector and show no name.

- [ ] **Step 3: Spot-check the cache**

Run:

```bash
.venv/bin/python -c "
import json; c = json.load(open('cache/sectors.json'))
named = [t for t, e in c.items() if e.get('name')]
print(len(named), 'of', len(c), 'have names')
print({t: c[t] for t in list(named)[:3]})"
```

Expected: the large majority have names.

- [ ] **Step 4: Regenerate a brief and check the email rendering**

Run: `.venv/bin/python run_weekly.py --no-email`

Then confirm the expansion landed in the artifacts but not the JSON:

```bash
grep -c "Micron Technology" reports/brief-*.md reports/brief-*.html
grep -c "Micron Technology" reports/brief-*.json || echo "json clean (expected)"
```

Expected: non-zero counts for `.md` and `.html`; the JSON check finds nothing in the newest file.

- [ ] **Step 5: Update the README**

In the "Web dashboard" section, note that every ticker shows its company name and sector, and that tickers inside brief and chat prose carry hover tooltips. Add `tools/backfill_ticker_names.py` to the tooling notes alongside `tools/build_universe.py`, describing it as a one-time pass to fill names into `cache/sectors.json`. In the weekly-brief section, note that the emailed brief expands each ticker's name on first mention per section.

- [ ] **Step 6: Commit**

```bash
git add README.md cache/sectors.json
git commit -m "docs: document ticker identity; backfill company names"
```

Note: check whether `cache/` is git-ignored before staging it — `.gitignore` may already exclude it, in which case only commit `README.md`.

---

## Self-Review Notes

Spec coverage check against `docs/superpowers/specs/2026-08-12-ticker-identity-design.md`:

- §2.1 resolver → Task 1
- §2.2 data_ingest info capture, `Signal.name`, cache self-healing → Task 3
- §2.3 backfill tool → Task 4
- §2.4 `build_overview` names, `/api/tickers` with `common_word` → Task 6
- §2.5 frontend rows and prose → Tasks 7, 8
- §2.6 report/email inline expansion, JSON stays raw, no `Brief` mutation → Task 5
- §3 relevant-set scoping + stoplist + single-sourced rule → Tasks 2, 6, 8
- §5 error handling (info failure, corrupt cache, empty `/api/tickers`, `resolve` never raises) → Tasks 1, 3, 4, 6
- §6 testing → each task's test steps; frontend manual verification in Tasks 7, 8
