import json
from pathlib import Path
from vantage.models import SignalSet, Signal, Brief, PortfolioContext, Holding
from vantage.web import artifacts as art

def _write_signals(data_dir, as_of, signals, momentum):
    SignalSet(as_of=as_of, signals=signals, sector_momentum=momentum).save(
        data_dir / f"signals-{as_of}.json")

def test_latest_signals_picks_newest(tmp_path):
    _write_signals(tmp_path, "2026-06-20", [], {})
    _write_signals(tmp_path, "2026-06-27", [Signal("NVDA", "ret_12m_leader", 1.8, 1)], {})
    ss = art.latest_signals(tmp_path)
    assert ss.as_of == "2026-06-27"
    assert ss.signals[0].ticker == "NVDA"

def test_latest_signals_none_when_empty(tmp_path):
    assert art.latest_signals(tmp_path) is None

def test_list_and_load_briefs(tmp_path):
    b = Brief(as_of="2026-06-27", executive_summary="Summary text.", items=[],
              watchlist=["MU", "AVGO"], challenge="c", what_im_missing="m",
              disclaimer="d")
    (tmp_path / "brief-2026-06-27.json").write_text(json.dumps(b.to_dict()))
    (tmp_path / "brief-2026-06-27.html").write_text("<h1>Brief</h1>")
    listing = art.list_briefs(tmp_path)
    assert listing == [{"as_of": "2026-06-27", "summary": "Summary text."}]
    loaded = art.load_brief(tmp_path, "2026-06-27")
    assert loaded.watchlist == ["MU", "AVGO"]
    assert art.read_brief_html(tmp_path, "2026-06-27") == "<h1>Brief</h1>"
    assert art.load_brief(tmp_path, "2099-01-01") is None

def test_build_overview_shape():
    ss = SignalSet(as_of="2026-06-27",
                   signals=[Signal("NVDA", "ret_12m_leader", 1.8, 1, "Technology"),
                            Signal("XYZ", "volume_spike", 3.1, 0, "Energy")],
                   sector_momentum={"Technology": 0.4, "Energy": -0.1})
    pf = PortfolioContext(available=True,
                          holdings=[Holding("NVDA", "Nvidia", 10, 100,
                                            current_value=1000, pct_of_portfolio=0.5,
                                            sector="Technology")],
                          sector_concentration={"Technology": 0.5})
    brief = Brief("2026-06-27", "exec", [], ["MU"], "c", "m", "d")
    ov = art.build_overview(ss, pf, brief)
    assert ov["signals_as_of"] == "2026-06-27"
    assert ov["top_leaders"][0]["ticker"] == "NVDA"
    assert ov["top_volume_spikes"][0]["ticker"] == "XYZ"
    assert ov["sector_momentum_top"][0]["sector"] == "Technology"
    assert ov["portfolio"]["available"] is True
    assert ov["portfolio"]["top_positions"][0]["ticker"] == "NVDA"
    assert ov["watchlist"] == ["MU"]
    assert ov["latest_brief"]["as_of"] == "2026-06-27"

def test_build_overview_empty():
    ov = art.build_overview(None, PortfolioContext(available=False, note="db down"), None)
    assert ov["signals_as_of"] is None
    assert ov["top_leaders"] == []
    assert ov["portfolio"] == {"available": False, "note": "db down"}
    assert ov["watchlist"] == []
    assert ov["latest_brief"] is None

def test_build_overview_includes_names():
    from vantage.models import SignalSet, Signal
    from vantage.web.artifacts import build_overview
    ss = SignalSet("2026-08-12",
                   [Signal("MU", "ret_12m_leader", 6.3, 1, "Technology",
                           "Micron Technology")], {})
    o = build_overview(ss, None, None)
    assert o["top_leaders"][0]["name"] == "Micron Technology"
    assert o["top_leaders"][0]["sector"] == "Technology"

def test_relevant_ticker_facts_scopes_and_flags():
    from vantage.models import SignalSet, Signal, Brief, PortfolioContext, Holding
    from vantage.tickers import TickerFacts
    from vantage.web.artifacts import relevant_ticker_facts
    facts = {"MU": TickerFacts("MU", "Micron Technology", "Technology"),
             "ALL": TickerFacts("ALL", "Allstate Corp", "Financial Services"),
             "SMH": TickerFacts("SMH", "VanEck Semiconductor ETF", "Technology"),
             "ZZZZ": TickerFacts("ZZZZ", "Never Mentioned Inc", "Utilities")}
    ss = SignalSet("2026-08-12", [Signal("MU", "ret_12m_leader", 6.3, 1)], {})
    pf = PortfolioContext(available=True,
                          holdings=[Holding("SMH", "VanEck Semiconductor ETF", 1, 1)])
    b = Brief("2026-08-12", "ALL of the moves", [], [], "", "", "d")
    out = relevant_ticker_facts(facts, ss, pf, b)
    assert set(out) == {"MU", "SMH", "ALL"}          # ZZZZ never appears anywhere
    assert out["MU"]["name"] == "Micron Technology"
    assert out["ALL"]["common_word"] is True          # JS applies the cue rule
    assert out["MU"]["common_word"] is False

def test_relevant_ticker_facts_scans_item_fields():
    # Ticker appears only inside a BriefItem field (thesis) — nowhere in the
    # top-level prose (executive_summary/challenge/what_im_missing/watchlist)
    # — so this only passes if _brief_text's loop over brief.items runs.
    from vantage.models import SignalSet, Brief, BriefItem
    from vantage.tickers import TickerFacts
    from vantage.web.artifacts import relevant_ticker_facts
    facts = {"AVGO": TickerFacts("AVGO", "Broadcom Inc", "Technology")}
    ss = SignalSet("2026-08-12", [], {})
    item = BriefItem(title="Semis", thesis="AVGO is accelerating.",
                     evidence="", why_it_matters="", portfolio_relevance="")
    b = Brief("2026-08-12", "no tickers in this summary", [item], [], "", "", "d")
    out = relevant_ticker_facts(facts, ss, None, b)
    assert out == {"AVGO": {"name": "Broadcom Inc", "sector": "Technology",
                            "common_word": False}}

def test_signals_payload_enriches_each_signal():
    from vantage.models import SignalSet, Signal
    from vantage.web.artifacts import signals_payload
    ss = SignalSet("2026-08-14", [
        Signal("MU", "ret_12m_leader", 6.317, 1, "Technology", "Micron",
               {"ret_1m": -0.073, "ret_12m": 6.317})], {})
    payload = signals_payload(ss)
    ts = payload["signals"][0]["term_structure"]
    assert [e["label"] for e in ts] == ["1m", "3m", "6m", "12m", "off high"]
    assert ts[0]["display"] == "-7.3%"
    assert ts[2]["display"] == "--"          # absent metric keeps its column
    assert payload["as_of"] == "2026-08-14"

def test_signals_payload_of_none_is_the_empty_shape():
    from vantage.web.artifacts import signals_payload
    assert signals_payload(None) == {"as_of": None, "signals": [],
                                     "sector_momentum": {}}

def test_build_overview_entries_carry_term_structure():
    from vantage.models import SignalSet, Signal
    from vantage.web.artifacts import build_overview
    ss = SignalSet("2026-08-14", [
        Signal("MU", "ret_12m_leader", 6.317, 1, "Technology", "Micron",
               {"ret_1m": -0.073, "ret_12m": 6.317})], {})
    o = build_overview(ss, None, None)
    assert o["top_leaders"][0]["term_structure"][0]["display"] == "-7.3%"
