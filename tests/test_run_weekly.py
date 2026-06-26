# tests/test_run_weekly.py
from pathlib import Path
import run_weekly
from radar.settings import Settings
from radar.data_ingest import MarketData
from radar.models import PortfolioContext, Brief, BriefItem
import pandas as pd

def _settings(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "universe.txt").write_text("AAPL\n")
    (tmp_path / "config" / "interests.yaml").write_text("themes: [AI]\n")
    for d in ("data", "reports", "cache"):
        (tmp_path / d).mkdir()
    return Settings(anthropic_api_key="k", gmail_user="m@x.com",
                    gmail_app_password="pw", email_recipient="y@x.com",
                    model="claude-opus-4-8", portfolio_analysis_path="/x",
                    project_root=tmp_path, config_dir=tmp_path / "config",
                    data_dir=tmp_path / "data", reports_dir=tmp_path / "reports",
                    cache_dir=tmp_path / "cache")

def test_run_weekly_orchestrates(tmp_path):
    s = _settings(tmp_path)
    idx = pd.date_range("2025-06-01", periods=260, freq="D")
    md = MarketData(as_of="2026-06-26",
                    prices={"AAPL": pd.Series([100.0 + i for i in range(260)], index=idx)},
                    volumes={"AAPL": pd.Series([1000.0] * 260, index=idx)},
                    sectors={"AAPL": "Technology"})
    pc = PortfolioContext(available=True, holdings=[], sector_concentration={},
                          asset_type_concentration={}, revealed_interests=[], note="")
    brief = Brief(as_of="2026-06-26", executive_summary="s",
                  items=[BriefItem(title="t", thesis="x", evidence="x",
                                   sources=[], why_it_matters="x",
                                   portfolio_relevance="x")],
                  watchlist=[], challenge="c", what_im_missing="m",
                  disclaimer="Not financial advice.")
    sent = {}
    path = run_weekly.run(
        settings=s,
        _market_data_fn=lambda tickers, cache_dir: md,
        _portfolio_fn=lambda pa_path: pc,
        _analyst_fn=lambda ss, pcx, interests, st: brief,
        _send_fn=lambda subject, html, st: sent.update({"subject": subject, "html": html}),
    )
    assert Path(path).exists()
    assert (s.data_dir / "signals-2026-06-26.json").exists()
    assert "Weekly Brief" in sent["subject"]
    assert "Not financial advice" in sent["html"]

def test_run_weekly_handles_missing_interests_yaml(tmp_path):
    s = _settings(tmp_path)
    (s.config_dir / "interests.yaml").unlink()  # file absent
    idx = pd.date_range("2025-06-01", periods=260, freq="D")
    md = MarketData(as_of="2026-06-26",
                    prices={"AAPL": pd.Series([100.0 + i for i in range(260)], index=idx)},
                    volumes={"AAPL": pd.Series([1000.0] * 260, index=idx)},
                    sectors={"AAPL": "Technology"})
    pc = PortfolioContext(available=True, holdings=[], sector_concentration={},
                          asset_type_concentration={}, revealed_interests=[], note="")
    brief = Brief(as_of="2026-06-26", executive_summary="s",
                  items=[BriefItem(title="t", thesis="x", evidence="x",
                                   sources=[], why_it_matters="x",
                                   portfolio_relevance="x")],
                  watchlist=[], challenge="c", what_im_missing="m",
                  disclaimer="Not financial advice.")
    path = run_weekly.run(
        settings=s,
        _market_data_fn=lambda tickers, cache_dir: md,
        _portfolio_fn=lambda pa_path: pc,
        _analyst_fn=lambda ss, pcx, interests, st: brief,
        _send_fn=lambda subject, html, st: None,
    )
    assert Path(path).exists()
