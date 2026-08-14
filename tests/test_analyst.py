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

def test_build_prompt_without_evidence_omits_the_block():
    from vantage.analyst import build_prompt
    from vantage.models import SignalSet, Signal, PortfolioContext
    ss = SignalSet("2026-08-13", [Signal("MU", "ret_12m_leader", 6.3, 1)], {})
    p = build_prompt(ss, PortfolioContext(available=False, note="x"), {})
    assert "Evidence register" not in p

def test_build_prompt_includes_the_evidence_block():
    from vantage.analyst import build_prompt
    from vantage.evidence import Evidence, Claim
    from vantage.models import SignalSet, Signal, PortfolioContext
    ev = Evidence(universe="913 tickers", limits=["survivorship bias"], claims=[
        Claim("acceleration-beats-12m", "Acceleration beats 12m rank.",
              "refuted", "2026-08-13", "36 of 36 negative.",
              "Do not rank on it.", "docs/f.md")])
    ss = SignalSet("2026-08-13", [Signal("MU", "ret_12m_leader", 6.3, 1)], {})
    p = build_prompt(ss, PortfolioContext(available=False, note="x"), {}, ev)
    assert "Evidence register" in p
    assert "REFUTED" in p
    assert "Do not rank on it." in p

def test_generate_brief_loads_the_register_from_settings(tmp_path):
    # The register reaches the prompt without run_weekly passing it.
    import yaml
    from vantage.analyst import generate_brief
    from vantage.models import SignalSet, Signal, PortfolioContext
    (tmp_path / "evidence.yaml").write_text(yaml.safe_dump({"claims": [{
        "id": "x", "claim": "A tested claim.", "verdict": "refuted",
        "tested": "2026-08-13", "evidence": "e", "implication": "i",
        "finding": "f.md"}]}), encoding="utf-8")

    seen = {}
    class _FakeStream:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get_final_message(self):
            class M: content = [type("B", (), {"type": "text",
                "text": '```json\n{"executive_summary": "s", "items": [], '
                        '"watchlist": [], "challenge": "", '
                        '"what_im_missing": ""}\n```'})()]
            return M()
    class _FakeMessages:
        def stream(self, **kw):
            seen["prompt"] = kw["messages"][0]["content"]
            return _FakeStream()
    class _FakeClient:
        messages = _FakeMessages()

    class _S:
        anthropic_api_key = "k"; model = "m"; config_dir = tmp_path
    ss = SignalSet("2026-08-13", [Signal("MU", "ret_12m_leader", 6.3, 1)], {})
    generate_brief(ss, PortfolioContext(available=False, note="x"), {}, _S(),
                   _client=_FakeClient())
    assert "A tested claim." in seen["prompt"]

def test_json_schema_asks_for_trajectory_read():
    from vantage.analyst import _JSON_OUTPUT
    assert "trajectory_read" in _JSON_OUTPUT

def test_parse_brief_reads_trajectory_read():
    from vantage.analyst import parse_brief
    text = ('```json\n{"executive_summary": "s", "items": [], "watchlist": [],'
            ' "challenge": "", "what_im_missing": "",'
            ' "trajectory_read": "Memory names are rolling over on 1m."}\n```')
    assert parse_brief(text, "2026-08-14").trajectory_read.startswith("Memory")

def test_parse_brief_without_the_key_defaults_to_empty():
    from vantage.analyst import parse_brief
    text = ('```json\n{"executive_summary": "s", "items": [], "watchlist": [],'
            ' "challenge": "", "what_im_missing": ""}\n```')
    assert parse_brief(text, "2026-08-14").trajectory_read == ""
