import json
from vantage.models import PortfolioContext, Holding
from vantage.tickers import TickerFacts, load_cache_facts, load_facts, resolve

def _write_cache(tmp_path, data):
    (tmp_path / "sectors.json").write_text(json.dumps(data), encoding="utf-8")
    return tmp_path

def test_subtitle_joins_known_parts():
    assert TickerFacts("MU", "Micron Technology", "Technology").subtitle() == \
        "Micron Technology · Technology"
    assert TickerFacts("MU", "Micron Technology").subtitle() == "Micron Technology"
    assert TickerFacts("MU", None, "Technology").subtitle() == "Technology"
    assert TickerFacts("MU").subtitle() == ""
    assert TickerFacts("MU", "Micron Technology", "Technology").subtitle(sep=", ") == \
        "Micron Technology, Technology"

def test_load_cache_facts_reads_name_and_sector(tmp_path):
    _write_cache(tmp_path, {"MU": {"sector": "Technology",
                                   "name": "Micron Technology",
                                   "fetched": "2026-08-11"}})
    facts = load_cache_facts(tmp_path)
    assert facts["MU"].name == "Micron Technology"
    assert facts["MU"].sector == "Technology"
    assert facts["MU"].ticker == "MU"

def test_load_cache_facts_tolerates_legacy_entries_without_name(tmp_path):
    _write_cache(tmp_path, {"AOS": {"sector": "Industrials", "fetched": "2026-08-11"}})
    facts = load_cache_facts(tmp_path)
    assert facts["AOS"].sector == "Industrials"
    assert facts["AOS"].name is None

def test_load_cache_facts_missing_or_corrupt_returns_empty(tmp_path):
    assert load_cache_facts(tmp_path) == {}
    (tmp_path / "sectors.json").write_text("{not json", encoding="utf-8")
    assert load_cache_facts(tmp_path) == {}

def test_load_cache_facts_non_dict_payload_returns_empty(tmp_path):
    (tmp_path / "sectors.json").write_text("[]", encoding="utf-8")
    assert load_cache_facts(tmp_path) == {}
    (tmp_path / "sectors.json").write_text("null", encoding="utf-8")
    assert load_cache_facts(tmp_path) == {}

def test_load_facts_layers_portfolio_over_cache(tmp_path):
    _write_cache(tmp_path, {"NVDA": {"sector": "Tech", "name": "NVIDIA Corp",
                                     "fetched": "2026-08-11"}})
    pf = PortfolioContext(available=True, holdings=[
        Holding("NVDA", "NVIDIA Corporation", 10, 100, sector="Technology"),
        Holding("SMH", "VanEck Semiconductor ETF", 5, 50, sector="Technology"),
    ])
    facts = load_facts(tmp_path, portfolio=pf)
    # portfolio wins where it has a value
    assert facts["NVDA"].name == "NVIDIA Corporation"
    assert facts["NVDA"].sector == "Technology"
    # portfolio adds tickers the cache never had (ETFs)
    assert facts["SMH"].name == "VanEck Semiconductor ETF"

def test_load_facts_portfolio_gap_falls_back_to_cache(tmp_path):
    _write_cache(tmp_path, {"NVDA": {"sector": "Technology", "name": "NVIDIA Corp",
                                     "fetched": "2026-08-11"}})
    pf = PortfolioContext(available=True,
                          holdings=[Holding("NVDA", "", 10, 100, sector=None)])
    facts = load_facts(tmp_path, portfolio=pf)
    assert facts["NVDA"].name == "NVIDIA Corp"
    assert facts["NVDA"].sector == "Technology"

def test_load_facts_ignores_unavailable_portfolio(tmp_path):
    _write_cache(tmp_path, {"MU": {"sector": "Technology", "name": "Micron",
                                   "fetched": "2026-08-11"}})
    pf = PortfolioContext(available=False, note="db down")
    assert load_facts(tmp_path, portfolio=pf)["MU"].name == "Micron"

def test_resolve_unknown_ticker_returns_bare_facts():
    f = resolve("ZZZZ", {})
    assert f.ticker == "ZZZZ" and f.name is None and f.sector is None
