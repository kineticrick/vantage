from vantage.models import Signal, SignalSet, Holding, PortfolioContext, Brief, BriefItem

def test_signalset_roundtrip(tmp_path):
    ss = SignalSet(
        as_of="2026-06-26",
        signals=[Signal(ticker="MU", signal_type="ret_12m_leader", value=1.4,
                        rank=1, sector="Technology",
                        metrics={"ret_12m": 1.4, "volume_ratio": 2.1})],
        sector_momentum={"Technology": 0.22},
    )
    p = tmp_path / "ss.json"
    ss.save(p)
    loaded = SignalSet.load(p)
    assert loaded.as_of == "2026-06-26"
    assert loaded.signals[0].ticker == "MU"
    assert loaded.signals[0].metrics["ret_12m"] == 1.4
    assert loaded.sector_momentum["Technology"] == 0.22

def test_portfolio_context_summary_text():
    pc = PortfolioContext(
        available=True,
        holdings=[Holding(ticker="AAPL", name="Apple", shares=10, cost_basis=1000,
                          current_value=2000, pct_of_portfolio=0.5,
                          sector="Technology", asset_type="Common Stock")],
        sector_concentration={"Technology": 0.5},
        asset_type_concentration={"Common Stock": 1.0},
        revealed_interests=["Technology"],
        note="",
    )
    text = pc.summary_text()
    assert "AAPL" in text and "Technology" in text

def test_brief_roundtrip():
    b = Brief(as_of="2026-06-26", executive_summary="x",
              items=[BriefItem(title="t", thesis="th", evidence="e",
                               sources=["http://s"], why_it_matters="w",
                               portfolio_relevance="p")],
              watchlist=["NVDA"], challenge="c", what_im_missing="m",
              disclaimer="not advice")
    d = b.to_dict()
    b2 = Brief.from_dict(d)
    assert b2.items[0].sources == ["http://s"]
    assert b2.challenge == "c"
