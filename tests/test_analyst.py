import json
from vantage.models import SignalSet, Signal, PortfolioContext, Brief
from vantage.analyst import build_prompt, parse_brief

def _sigset():
    return SignalSet(as_of="2026-06-26",
                     signals=[Signal(ticker="MU", signal_type="ret_12m_leader",
                                     value=1.4, rank=1, sector="Technology",
                                     metrics={"ret_12m": 1.4})],
                     sector_momentum={"Technology": 0.2})

def test_build_prompt_includes_signals_portfolio_and_challenge_instruction():
    pc = PortfolioContext(available=True, holdings=[], sector_concentration={},
                          asset_type_concentration={}, revealed_interests=["Energy"],
                          note="")
    prompt = build_prompt(_sigset(), pc, {"themes": ["AI"], "risk_appetite": "moderate"})
    assert "MU" in prompt
    assert "Energy" in prompt
    assert "challenge" in prompt.lower()           # challenge/coaching instruction present
    assert "second-order" in prompt.lower()        # supply-chain reasoning instruction
    assert "json" in prompt.lower()                # output-format instruction

def test_parse_brief_reads_model_json():
    payload = {
        "executive_summary": "summary",
        "items": [{"title": "Memory boom", "thesis": "t", "evidence": "e",
                   "sources": ["http://x"], "why_it_matters": "w",
                   "portfolio_relevance": "p"}],
        "watchlist": ["NVDA"],
        "challenge": "You sold WDC early.",
        "what_im_missing": "m",
    }
    text = "prose...\n```json\n" + json.dumps(payload) + "\n```\ntrailing"
    brief = parse_brief(text, as_of="2026-06-26")
    assert isinstance(brief, Brief)
    assert brief.items[0].title == "Memory boom"
    assert brief.challenge == "You sold WDC early."
    assert "not financial advice" in brief.disclaimer.lower()

def test_parse_brief_reads_bare_json_no_fence():
    payload = {"executive_summary": "s", "items": [], "watchlist": [],
               "challenge": "c", "what_im_missing": "m"}
    text = "Here is the brief: " + json.dumps(payload) + " done."
    brief = parse_brief(text, as_of="2026-06-26")
    assert brief.executive_summary == "s"
    assert brief.challenge == "c"
    assert "not financial advice" in brief.disclaimer.lower()

def test_parse_brief_raises_on_no_json():
    import pytest
    with pytest.raises(ValueError):
        parse_brief("no json object here at all", as_of="2026-06-26")
