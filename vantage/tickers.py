"""Ticker identity: what a symbol's company name and sector are.

Single source of truth for turning a bare symbol into something a human
recognizes. Facts come from two places, highest priority first: the user's
Wake holdings (authoritative for what they own, and the only source that
names their ETFs) and the yfinance-derived cache written by data_ingest.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TickerFacts:
    ticker: str
    name: str | None = None
    sector: str | None = None

    def subtitle(self, sep: str = " · ") -> str:
        """Human label from whatever is known; empty string if nothing is."""
        return sep.join(p for p in (self.name, self.sector) if p)


def _cache_path(cache_dir) -> Path:
    # Filename kept as sectors.json so the existing cache stays valid.
    return Path(cache_dir) / "sectors.json"


def load_cache_facts(cache_dir) -> dict:
    p = _cache_path(cache_dir)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    if not isinstance(raw, dict):
        # Valid JSON but not an object (e.g. "[]" or "null") is still corrupt
        # from this cache's perspective.
        return {}
    return {t: TickerFacts(ticker=t, name=e.get("name"), sector=e.get("sector"))
            for t, e in raw.items() if isinstance(e, dict)}


def load_facts(cache_dir, portfolio=None) -> dict:
    """Cache facts, overlaid with portfolio holdings where those know better."""
    facts = load_cache_facts(cache_dir)
    if portfolio is not None and getattr(portfolio, "available", False):
        for h in portfolio.holdings:
            if not h.ticker:
                continue
            cached = facts.get(h.ticker)
            facts[h.ticker] = TickerFacts(
                ticker=h.ticker,
                name=h.name or (cached.name if cached else None),
                sector=h.sector or (cached.sector if cached else None),
            )
    return facts


def resolve(ticker, facts) -> TickerFacts:
    """Never raises — an unknown ticker resolves to bare facts."""
    return facts.get(ticker) or TickerFacts(ticker=ticker)


# --- Prose detection -------------------------------------------------------
# Tickers that are also ordinary English words. Annotating these on sight
# would light up normal prose ("it", "all", "on"), so they are skipped unless
# the surrounding text carries a price/percent cue. Biased toward
# under-annotating: a missed tooltip is invisible, a wrong one is a bug.
#
# Derived from the real universe, not from imagination: every entry below
# except PLAY is present in config/universe.txt (915 symbols, == cache/
# sectors.json), intersected with /usr/share/dict/american-english and then
# hand-judged. Since TICKER_RE only matches all-caps tokens, the risk is not
# "gap" in ordinary lowercase prose but a word SHOUTED for emphasis or used in
# a heading — which is exactly how the analyst writes ("FLAG + PERSONAL GAP",
# "ratios are actually LOW"). Symbols that are dictionary words but implausible
# as all-caps prose are deliberately left out so genuine mentions still
# annotate: ONTO, LITE, META, DELL, MU, COIN, APP, ALLY, KEYS, FANG, UPS, TAP.
# PLAY (Dave & Buster's) is the one entry not currently in the universe; it is
# kept because "a pure AI PLAY" is high-frequency prose and the universe is a
# user-editable config file.
# Keep this a literal: it must be deterministic and identical for consumers
# that have no cache on disk.
COMMON_WORD_TICKERS = frozenset({
    # articles, pronouns, verbs, prepositions
    "A", "ALL", "AM", "AN", "ARE", "HAS", "IT", "ON", "SO",
    # nouns/adjectives that get capitalized for emphasis or in headings
    "ARM", "BALL", "BILL", "CAR", "CART", "CAT", "COST", "DASH", "FAST",
    "FIVE", "FIX", "FLEX", "FOUR", "GAP", "GEN", "HOOD", "ICE", "KEY", "LOW",
    "NOW", "PATH", "PLAY", "POST", "SHOP", "TECH", "WELL",
    # financial abbreviations that collide with a symbol
    "AMT", "COO", "MTD", "PEG", "SAM",
})

# A symbol: 1-5 uppercase alphanumerics, optionally a class suffix (BRK-B).
TICKER_RE = re.compile(r"\b[A-Z][A-Z0-9]{0,4}(?:-[A-Z])?\b")

# A price/percent cue immediately after a symbol: "+32%", "$214", "is 12".
_CUE_RE = re.compile(r"^\s*(?:is\s+|at\s+)?[+\-]?\$?\d")


def is_common_word(ticker) -> bool:
    return str(ticker).upper() in COMMON_WORD_TICKERS


def _has_price_cue(text, end) -> bool:
    return bool(_CUE_RE.match(text[end:end + 12]))


def _needs_price_cue(ticker) -> bool:
    """Symbols that must be corroborated by a nearby price/percent.

    Every 1-character symbol qualifies unconditionally: a lone capital letter
    is far more often a sentence-initial "A", an initial, or a list marker than
    a ticker, and no 1-char symbol is safe bare. Mirrored in app.js.
    """
    return len(str(ticker)) == 1 or is_common_word(ticker)


def find_mentions(text, facts) -> list:
    """Spans of ticker mentions we are confident about, left to right."""
    text = text or ""
    out = []
    for m in TICKER_RE.finditer(text):
        t = m.group(0)
        if t not in facts:
            continue
        if _needs_price_cue(t) and not _has_price_cue(text, m.end()):
            continue
        out.append((m.start(), m.end(), t))
    return out


def expand_first_mention(text, facts, seen=None) -> str:
    """Append "(Name, Sector)" after the first mention of each ticker.

    `seen` is shared across calls that belong to the same section, so a name
    is not repeated within one section but is reintroduced in the next.
    """
    text = text or ""
    seen = seen if seen is not None else set()
    parts, last = [], 0
    for start, end, t in find_mentions(text, facts):
        if t in seen:
            continue
        detail = resolve(t, facts).subtitle(sep=", ")
        if not detail:
            continue
        seen.add(t)
        parts.append(text[last:end])
        parts.append(f" ({detail})")
        last = end
    parts.append(text[last:])
    return "".join(parts)
