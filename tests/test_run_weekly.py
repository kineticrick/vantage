# tests/test_run_weekly.py
from pathlib import Path
import run_weekly
from vantage.settings import Settings
from vantage.data_ingest import MarketData
from vantage.models import PortfolioContext, Brief, BriefItem, Holding
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
    # the pipeline persists md + html + json for every report
    assert (s.reports_dir / "brief-2026-06-26.html").exists()
    assert (s.reports_dir / "brief-2026-06-26.json").exists()
    assert (s.data_dir / "signals-2026-06-26.json").exists()
    assert "Weekly Brief" in sent["subject"]
    assert "Not financial advice" in sent["html"]

def test_run_weekly_degrades_when_analyst_fails(tmp_path):
    s = _settings(tmp_path)
    idx = pd.date_range("2025-06-01", periods=260, freq="D")
    md = MarketData(as_of="2026-06-26",
                    prices={"AAPL": pd.Series([100.0 + i for i in range(260)], index=idx)},
                    volumes={"AAPL": pd.Series([1000.0] * 260, index=idx)},
                    sectors={"AAPL": "Technology"})
    pc = PortfolioContext(available=True, holdings=[], sector_concentration={},
                          asset_type_concentration={}, revealed_interests=[], note="")
    def boom(ss, pcx, interests, st):
        raise RuntimeError("api exploded")
    sent = {}
    path = run_weekly.run(
        settings=s,
        _market_data_fn=lambda tickers, cache_dir: md,
        _portfolio_fn=lambda pa_path: pc,
        _analyst_fn=boom,
        _send_fn=lambda subject, html, st: sent.update({"html": html}),
    )
    assert Path(path).exists()
    assert "not financial advice" in sent["html"].lower()
    assert "fallback" in sent["html"].lower()

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

def test_main_no_email_uses_skip_send(monkeypatch):
    captured = {}
    def fake_run(**kwargs):
        captured.update(kwargs)
        return Path("/tmp/brief.md")
    monkeypatch.setattr(run_weekly, "run", fake_run)

    # --no-email passes a _send_fn that does not raise and sends nothing
    run_weekly.main(["--no-email"])
    assert "_send_fn" in captured
    captured["_send_fn"]("subj", "<html>", None)  # no-op, must not raise

    # default (no flag) passes no _send_fn override → real emailing path
    captured.clear()
    run_weekly.main([])
    assert "_send_fn" not in captured

def test_run_weekly_expands_ticker_names_in_html_and_markdown(tmp_path):
    # Regression guard: facts must reach BOTH save_report(...) and
    # render_html(...). A wiring bug that computes facts but only threads
    # them into one of the two call sites would keep every other test in
    # this file green (they all use holdings=[] → facts == {}), while in
    # production the emailed HTML and the saved .md artifact would silently
    # disagree about whether ticker names are expanded.
    s = _settings(tmp_path)
    idx = pd.date_range("2025-06-01", periods=260, freq="D")
    md = MarketData(as_of="2026-06-26",
                    prices={"AAPL": pd.Series([100.0 + i for i in range(260)], index=idx)},
                    volumes={"AAPL": pd.Series([1000.0] * 260, index=idx)},
                    sectors={"AAPL": "Technology"})
    pc = PortfolioContext(
        available=True,
        holdings=[Holding(ticker="MU", name="Micron Technology", shares=10,
                          cost_basis=50.0, sector="Technology")],
        sector_concentration={}, asset_type_concentration={},
        revealed_interests=[], note="")
    brief = Brief(as_of="2026-06-26", executive_summary="MU is having a big week.",
                  items=[], watchlist=[], challenge="", what_im_missing="",
                  disclaimer="Not financial advice.")
    sent = {}
    path = run_weekly.run(
        settings=s,
        _market_data_fn=lambda tickers, cache_dir: md,
        _portfolio_fn=lambda pa_path: pc,
        _analyst_fn=lambda ss, pcx, interests, st: brief,
        _send_fn=lambda subject, html, st: sent.update({"html": html}),
    )
    expanded = "MU (Micron Technology — Technology)"
    assert expanded in sent["html"]
    assert expanded in Path(path).read_text(encoding="utf-8")
