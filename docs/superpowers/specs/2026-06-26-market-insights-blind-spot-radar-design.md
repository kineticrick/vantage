# Market Insights — Blind-Spot Radar (v1 Design)

**Date:** 2026-06-26
**Status:** Design — pending user review
**Project root:** `/home/kineticrick/code/python/market_insights`

## 1. Purpose

A proactive, AI-driven research partner for stock-market decision-making. Each
week it scans the market broadly, fuses hard price/volume signals with
self-sourced news narratives, and emails a reasoned brief on emerging trends,
sectors, and assets the user should be aware of — so the next "Micron moment"
(the AI-hardware/memory boom the user missed) surfaces *before* it becomes
consensus. It also sends daily alerts when sharp, rule-based signals fire.

It is explicitly a **research and decision aid, not a trading bot and not
financial advice.** It surfaces, reasons, and explains; the user decides.

It is also a **sparring partner, not just an informer.** The user explicitly
wants their prior thinking and decisions challenged with new evidence so they
can grow as an investor — so the tool deliberately probes, debates, and
pressure-tests past decisions and patterns (this is the same motivation behind
the `hypotheticals` analysis in `portfolio_analysis`). Challenge is
evidence-based and constructive, never contrarian for its own sake.

### Motivating pain
The user stays on top of trends by reading news/opinion and applying their own
judgment, but missed the memory/hardware run-up (Micron, SanDisk, Western
Digital) driven by AI buildouts — both a reasoning blind spot and a failure to
capture external signals. The radar's job is to not let that happen again.

### Success criteria (v1)
- A weekly email brief that the user finds genuinely informative — surfaces at
  least some things they were not already tracking, with reasoning they can
  evaluate.
- Deterministic, reproducible quantitative screening (same inputs → same
  signals).
- The brief is grounded: claims carry evidence and cited sources; uncertainty
  is stated rather than papered over.
- The brief challenges the user's own decisions where the evidence warrants —
  not as a gimmick, but with specific, defensible reasoning the user can push
  back on.
- Easy to evolve: adding a signal, changing a threshold, or adjusting the
  analyst's instructions is a small, localized change.

## 2. Architecture

**Approach: hybrid.** Deterministic Python for data + screening (where
reproducibility is the point); a Claude API "analyst" layer for narrative
detection, convergence, and second-order reasoning (where judgment is the
point). The two communicate through a structured `Signal` schema, so the
analyst can later be driven interactively (a future conversational mode)
without touching the screener.

### Units (each independently understandable and testable)

```
config/                  interest profile overlay, universe list, thresholds, settings
  │
  ├─ data_ingest.py        pull prices/volume/sector data via yfinance (batched, disk-cached)
  │     │
  │     └─→ screener.py     compute deterministic signals → structured Signal set  ─┐
  │                                                                                  │ deterministic,
  ├─ portfolio_context.py   adapter over portfolio_analysis → PortfolioContext  ─────┤ unit-tested
  │                                                                                  │
  ▼                                                                                  ▼
analyst.py                 Claude API (claude-opus-4-8, adaptive thinking, web_search):
  │                        consumes Signal set + PortfolioContext + interest overlay,
  │                        produces a structured Brief (judgment layer)
  ▼
report.py                  render Brief → dated Markdown (archive) + HTML email
  ▼
deliver.py                 send via Gmail SMTP
  ▲
run_weekly.py / run_daily.py   entry points invoked by cron
```

**Determinism boundary:** `data_ingest`, `screener`, and `portfolio_context`
are pure/deterministic and unit-tested. `analyst` is the only non-deterministic
unit. Everything downstream of the analyst is mechanical rendering/sending.

### Data contracts (the seams that keep units decoupled)
- `Signal` — one detected quantitative signal: ticker, signal type, value,
  rank, supporting metrics (e.g. trailing returns, volume ratio), sector.
  A run produces a `SignalSet` (the ranked collection) persisted as dated JSON
  in `data/`.
- `PortfolioContext` — a clean snapshot derived from the user's real data:
  current holdings (ticker, shares, cost basis, % of portfolio), sector and
  asset-type concentration, and "revealed interests" (where capital has gone
  over time, from transaction history). This is *our* object, not a
  `portfolio_analysis` type — see §4.
- `Brief` — the analyst's structured output: executive summary; ranked notable
  items (each with thesis, evidence, cited sources, why-it-matters, and any
  portfolio relevance); watchlist suggestions; an explicit "what I might be
  missing" section; a **"challenge / coaching" section** that pressure-tests
  the user's current positioning and past decisions against the new evidence;
  disclaimer.

## 3. Quantitative layer (data_ingest + screener)

### Universe
S&P 500 + Nasdaq-100 + a curated mid-cap extension (~1,000–1,500 tickers),
defined in a config file so it can grow. Chosen to cover large- and mid-cap
names (where Western Digital / SanDisk-type movers live) while staying
manageable on free data. Index membership sourced from free public lists.

### Data source
`yfinance` (free). Prices/volume pulled in batches and cached to disk to
respect rate limits and make runs repeatable. (Note: `portfolio_analysis`
ships `yfinance_helpers`; v1 keeps the radar's market-data layer independent
to avoid over-coupling, but this is a candidate for later consolidation.)

### Signals (thresholds config-driven)
- Trailing returns over 1m / 3m / 6m / 12m → "up >100% / 12mo" leaders.
- Volume spikes vs. trailing average.
- Sector momentum — which sectors are quietly outperforming.
- New entrants to leader lists (drives daily alerts: "X newly crossed +100%").

Output: a ranked `SignalSet` written to dated JSON. This is the deterministic
substrate the analyst reasons over, and the standalone input to daily alerts.

## 4. Portfolio integration (portfolio_context)

**Decision: import `portfolio_analysis` as a library, behind an
anti-corruption adapter.**

`~/code/python/portfolio_analysis` exposes a high-level query API returning
pandas DataFrames — notably `get_portfolio_summary()` (current holdings + cost
basis), `get_portfolio_current_value()` (holdings + live prices + % of
portfolio + lifetime return), `build_master_log()` (full transaction history,
correctly handling splits and acquisitions), `add_asset_info()` (sector / asset
type / geography), and `gen_aggregated_historical_value()` (sector / asset-type
aggregates). Reusing these avoids re-deriving non-trivial logic (especially
splits/acquisitions) and keeps one source of truth.

**Coupling containment:** all `portfolio_analysis` access is confined to
`portfolio_context.py`. It imports via `sys.path.append('.../portfolio_analysis')`,
calls the high-level helpers, and returns *our* `PortfolioContext` object. No
other unit imports `portfolio_analysis`. If the upstream API changes, only this
file changes.

**Resilience:** if the DB is unreachable or the import fails, `portfolio_context`
returns `None`/empty and the radar runs in market-wide-only mode (logging a
warning, noting it in the brief). Portfolio data enriches the brief; it is not
required for it to run.

**Known integration facts (from code exploration):**
- DB: MySQL database `portfolio`, credentials hardcoded in
  `portfolio_analysis/libraries/db/{dbcfg.py,pwd.py}`. We rely on the library's
  own config; we do not duplicate credentials.
- No `setup.py`/`pyproject.toml` — import is by path.
- Global connection-pool singleton + project-local disk cache; fine for our
  sequential, single-process scheduled runs.

## 5. The analyst brain (analyst.py)

A Claude API call — the differentiating unit.

- **Model:** `claude-opus-4-8` (current default; ~$5/$25 per 1M tokens — at
  weekly + daily cadence, a few dollars/month).
- **Thinking:** adaptive (`thinking: {type: "adaptive"}`), effort `high`.
- **Tooling:** the built-in `web_search` server tool (type
  `web_search_20260209`) so the analyst sources its own news/narratives
  server-side. Streaming used (large output).
- **API key:** from env (`.env`, never committed).

**Inputs:** the `SignalSet`, the `PortfolioContext`, and a small hand-written
interest overlay (themes the user cares about but may not hold yet).

**Tasks (prompted):**
1. **Emerging narratives** — search news for themes around the top movers and
   momentum sectors; flag ones rising in frequency before they're mainstream.
2. **Narrative ↔ price convergence** — where a rising narrative AND unusual
   price action point at the same sector/asset (the exact memory-stock
   pattern). Highest-signal output.
3. **Second-order / supply-chain reasoning** — "if X is booming, who are the
   non-obvious upstream/downstream beneficiaries?" — to surface SanDisk-type
   names before consensus.
4. **Personal layer (lens, not filter)** — using `PortfolioContext`: flag
   trends that threaten a concentration, connect movers to held names, and spot
   adjacents to themes the user has repeatedly bought. The market-wide scan
   stays primary; the portfolio adds a layer on top, it does not narrow the
   search.
5. **Challenge & coach** — deliberately pressure-test the user's positioning
   and past decisions against the new evidence: over-concentration, a thesis
   that the evidence now undercuts, a rotation the user appears to have missed,
   a recurring behavioral pattern in the transaction history (e.g. selling
   winners early, chasing a theme late). Play evidence-based devil's advocate,
   state the counter-case the user should have to answer, and frame it as
   coaching — specific and defensible, not contrarian for its own sake. This
   draws on `PortfolioContext` (holdings + transaction history) and, where
   useful, the `hypotheticals` analysis in `portfolio_analysis` (validate
   availability during implementation — see §13).

**Output:** a structured `Brief` (see §2). The analyst is instructed to show
evidence, cite sources, surface uncertainty rather than fabricate confidence,
and keep challenge constructive and grounded.

## 6. Reports & delivery (report.py + deliver.py)

- `report.py` renders the `Brief` to dated Markdown (archived in `reports/`)
  and a clean HTML email.
- `deliver.py` sends via Gmail SMTP using an app password from `.env`. Two
  email types: the weekly digest and the shorter daily alert.

## 7. Scheduling

v1 uses system `cron` with two entry points, documented in the README:
- **Weekly** (e.g. Sunday morning): `run_weekly.py` → full pipeline
  (data → screener → portfolio_context → analyst → report → digest email).
- **Daily:** `run_daily.py` → data + screener only; if alert rules fire (e.g.
  a new entrant to the >100%/12mo list, a large volume spike), send a short
  alert email. No LLM cost on daily runs.

## 8. Configuration

A `config/` directory holding: the ticker universe list, signal thresholds,
the interest-overlay file, email settings (recipient, cadence), and references
to secrets in `.env`. Secrets (`ANTHROPIC_API_KEY`, Gmail app password) live in
`.env`, which is git-ignored; a `.env.example` documents the required keys.

## 9. Guardrails

- Every brief and alert carries a plain disclaimer: research aid, not financial
  advice; verify before acting.
- The analyst is instructed toward evidence, citations, and stated uncertainty.
- Challenge is constructive and evidence-grounded: it states a defensible
  counter-case the user can argue with, not contrarianism or false certainty.
- The radar degrades gracefully: missing portfolio data → market-wide-only
  mode; data-source hiccups are logged, not silently swallowed.

## 10. Out of scope for v1 (YAGNI)

Deferred, and clean to add later because of the unit boundaries:
- Portfolio P&L tracking / performance attribution (lives in
  `portfolio_analysis` already).
- Brokerage / trade execution integration.
- Backtesting of signals.
- A web UI / dashboard.
- The interactive conversational analyst mode (the analyst unit is designed so
  it can later be driven interactively).
- Paid market-data or news feeds (start free; upgrade if it proves out).

## 11. First build slice

**Weekly digest, end-to-end:** `data_ingest` → `screener` →
`portfolio_context` → `analyst` → `report` → `deliver`, plus the weekly cron
entry point and a project `README`.

**Fast-follow:** daily alerts (`run_daily.py`), which reuse `data_ingest` +
`screener` with no new LLM cost.

## 12. Deliverables / conventions

- A project `README.md` covering setup (`.env`, dependencies, the
  `portfolio_analysis` path dependency), how to run each entry point, and how
  to install the cron jobs. Kept current as the code evolves.
- Unit tests for the deterministic units (`data_ingest`, `screener`,
  `portfolio_context` adapter logic).

## 13. Open risks / things to validate during implementation

- **Free-data rate limits** at ~1,000–1,500 tickers: batching + disk caching
  should handle it; validate run time and back off batch size if needed.
- **`portfolio_analysis` import side effects** (global pool, project-local
  cache): confirm a clean import from an external process; the adapter isolates
  any fallout.
- **Analyst output quality and token cost:** validate the brief is useful and
  costs land in the expected few-dollars/month range on a real run; tune the
  prompt and effort if not.
- **Universe membership source:** pick a reliable free source for index
  constituents and pin/refresh it sensibly.
- **`hypotheticals` availability and shape:** the design assumes the
  `hypotheticals` analysis in `portfolio_analysis` can feed the "challenge &
  coach" element. Confirm what it exposes (functions / data) and how cleanly it
  maps into `PortfolioContext` during implementation; if integration is awkward
  in v1, the challenge element can rely on holdings + transaction history alone
  and add `hypotheticals` later.
