import json
from pathlib import Path
from fastapi.testclient import TestClient
from vantage.settings import Settings
from vantage.models import SignalSet, Signal, Brief, PortfolioContext, Holding
from vantage.web.app import create_app

def _settings(tmp_path):
    for sub in ("reports", "data", "config", "cache"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    return Settings(anthropic_api_key="k", gmail_user="", gmail_app_password="",
                    email_recipient="", model="m", portfolio_analysis_path="/x",
                    project_root=tmp_path, config_dir=tmp_path / "config",
                    data_dir=tmp_path / "data", reports_dir=tmp_path / "reports",
                    cache_dir=tmp_path / "cache")

def _seed(s):
    SignalSet("2026-06-27", [Signal("NVDA", "ret_12m_leader", 1.8, 1, "Technology")],
              {"Technology": 0.4}).save(s.data_dir / "signals-2026-06-27.json")
    b = Brief("2026-06-27", "exec summary", [], ["MU"], "c", "m", "d")
    (s.reports_dir / "brief-2026-06-27.json").write_text(json.dumps(b.to_dict()))
    (s.reports_dir / "brief-2026-06-27.html").write_text("<h1>Brief</h1>")

def _client(s, available=True):
    pf = (PortfolioContext(available=True,
                           holdings=[Holding("NVDA", "Nvidia", 10, 100,
                                             current_value=1000, pct_of_portfolio=0.5,
                                             sector="Technology")],
                           sector_concentration={"Technology": 0.5})
          if available else PortfolioContext(available=False, note="db down"))
    return TestClient(create_app(settings=s, portfolio_loader=lambda path: pf))

def test_overview(tmp_path):
    s = _settings(tmp_path); _seed(s)
    r = _client(s).get("/api/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["top_leaders"][0]["ticker"] == "NVDA"
    assert body["portfolio"]["available"] is True
    assert body["watchlist"] == ["MU"]

def test_signals_and_empty(tmp_path):
    s = _settings(tmp_path); _seed(s)
    assert _client(s).get("/api/signals").json()["as_of"] == "2026-06-27"
    s2 = _settings(tmp_path / "empty")
    assert _client(s2).get("/api/signals").json() == {
        "as_of": None, "signals": [], "sector_momentum": {}}

def test_portfolio_unavailable(tmp_path):
    s = _settings(tmp_path)
    body = _client(s, available=False).get("/api/portfolio").json()
    assert body["available"] is False and body["note"] == "db down"

def test_briefs_list_and_fetch_and_404(tmp_path):
    s = _settings(tmp_path); _seed(s)
    c = _client(s)
    assert c.get("/api/briefs").json()[0]["as_of"] == "2026-06-27"
    one = c.get("/api/briefs/2026-06-27").json()
    assert one["brief"]["watchlist"] == ["MU"]
    assert one["html"] == "<h1>Brief</h1>"
    assert c.get("/api/briefs/2099-01-01").status_code == 404

def test_tickers_endpoint(tmp_path):
    s = _settings(tmp_path); _seed(s)
    (s.cache_dir / "sectors.json").write_text(json.dumps(
        {"NVDA": {"sector": "Technology", "name": "NVIDIA Corporation",
                  "fetched": "2026-08-11"},
         "MU": {"sector": "Technology", "name": "Micron Technology",
                "fetched": "2026-08-11"}}))
    r = _client(s).get("/api/tickers")
    assert r.status_code == 200
    body = r.json()
    assert body["NVDA"]["name"] == "Nvidia"   # in signals + holdings; holding name wins over cache
    assert body["MU"]["sector"] == "Technology"           # in the brief watchlist
    assert body["MU"]["common_word"] is False

def test_tickers_endpoint_empty_when_no_artifacts(tmp_path):
    s = _settings(tmp_path)
    assert _client(s, available=False).get("/api/tickers").json() == {}
