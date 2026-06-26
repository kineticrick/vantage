# Final Review Fix Report — feat/weekly-digest-radar

## Fixes Applied

### FIX A — Analyst graceful degradation

**A1. `radar/analyst.py` — `parse_brief` raises on missing JSON**
Added guard before `json.loads`: if `start == -1 or end == -1 or end < start`, raises
`ValueError("Analyst response contained no JSON object")`.

**A2. `run_weekly.py` — fallback brief on analyst failure**
- Added `import logging` and module-level `logger = logging.getLogger(__name__)`.
- Added `_fallback_brief(signal_set, error)` helper that returns a `Brief` using the
  `DISCLAIMER` constant and top 15 quantitative movers as `what_im_missing`.
- Wrapped the analyst call in `try/except Exception`: on failure, logs a WARNING and
  calls `_fallback_brief` so the run continues and emails a degraded-but-useful brief.

**A3. New tests**
- `tests/test_analyst.py::test_parse_brief_raises_on_no_json` — confirms `ValueError`
  is raised when response text has no JSON object.
- `tests/test_run_weekly.py::test_run_weekly_degrades_when_analyst_fails` — injects a
  booming analyst, asserts file saved + fallback HTML sent with disclaimer and "fallback"
  keyword present. Assertion uses `.lower()` to match the DISCLAIMER's lowercase "not
  financial advice" (minor case correction from spec; semantics identical).

---

### FIX B — Cache sectors + logging + flat-column handling (`radar/data_ingest.py`)

- Added `import json`, `import logging`, and `logger = logging.getLogger(__name__)`.
- Added `_extract_series(df, field, ticker)` helper that handles both `pd.MultiIndex`
  columns (yfinance multi-ticker download) and flat columns (single-ticker / test frames).
- Replaced `fetch_market_data` body:
  - Writes a `.sectors.json` sidecar next to each parquet cache; reads it on cache-hit,
    so `sector_fn` is called at most once per batch per day.
  - Uses `_extract_series` instead of hardcoded `df[("Close", t)]`.
  - Logs `WARNING` for missing tickers, `INFO` per-batch loaded count, and `WARNING`
    when the result is empty.

**New tests**
- `tests/test_data_ingest.py::test_fetch_market_data_caches_sectors` — verifies sector
  function is called exactly once across two `fetch_market_data` calls (sidecar hit).
- `tests/test_data_ingest.py::test_fetch_market_data_handles_flat_columns` — passes a
  flat (non-MultiIndex) DataFrame, asserts prices and volumes load correctly.

---

### FIX C — Two merge-worthy minors

**C1. `radar/models.py` — asset-type concentration in `summary_text()`**
Added a line after sector concentration:
```python
lines.append("Asset-type concentration: " + ", ".join(
    f"{k} {v:.0%}" for k, v in self.asset_type_concentration.items()))
```
This surfaces ETF/equity/bond splits to the analyst prompt.

**C2. `radar/portfolio_context.py` — truncate exception string**
Changed `note=str(e)` to `note=str(e)[:200]` in the `except Exception` degradation
branch to prevent a DB exception string from leaking full tracebacks into the prompt.

---

## Full Suite Output

```
============================= test session starts ==============================
platform linux -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0
collected 27 items

tests/test_analyst.py::test_build_prompt_includes_signals_portfolio_and_challenge_instruction PASSED
tests/test_analyst.py::test_parse_brief_reads_model_json PASSED
tests/test_analyst.py::test_parse_brief_reads_bare_json_no_fence PASSED
tests/test_analyst.py::test_parse_brief_raises_on_no_json PASSED
tests/test_data_ingest.py::test_fetch_market_data_builds_series PASSED
tests/test_data_ingest.py::test_fetch_market_data_caches PASSED
tests/test_data_ingest.py::test_fetch_market_data_caches_sectors PASSED
tests/test_data_ingest.py::test_fetch_market_data_handles_flat_columns PASSED
tests/test_deliver.py::test_send_email_builds_and_sends PASSED
tests/test_models.py::test_signalset_roundtrip PASSED
tests/test_models.py::test_portfolio_context_summary_text PASSED
tests/test_models.py::test_brief_roundtrip PASSED
tests/test_portfolio_context.py::test_load_portfolio_context_builds_concentrations PASSED
tests/test_portfolio_context.py::test_load_portfolio_context_degrades_on_error PASSED
tests/test_portfolio_context.py::test_load_portfolio_context_degrades_on_malformed_holding PASSED
tests/test_report.py::test_render_markdown_contains_sections PASSED
tests/test_report.py::test_render_html_is_html PASSED
tests/test_report.py::test_render_html_escapes_and_sanitizes_links PASSED
tests/test_report.py::test_save_markdown_writes_dated_file PASSED
tests/test_run_weekly.py::test_run_weekly_orchestrates PASSED
tests/test_run_weekly.py::test_run_weekly_degrades_when_analyst_fails PASSED
tests/test_run_weekly.py::test_run_weekly_handles_missing_interests_yaml PASSED
tests/test_screener.py::test_screener_flags_12m_leader_and_volume_spike PASSED
tests/test_screener.py::test_screener_ranks_by_12m_return PASSED
tests/test_screener.py::test_screener_short_series_emits_no_signals PASSED
tests/test_settings.py::test_load_settings_reads_env_and_makes_dirs PASSED
tests/test_universe.py::test_load_universe_parses_and_dedupes PASSED

============================== 27 passed in 0.36s ==============================
```

**Total: 27/27 passing**
