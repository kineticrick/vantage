# tests/test_chat_context.py
import json
from pathlib import Path
from radar.settings import Settings
from radar.chat_context import ChatContext, load_chat_context
from radar.models import SignalSet, Signal, Brief, BriefItem, PortfolioContext

def _settings(tmp_path):
    for d in ("data", "reports", "config"):
        (tmp_path / d).mkdir(exist_ok=True)
    return Settings(anthropic_api_key="", gmail_user="", gmail_app_password="",
                    email_recipient="", model="claude-opus-4-8",
                    portfolio_analysis_path="/x", project_root=tmp_path,
                    config_dir=tmp_path / "config", data_dir=tmp_path / "data",
                    reports_dir=tmp_path / "reports", cache_dir=tmp_path)

def _pc():
    return PortfolioContext(available=True, holdings=[], sector_concentration={"Tech": 0.5},
                            asset_type_concentration={}, revealed_interests=["NVDA"], note="")

def test_load_chat_context_picks_newest_and_renders(tmp_path):
    s = _settings(tmp_path)
    # two signal files; the newest (by name/date) should win
    SignalSet("2026-06-20", [Signal("OLD", "ret_12m_leader", 1.0, 1)], {}).save(
        s.data_dir / "signals-2026-06-20.json")
    SignalSet("2026-06-27", [Signal("MU", "ret_12m_leader", 7.9, 1)], {"Tech": 0.25}).save(
        s.data_dir / "signals-2026-06-27.json")
    (s.config_dir / "interests.yaml").write_text("themes: [AI]\n")
    brief = Brief("2026-06-27", "summary", [BriefItem("t","x","x",[],"x","x")],
                  ["NVDA"], "challenge", "missing", "Not financial advice.")
    (s.reports_dir / "brief-2026-06-27.json").write_text(json.dumps(brief.to_dict()))

    ctx = load_chat_context(s, _portfolio_fn=lambda pa: _pc())
    assert ctx.signals.as_of == "2026-06-27"          # newest
    assert ctx.signals.signals[0].ticker == "MU"
    assert ctx.interests == {"themes": ["AI"]}
    assert ctx.brief.executive_summary == "summary"
    assert ctx.portfolio.available
    text = ctx.render()
    assert "MU" in text and "Tech" in text and "NVDA" in text

def test_load_chat_context_graceful_when_missing(tmp_path):
    s = _settings(tmp_path)  # no signals, no brief, no interests
    ctx = load_chat_context(s, _portfolio_fn=lambda pa: PortfolioContext(available=False, note="db down"))
    assert ctx.signals is None and ctx.brief is None and ctx.interests == {}
    text = ctx.render()
    assert "unavailable" in text.lower() or "no " in text.lower()  # notes the gaps

def test_load_chat_context_survives_corrupt_files(tmp_path):
    s = _settings(tmp_path)
    (s.config_dir / "interests.yaml").write_text("!!invalid: yaml: [")
    (s.data_dir / "signals-2026-06-27.json").write_text("{not valid json")
    (s.reports_dir / "brief-2026-06-27.json").write_text("{not valid json")
    ctx = load_chat_context(s, _portfolio_fn=lambda pa: _pc())
    assert ctx.interests == {}
    assert ctx.signals is None
    assert ctx.brief is None
    assert ctx.render()  # must not raise
