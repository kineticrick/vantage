import json
from pathlib import Path

import pytest

from vantage.models import PortfolioContext, Holding
from vantage.tickers import TickerFacts, load_cache_facts, load_facts, resolve
from vantage.tickers import (COMMON_WORD_TICKERS, is_common_word,
                             find_mentions, expand_first_mention)

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

_FACTS = {
    "MU": TickerFacts("MU", "Micron Technology", "Technology"),
    "WDC": TickerFacts("WDC", "Western Digital", "Technology"),
    "ALL": TickerFacts("ALL", "Allstate Corp", "Financial Services"),
    "BRK-B": TickerFacts("BRK-B", "Berkshire Hathaway", "Financial Services"),
    "NONAME": TickerFacts("NONAME"),
}

def test_is_common_word():
    assert is_common_word("ALL") and is_common_word("IT") and is_common_word("ON")
    assert not is_common_word("MU") and not is_common_word("NVDA")

def test_find_mentions_only_known_tickers():
    found = [t for _, _, t in find_mentions("MU and WDC led; ZZZZ did not", _FACTS)]
    assert found == ["MU", "WDC"]

def test_find_mentions_skips_common_words_without_price_cue():
    assert find_mentions("This is ALL of the story", _FACTS) == []

def test_find_mentions_accepts_common_word_with_price_cue():
    assert [t for _, _, t in find_mentions("ALL +32% on the year", _FACTS)] == ["ALL"]
    assert [t for _, _, t in find_mentions("ALL $214 a share", _FACTS)] == ["ALL"]

def test_find_mentions_handles_dotted_class_shares():
    assert [t for _, _, t in find_mentions("BRK-B lagged", _FACTS)] == ["BRK-B"]

def test_expand_first_mention_expands_once():
    out = expand_first_mention("MU rose, then MU fell", _FACTS)
    assert out == "MU (Micron Technology, Technology) rose, then MU fell"

def test_expand_first_mention_shares_seen_across_calls():
    seen = set()
    a = expand_first_mention("MU rose", _FACTS, seen)
    b = expand_first_mention("MU fell", _FACTS, seen)
    assert "Micron Technology" in a
    assert b == "MU fell"

def test_expand_first_mention_fresh_seen_expands_again():
    a = expand_first_mention("MU rose", _FACTS, set())
    b = expand_first_mention("MU fell", _FACTS, set())
    assert "Micron Technology" in a and "Micron Technology" in b

def test_expand_first_mention_omitted_seen_does_not_leak_between_calls():
    a = expand_first_mention("MU rose", _FACTS)
    b = expand_first_mention("MU fell", _FACTS)
    assert "Micron Technology" in a and "Micron Technology" in b

def test_expand_first_mention_skips_ticker_with_no_facts():
    assert expand_first_mention("NONAME moved", _FACTS) == "NONAME moved"

def test_expand_first_mention_leaves_unknown_text_untouched():
    assert expand_first_mention("nothing to see here", _FACTS) == "nothing to see here"

def test_expand_first_mention_handles_empty_text():
    assert expand_first_mention("", _FACTS) == ""
    assert expand_first_mention(None, _FACTS) == ""

def test_single_char_symbols_need_a_price_cue():
    facts = {"A": TickerFacts("A", "Agilent Technologies", "Healthcare"),
             "T": TickerFacts("T", "AT&T", "Communication Services")}
    # sentence-initial "A" is the highest-frequency false positive
    assert find_mentions("A credible US foundry alternative", facts) == []
    assert find_mentions("T said little", facts) == []
    # a price cue still lets a real 1-char mention through
    assert [t for _, _, t in find_mentions("A +12% on the week", facts)] == ["A"]

# --- Regression over the real corpus ---------------------------------------
# The invented-sentence tests above cannot catch a stoplist that was written
# from imagination. reports/ and cache/ are git-ignored, so this skips on a
# fresh clone rather than silently passing.
_ROOT = Path(__file__).resolve().parents[1]
_REAL_BRIEF = _ROOT / "reports" / "brief-2026-08-11.json"
_REAL_CACHE = _ROOT / "cache"

def _real_brief_text(brief) -> str:
    parts = [brief.get("executive_summary") or "", brief.get("challenge") or "",
             brief.get("what_im_missing") or ""]
    for i in brief.get("items") or []:
        parts += [i.get(k) or "" for k in
                  ("title", "thesis", "evidence", "why_it_matters",
                   "portfolio_relevance")]
    parts += [w or "" for w in brief.get("watchlist") or []]
    return "\n".join(parts)

@pytest.mark.skipif(
    not (_REAL_BRIEF.exists() and (_REAL_CACHE / "sectors.json").exists()),
    reason="needs the git-ignored real brief and ticker cache")
def test_find_mentions_on_real_brief_has_no_english_word_false_positives():
    facts = load_cache_facts(_REAL_CACHE)
    text = _real_brief_text(json.loads(_REAL_BRIEF.read_text(encoding="utf-8")))
    found = {t for _, _, t in find_mentions(text, facts)}
    # Observed false positives: "A credible…", "PERSONAL GAP:", "actually LOW".
    assert {"A", "GAP", "LOW"} & found == set()
    # …without over-correcting: genuine mentions still annotate.
    assert {"MU", "WDC", "LITE", "NVDA", "PBF"} <= found

@pytest.mark.skipif(not (_ROOT / "config" / "universe.txt").exists(),
                    reason="needs config/universe.txt")
def test_common_word_stoplist_has_no_dead_entries():
    """Entries that can never match disguise an unmaintained list."""
    from vantage.universe import load_universe
    universe = set(load_universe(_ROOT / "config" / "universe.txt"))
    # PLAY is a documented exception: a real listed symbol not in this
    # universe today, kept because "a pure AI PLAY" is high-frequency prose.
    assert (COMMON_WORD_TICKERS - universe) == {"PLAY"}
