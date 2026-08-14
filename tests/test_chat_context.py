# tests/test_chat_context.py
import json
from pathlib import Path
from vantage.settings import Settings
from vantage.chat_context import ChatContext, load_chat_context
from vantage.models import SignalSet, Signal, Brief, BriefItem, PortfolioContext

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

def test_chat_context_renders_the_evidence_block():
    from vantage.chat_context import ChatContext
    from vantage.evidence import Evidence, Claim
    ev = Evidence(universe="913 tickers", claims=[
        Claim("id1", "A tested claim.", "refuted", "2026-08-13", "e",
              "Do not act on it.", "docs/f.md")])
    text = ChatContext(evidence=ev).render()
    assert "Evidence register" in text
    assert "Do not act on it." in text

def test_chat_context_without_evidence_renders_without_the_block():
    from vantage.chat_context import ChatContext
    assert "Evidence register" not in ChatContext().render()

def test_load_chat_context_loads_the_register(tmp_path, monkeypatch):
    import yaml
    from vantage.chat_context import load_chat_context
    from vantage.models import PortfolioContext
    for sub in ("config", "data", "reports"):
        (tmp_path / sub).mkdir()
    (tmp_path / "config" / "evidence.yaml").write_text(yaml.safe_dump({"claims": [{
        "id": "x", "claim": "A tested claim.", "verdict": "refuted",
        "tested": "2026-08-13", "evidence": "e", "implication": "i",
        "finding": "f.md"}]}), encoding="utf-8")

    class _S:
        config_dir = tmp_path / "config"
        data_dir = tmp_path / "data"
        reports_dir = tmp_path / "reports"
        portfolio_analysis_path = "/x"
    ctx = load_chat_context(_S(),
                            _portfolio_fn=lambda p: PortfolioContext(available=False, note="x"))
    assert ctx.evidence is not None
    assert "A tested claim." in ctx.render()
