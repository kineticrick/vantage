from vantage.portfolio_context import load_portfolio_context
from vantage.models import PortfolioContext

def _fake_loader(pa_path):
    return {
        "holdings": [
            {"ticker": "AAPL", "name": "Apple", "shares": 10, "cost_basis": 1000,
             "current_value": 3000, "pct_of_portfolio": 0.6,
             "sector": "Technology", "asset_type": "Common Stock"},
            {"ticker": "XOM", "name": "Exxon", "shares": 20, "cost_basis": 2000,
             "current_value": 2000, "pct_of_portfolio": 0.4,
             "sector": "Energy", "asset_type": "Common Stock"},
        ],
        "revealed_interests": ["Technology", "Energy", "Semiconductors"],
    }

def test_load_portfolio_context_builds_concentrations():
    pc = load_portfolio_context("/unused", _loader=_fake_loader)
    assert isinstance(pc, PortfolioContext) and pc.available
    assert pc.sector_concentration["Technology"] == 0.6
    assert pc.asset_type_concentration["Common Stock"] == 1.0
    assert "Semiconductors" in pc.revealed_interests

def test_load_portfolio_context_degrades_on_error():
    def boom(pa_path):
        raise RuntimeError("db down")
    pc = load_portfolio_context("/unused", _loader=boom)
    assert pc.available is False and "db down" in pc.note

def test_load_portfolio_context_degrades_on_malformed_holding():
    def bad_holdings(pa_path):
        return {"holdings": [{"ticker": "AAPL", "unexpected_field": 1}],
                "revealed_interests": []}
    pc = load_portfolio_context("/unused", _loader=bad_holdings)
    assert pc.available is False
    assert pc.note  # carries the error reason
