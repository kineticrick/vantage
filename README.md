# Vantage

*See where the market's headed.*

An AI-driven research **partner** for stock-market decision-making. It scans the
market for things you might be missing, fuses hard price/volume signals with
self-sourced news, grounds everything in your *real* portfolio, and — crucially
— **challenges your reasoning** rather than just informing you. Two ways to use
it: a proactive **weekly brief**, and an interactive **conversational analyst**.

> Research aid — **not financial advice.** Every output carries a disclaimer;
> verify independently before acting.

## What it does

- **Weekly blind-spot brief** — screens a ~915-ticker universe (S&P 500 +
  Nasdaq-100 + S&P 400 mid-caps) for 12-month return leaders, volume spikes, and
  sector momentum; an LLM analyst (Claude `claude-opus-4-8` with web search)
  fuses those signals with sourced news to flag emerging narratives,
  narrative↔price convergence, non-obvious second-order beneficiaries, and how
  it all relates to what you hold — then emails you a reasoned, deliberately
  challenging brief.
- **Conversational analyst** — an interactive chat you can argue with about your
  portfolio and the market, with the same challenge-and-coach voice. It can pull
  exact ticker metrics, re-run the screen, and web-search for news on demand, so
  its numbers are real, not guessed.
- **Grounded in your real holdings** — both modes load your live portfolio and
  full transaction history from the **Wake** project (read-only).
- **Challenge-first** — it pressure-tests over-concentration, stale theses,
  missed rotations, and recurring behavioral patterns in your trading history.

## Setup

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `cp .env.example .env` and fill in:
   - `ANTHROPIC_API_KEY` — required for the analyst (both modes).
   - `GMAIL_USER`, `GMAIL_APP_PASSWORD` (a Gmail **App Password**, not your
     login), `EMAIL_RECIPIENT` — only needed to *email* the weekly brief.
4. Make sure the **Wake** codebase is at
   `~/code/python/wake` (or set
   `WAKE_PATH`), and its MySQL DB is reachable. If it isn't, both
   modes still run in **market-wide-only mode** (noted in the output).
5. (Optional) Tune `config/universe.txt` and `config/interests.yaml` — see
   [Configuration](#configuration).

## Usage

### Weekly brief

```bash
python run_weekly.py            # full pipeline, emails the brief
python run_weekly.py --no-email # full real pipeline, writes to reports/ but skips email
```

Each run writes the brief to `reports/brief-<date>.md`, `.html`, and `.json`
(the structured brief, so any report can be re-rendered later), and the
screener output to `data/signals-<date>.json`. The first run of the day fetches
prices for the whole universe and warms a long-lived sector cache, so it's
slower; same-day re-runs are fast.

The emailed (and `.md`/`.html`) brief expands each ticker's company name and
sector inline on its first mention per section — e.g. `MU (Micron Technology,
Inc. — Technology)` — since tooltips aren't reliable across mail clients. The
`.json` artifact stays raw and unannotated; the dashboard applies its own
tooltip treatment when rendering it.

When the analyst response includes it, the brief also carries a "Trajectory
read" section (emailed brief, `.md`/`.html`, and the dashboard's brief detail
panel) describing what the return term structure shows across that week's
names — descriptive only. No forward conclusion is drawn from it, and no
ranking, sorting, or filtering anywhere in Vantage depends on it; the reason
is recorded in `config/evidence.yaml`. Briefs written before this field
existed simply omit the section.

### Conversational analyst

```bash
python chat.py
```

Loads your live portfolio, the latest saved signals, your interest overlay, and
the latest brief, then gives you an interactive prompt. Things to ask:

- **Debate decisions:** `Challenge my 15% META position.` ·
  `Is my tech concentration too aggressive for "moderate" risk?`
- **Exact figures (real data tool):** `What's CEG's 12-month return and volume ratio?`
- **Re-run the screen:** `Re-run the screen with the volume threshold at 3x.` ·
  `Show me only 12-month leaders above +200%.`
- **Current news (web search):** `What's the latest news driving Western Digital?`
- **Reference context:** `Tell me more about the memory item in this week's brief.` ·
  `Given my holdings, what am I most exposed to if AI capex slows?`

When it fetches data mid-answer you'll see a note like
`[looking up via get_ticker_metrics({'ticker': 'CEG'})]`. Exit with `exit`,
`quit`, or Ctrl-D; each session is saved to `reports/chat-<timestamp>.md`. Each
turn is a real (paid) Claude call, so expect a brief pause while it thinks.

### Web dashboard

```bash
python -m vantage.web
```

Opens a local server at `http://127.0.0.1:8000` with a two-column editorial
dashboard: data panels on the left (Overview, Portfolio, Signals, Briefs) and
an analyst chat docked on the right.

- **Data panels** read the latest artifacts from `data/` and `reports/` — no
  re-run needed. If no artifacts are present yet, panels show "None" /
  "Unavailable" without errors.
- **Ticker identity** — tickers on the dashboard (Overview leaders, Signals,
  Portfolio positions) show company name and sector beneath them when known,
  degrading to whichever part is available (a lookup can fail or an entry can
  lack a name). Tickers mentioned inside brief prose, the watchlist, and chat
  replies carry a hover/focus tooltip with the same information instead.
- **Refresh data** re-runs the full quantitative pipeline (market fetch →
  screener → portfolio context) and reloads all panels on completion. This
  makes real market-data requests and takes a few minutes.
- **Analyst chat** streams responses token-by-token using the same
  conversational engine as `chat.py`. Requires `ANTHROPIC_API_KEY`. "New
  conversation" starts a fresh session.

The server uses the same `WAKE_PATH` and portfolio settings as the CLI; if
Wake is unreachable, Portfolio shows "Unavailable" and the other panels are
unaffected.

### Rebuild the ticker universe

```bash
python tools/build_universe.py   # refreshes config/universe.txt (needs lxml)
```

Fetches current S&P 500 + Nasdaq-100 + S&P 400 constituents and writes them
yfinance-normalized to `config/universe.txt`. (`lxml` is a tooling-only
dependency, not needed by the pipeline itself.)

### Backfill ticker names

```bash
python tools/backfill_ticker_names.py
```

One-time pass that fills the `name` field for every already-cached ticker in
`cache/sectors.json` (sector-only entries from before ticker identity was
added). The weekly pipeline self-heals this cache on its own as it runs, so
this tool only exists to avoid waiting out the normal refresh cadence.

### Momentum term structure

`vantage/momentum.py` compares an asset's recent pace (default: trailing
3-month annualized return) against its own long-run (trailing 12-month)
pace to classify it as `accelerating`, `steady`, `fading`, or `unknown`,
optionally adjusted for volatility and benchmark-relative pace. It is a
pure module — no I/O, no settings — used only by the two tools below.

`tools/fetch_history.py` (deep, ~10-year single-vintage price fetch),
`tools/backtest_momentum.py` (cohort backtest + parameter sweep),
`tools/backtest_conditional.py` (two follow-up experiments) and
`tools/analyze_conditional.py` (significance context for the latter) are
**tooling-only**: they are run by hand for research and are never invoked
by the weekly pipeline or the dashboard. Phase 1 ships no behavior change
to the brief, the screener, or the dashboard.

`run_backtest` reports each cohort's forward return two ways, and the
difference between them matters: the aggregate median/mean per cohort, and
the **paired** per-date differences (`paired`) with hit rate and dispersion.
A difference of two separately-aggregated medians is not the median of the
per-date differences — median is not linear — and reading the first as if it
were the second reversed three conclusions in the finding below before it was
caught. Use `paired`. `per_date` retains the raw per-formation-date series so
a comparison between two runs (e.g. two parameter settings) can be paired
too.

The backtest asked whether the acceleration score predicts forward returns
better than the trailing 12-month rank Vantage uses today. Finding (a
negative result — the score did not beat 12-month momentum in this
backtest):
`docs/superpowers/findings/2026-08-13-momentum-backtest.md`.

Two pre-registered follow-ups asked the questions that study did not:
whether trajectory discriminates *among* 12-month leaders (top 30 split into
high- and low-score halves), and whether `sector_breadth` predicts sector
forward returns. Both are null — 0 of 30 pre-registered comparisons reach
conventional significance. Finding:
`docs/superpowers/findings/2026-08-14-conditional-and-sector-breadth.md`.
`tools/backtest_conditional.py` deliberately exposes **no** aggregate
cross-cohort spread at all; pairing is the only cross-cohort route it offers.

### Tests

```bash
python -m pytest -q
```

## Configuration

- **`.env`** — secrets (git-ignored). See `.env.example`. Optional
  `VANTAGE_MODEL` overrides the analyst model (default `claude-opus-4-8`);
  `WAKE_PATH` overrides the Wake (portfolio data) location.
- **`config/universe.txt`** — the ticker universe, one symbol per line
  (`#` comments allowed). Regenerate with `tools/build_universe.py`.
- **`config/interests.yaml`** — your interest overlay (themes, sectors, risk
  appetite) that the analyst weighs alongside your actual holdings.
- **`config/evidence.yaml`** — the evidence register: claims about this
  market universe that have been tested empirically, each recorded with a
  verdict (`supported`/`refuted`) and the data behind it. Both the weekly
  brief and the conversational analyst load it (`vantage/evidence.py`) and
  include it in their prompts, so the analyst treats prior findings as
  settled rather than re-litigating them. A new entry is appended after each
  study; see `docs/superpowers/findings/` for the studies themselves.
  `tests/test_evidence_config.py` enforces the register's schema and asserts
  that every cited finding path exists on disk. This changes only what the
  analyst knows going in — it ships no change to what it shows you.

## Outputs

| Path | What |
|---|---|
| `reports/brief-<date>.{md,html,json}` | The weekly brief, three formats |
| `reports/chat-<timestamp>.md` | A conversational-analyst transcript |
| `data/signals-<date>.json` | The deterministic screener output |
| `cache/` | yfinance price cache + long-lived `sectors.json` |

(`reports/`, `data/`, and `cache/` are git-ignored.)

## Schedule (cron)

Weekly, Sunday 7am:

```
0 7 * * 0 cd ~/code/python/vantage && /path/to/.venv/bin/python run_weekly.py >> reports/cron.log 2>&1
```

## Architecture

Hybrid: deterministic Python for data + screening (reproducible, unit-tested)
and a Claude analyst layer for judgment (narratives, convergence, second-order
reasoning, challenge). Units communicate through plain dataclasses.

- Weekly pipeline: `data_ingest → screener → portfolio_context → analyst → report → deliver`
- Conversational analyst: a web-ready `Conversation` engine (`vantage/conversation.py`)
  whose `send()` yields an event stream, consumed by the `chat.py` terminal REPL;
  it reuses the analyst persona (`vantage/persona.py`) and custom tools
  (`vantage/chat_tools.py`) over the same deterministic units.

Design specs:
- `docs/superpowers/specs/2026-06-26-market-insights-blind-spot-radar-design.md`
- `docs/superpowers/specs/2026-06-27-conversational-analyst-design.md`

Planned fast-follow: daily signal alerts (`run_daily.py`, reusing the screener).
The web dashboard (`python -m vantage.web`, `vantage/web/`) serves the same conversational engine plus read views of signals, portfolio, and briefs in the browser over SSE.
