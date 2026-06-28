# Market Insights — Blind-Spot Radar

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
  full transaction history from the `portfolio_analysis` project (read-only).
- **Challenge-first** — it pressure-tests over-concentration, stale theses,
  missed rotations, and recurring behavioral patterns in your trading history.

## Setup

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `cp .env.example .env` and fill in:
   - `ANTHROPIC_API_KEY` — required for the analyst (both modes).
   - `GMAIL_USER`, `GMAIL_APP_PASSWORD` (a Gmail **App Password**, not your
     login), `EMAIL_RECIPIENT` — only needed to *email* the weekly brief.
4. Make sure the `portfolio_analysis` codebase is at
   `/home/kineticrick/code/python/portfolio_analysis` (or set
   `PORTFOLIO_ANALYSIS_PATH`), and its MySQL DB is reachable. If it isn't, both
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

### Rebuild the ticker universe

```bash
python tools/build_universe.py   # refreshes config/universe.txt (needs lxml)
```

Fetches current S&P 500 + Nasdaq-100 + S&P 400 constituents and writes them
yfinance-normalized to `config/universe.txt`. (`lxml` is a tooling-only
dependency, not needed by the pipeline itself.)

### Tests

```bash
python -m pytest -q
```

## Configuration

- **`.env`** — secrets (git-ignored). See `.env.example`. Optional
  `RADAR_MODEL` overrides the analyst model (default `claude-opus-4-8`);
  `PORTFOLIO_ANALYSIS_PATH` overrides the portfolio_analysis location.
- **`config/universe.txt`** — the ticker universe, one symbol per line
  (`#` comments allowed). Regenerate with `tools/build_universe.py`.
- **`config/interests.yaml`** — your interest overlay (themes, sectors, risk
  appetite) that the analyst weighs alongside your actual holdings.

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
0 7 * * 0 cd /home/kineticrick/code/python/market_insights && /path/to/.venv/bin/python run_weekly.py >> reports/cron.log 2>&1
```

## Architecture

Hybrid: deterministic Python for data + screening (reproducible, unit-tested)
and a Claude analyst layer for judgment (narratives, convergence, second-order
reasoning, challenge). Units communicate through plain dataclasses.

- Weekly pipeline: `data_ingest → screener → portfolio_context → analyst → report → deliver`
- Conversational analyst: a web-ready `Conversation` engine (`radar/conversation.py`)
  whose `send()` yields an event stream, consumed by the `chat.py` terminal REPL;
  it reuses the analyst persona (`radar/persona.py`) and custom tools
  (`radar/chat_tools.py`) over the same deterministic units.

Design specs:
- `docs/superpowers/specs/2026-06-26-market-insights-blind-spot-radar-design.md`
- `docs/superpowers/specs/2026-06-27-conversational-analyst-design.md`

Planned fast-follow: daily signal alerts (`run_daily.py`, reusing the screener).
A web UI for the conversational analyst is a deliberate future addition — the
engine's event-stream interface is built so it's a clean add.
