# Market Insights — Blind-Spot Radar

An AI-driven research partner that scans the market weekly, fuses hard
price/volume signals with self-sourced news, and emails a reasoned (and
deliberately challenging) brief. Research aid — **not financial advice**.

## Setup
1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `cp .env.example .env` and fill in `ANTHROPIC_API_KEY`, Gmail credentials
   (use a Gmail **App Password**), and `EMAIL_RECIPIENT`.
4. Edit `config/universe.txt` (ticker universe) and `config/interests.yaml` Regenerate the full S&P 500 + Nasdaq-100 + S&P 400 blend with `python tools/build_universe.py` (needs `lxml`).
   (your interest overlay).
5. Ensure the `portfolio_analysis` codebase is at
   `/home/kineticrick/code/python/portfolio_analysis` (or set
   `PORTFOLIO_ANALYSIS_PATH`). Its MySQL DB must be reachable. If unavailable,
   the radar runs in market-wide-only mode.

## Run
- Weekly digest (full pipeline): `python run_weekly.py`
- Dry run (full real pipeline, writes the brief to `reports/` instead of emailing): `python run_weekly.py --no-email`

Each run writes `reports/brief-<date>.md`, `.html`, and `.json` (the structured brief, for re-rendering).
- Tests: `python -m pytest -v`

## Schedule (cron)
Weekly, Sunday 7am:
```
0 7 * * 0 cd /home/kineticrick/code/python/market_insights && /path/to/.venv/bin/python run_weekly.py >> reports/cron.log 2>&1
```

## Architecture
See `docs/superpowers/specs/2026-06-26-market-insights-blind-spot-radar-design.md`.
Pipeline: data_ingest → screener → portfolio_context → analyst → report → deliver.
Daily alerts are a planned fast-follow.
