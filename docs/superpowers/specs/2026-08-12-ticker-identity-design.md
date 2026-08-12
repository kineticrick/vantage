# Ticker Identity (Name + Sector) — Design

**Date:** 2026-08-12
**Status:** Design — pending user review
**Project root:** `/home/kineticrick/code/python/vantage`

## 1. Purpose

Every asset reference in the web dashboard is a bare ticker symbol. `MU` and
`LITE` and `ONTO` mean nothing at a glance unless you already hold them, which
undercuts the point of a radar: it surfaces things you *don't* know. Show the
company name and sector next to every ticker, everywhere a ticker appears.

### Success criteria
- Every structured row in the dashboard (Overview leaders, Signals, Portfolio
  positions) shows the company name and sector alongside the ticker.
- Tickers embedded in prose (brief items, watchlist lines, chat replies) are
  identifiable without leaving the page.
- No wrong annotations. A ticker that goes un-annotated is invisible to the
  user; a common English word annotated as a company is a visible bug. The
  design is deliberately conservative about prose.
- Existing artifacts (`data/signals-*.json`, `reports/brief-*.json`) written
  before this change still load.

### Motivating observation
Sector is **already** carried on every `Signal` and `Holding` and simply is not
rendered — that half is a display fix. Company name is stored nowhere, even
though `data_ingest._default_sector_fn` already calls `yf.Ticker(t).info` (which
returns `longName`) and discards everything but the sector. The name is being
fetched and thrown away 915 times per run.

## 2. Architecture

Five units. Each is independently understandable and testable.

### 2.1 `vantage/tickers.py` (new) — the resolver

The single answer to "what is this ticker?". Everything else asks this unit and
does not care where the answer came from.

```python
@dataclass
class TickerFacts:
    ticker: str
    name: str | None = None
    sector: str | None = None
```

- `load_facts(cache_dir, portfolio=None) -> dict[str, TickerFacts]`
- `resolve(ticker, facts) -> TickerFacts` — never raises; falls back to
  `TickerFacts(ticker=ticker)` so callers can always render something.

**Source layering**, highest priority first:
1. **Wake portfolio holdings** — authoritative for what the user owns, and the
   only source that names the ETFs (SMH, VGT, QQQ, MGK, VOO, IVW). `Holding`
   already carries `name`, `sector`, `asset_type`.
2. **Ticker-facts cache** (`cache/sectors.json`) — the yfinance-derived facts.
3. **Bare ticker** — name and sector `None`.

### 2.2 `vantage/data_ingest.py` — capture what is already fetched

- `_default_sector_fn(ticker) -> str` becomes
  `_default_info_fn(ticker) -> dict` returning `{"sector", "name"}` from the
  same single `.info` call. Name is `longName` → `shortName` → ticker.
- `_sector_for` becomes `_facts_for`. Staleness gains a second condition: an
  entry **missing the `name` key is treated as stale** regardless of age, so
  the cache self-heals on any subsequent fetch without a migration step.
- `cache/sectors.json` keeps its filename (915 entries stay valid); entries
  grow from `{"sector", "fetched"}` to `{"sector", "name", "fetched"}`.
- `MarketData` gains `names: dict`.
- `Signal` gains `name: str | None = None`, populated by the screener. This
  makes `signals-*.json` self-describing — the web layer renders name and
  sector straight from the artifact with no lookup — and the default keeps
  `Signal(**s)` working on signal files written before this change.

### 2.3 `tools/backfill_ticker_names.py` (new)

One-time pass to fill `name` for the ~915 already-cached tickers, whose sector
entries are fresh until roughly 2026-09-10 and so would not otherwise re-fetch.

- Writes the cache incrementally (resumable; safe to interrupt).
- Logs progress per batch.
- Tooling only — the weekly pipeline never needs it.

Cost: one `.info` call per ticker, roughly 5–15 minutes. Run in the background.

### 2.4 Web API (`vantage/web/`)

- `artifacts.build_overview` propagates `name` into `top_leaders`,
  `top_volume_spikes`, and `top_positions` (which already has it).
- `/api/signals` needs no change — it serializes `Signal`, which now carries
  `name` and already carried `sector`.
- `/api/portfolio` needs no change — `Holding` already carries both.
- **New `/api/tickers`** returns `{TICKER: {"name", "sector"}}` for the
  *relevant set* only: tickers in the latest signal set, plus portfolio
  holdings, plus any cache-known ticker whose symbol appears in the latest
  brief's text (executive summary, item fields, challenge, what-I'm-missing,
  watchlist). The candidate pool for that last scan is the cache's own keys —
  the server holds all ~915 known symbols, and only the subset that actually
  occurs in the brief is returned. Roughly 50–100 entries, not the full 923.
  The frontend fetches this once on load and uses it for prose annotation.

### 2.5 Frontend (`vantage/web/static/`)

**Structured rows.** A shared helper renders the ticker as the bold anchor with
`name · sector` beneath it in smaller muted type:

```
MU  · ret_12m_leader              +632%
Micron Technology · Technology
```

Chosen over a single inline line (long names crowd the value column and force
ellipsis in the narrow left panel) and over sector chips (more visual weight
than the information deserves). Missing name or sector degrades to whichever
part is known, with no empty separator left behind.

**Prose.** `annotate(text, facts) -> DocumentFragment` builds text nodes and
`<span class="tk" data-tip="…">` elements via DOM APIs — never `innerHTML`.
This preserves the escaping posture established in commits `5107bda` and
`dd94d10`. Consumers: brief item fields, watchlist lines, and chat bubbles
(annotated once the stream for that bubble completes, since partial tokens
would match unpredictably).

Tooltip is CSS-only on `:hover` / `:focus` against `data-tip`, with
`tabindex="0"` so it is reachable by keyboard and by tap on touch devices.

## 3. False positives in prose

The core risk. A naive `\b[A-Z]{1,5}\b` scan across 923 tickers would annotate
`IT`, `ALL`, `ON`, `KEY`, `NOW`, `CAT`, `SEE`, `HAS`, `BIG`, `RUN` wherever
they appear as ordinary English. Two defenses, applied together:

1. **Relevant-set scoping.** Only tickers in the `/api/tickers` map are
   candidates. A brief that never mentions Caterpillar never has `CAT` in
   scope, which removes most of the collision surface before any matching
   happens.
2. **Stoplist.** Common English words that are also tickers are skipped even
   when in scope, unless the adjacent text carries a price/percent cue (e.g.
   `ALL +32%`).

Deliberately biased toward under-annotating: a missed tooltip is invisible, a
wrong one is a visible bug. Approved by the user as conservative-by-design.

## 4. Data flow

```
yfinance .info ──┐
                 ├─> cache/sectors.json ──┐
Wake holdings ───┘   (name + sector)      ├─> vantage/tickers.py ──> /api/tickers ──> prose tooltips
                                          │
screener ──> Signal{name, sector} ──> data/signals-*.json ──> /api/signals ──> structured rows
```

## 5. Error handling

- `.info` failure for a ticker yields `{"sector": "Unknown", "name": None}` —
  the existing try/except posture, extended. One bad ticker never fails a run.
- A corrupt or unreadable `cache/sectors.json` is treated as empty (existing
  behavior in `_load_sector_cache`).
- `/api/tickers` with no artifacts present returns `{}`; the frontend renders
  bare tickers with no tooltips and no errors, matching how the panels already
  degrade to "None" / "Unavailable".
- `resolve()` never raises.

## 6. Testing

Python (pytest, alongside the existing 51 tests):
- Resolver: cache hit; age-stale entry; entry missing `name` treated as stale;
  portfolio layering overrides cache; unknown ticker returns bare fallback.
- `data_ingest`: injected `_info_fn` captures both name and sector; cache round
  trip preserves both; legacy name-less entries trigger re-fetch.
- `Signal` / `SignalSet`: a signal file written without `name` still loads.
- `build_overview`: name reaches leaders and spikes.
- `/api/tickers`: relevant-set scoping; empty-artifact case returns `{}`.

Frontend: no JS test harness exists in this project (all 51 tests are Python),
so row rendering, tooltip behavior, and the absence of false-positive
annotations in a real brief are verified manually in the browser.

## 7. Out of scope

- Annotating tickers in the emailed HTML brief (`vantage/report.py`) — email
  clients handle CSS tooltips inconsistently.
- Any change to how the analyst writes prose. This is a display layer only.
- Backfilling names into already-written `data/signals-*.json` artifacts; the
  web layer falls back to `/api/tickers` for older files.
