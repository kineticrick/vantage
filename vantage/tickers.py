"""Ticker identity: what a symbol's company name and sector are.

Single source of truth for turning a bare symbol into something a human
recognizes. Facts come from two places, highest priority first: the user's
Wake holdings (authoritative for what they own, and the only source that
names their ETFs) and the yfinance-derived cache written by data_ingest.
"""
import json
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
