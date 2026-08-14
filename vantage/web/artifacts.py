import json
from pathlib import Path
from vantage.models import SignalSet, Brief
from vantage.tickers import TICKER_RE, is_common_word, resolve
from vantage.termstructure import term_structure

def latest_signals(data_dir):
    files = sorted(Path(data_dir).glob("signals-*.json"))
    return SignalSet.load(files[-1]) if files else None

def list_briefs(reports_dir):
    out = []
    for p in sorted(Path(reports_dir).glob("brief-*.json"), reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        out.append({"as_of": d.get("as_of"),
                    "summary": (d.get("executive_summary") or "")[:280]})
    return out

def load_brief(reports_dir, as_of):
    p = Path(reports_dir) / f"brief-{as_of}.json"
    return Brief.from_dict(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else None

def read_brief_html(reports_dir, as_of):
    p = Path(reports_dir) / f"brief-{as_of}.html"
    return p.read_text(encoding="utf-8") if p.exists() else None

def signals_payload(signal_set) -> dict:
    """The signals artifact plus rendered term-structure cells per signal.

    The display strings are produced server-side so the browser never formats
    a percentage — one formatter, one appearance, everywhere.
    """
    if signal_set is None:
        return {"as_of": None, "signals": [], "sector_momentum": {}}
    payload = signal_set.to_dict()
    for raw, sig in zip(payload["signals"], signal_set.signals):
        raw["term_structure"] = term_structure(sig.metrics)
    return payload

def build_overview(signal_set, portfolio, latest_brief):
    leaders, spikes = [], []
    if signal_set:
        for s in signal_set.signals:
            entry = {"ticker": s.ticker, "value": s.value, "sector": s.sector,
                     "name": s.name, "term_structure": term_structure(s.metrics)}
            if s.signal_type == "ret_12m_leader":
                leaders.append(entry)
            elif s.signal_type == "volume_spike":
                spikes.append(entry)
    mom = sorted((signal_set.sector_momentum.items() if signal_set else []),
                 key=lambda kv: kv[1], reverse=True)
    if portfolio is not None and portfolio.available:
        top = sorted(portfolio.holdings, key=lambda h: h.pct_of_portfolio or 0,
                     reverse=True)[:8]
        pf = {"available": True, "holdings_count": len(portfolio.holdings),
              "top_positions": [{"ticker": h.ticker, "name": h.name,
                                 "pct": h.pct_of_portfolio, "sector": h.sector}
                                for h in top],
              "sector_concentration": portfolio.sector_concentration}
    else:
        pf = {"available": False, "note": portfolio.note if portfolio else ""}
    return {
        "signals_as_of": signal_set.as_of if signal_set else None,
        "top_leaders": leaders[:5],
        "top_volume_spikes": spikes[:5],
        "sector_momentum_top": [{"sector": k, "value": v} for k, v in mom[:5]],
        "sector_momentum_bottom": [{"sector": k, "value": v} for k, v in mom[-5:][::-1]],
        "portfolio": pf,
        "watchlist": latest_brief.watchlist if latest_brief else [],
        "latest_brief": ({"as_of": latest_brief.as_of,
                          "executive_summary": latest_brief.executive_summary}
                         if latest_brief else None),
    }


def _brief_text(brief) -> str:
    """All prose in a brief, concatenated — used to scope the ticker map."""
    parts = [brief.executive_summary or "", brief.trajectory_read or "",
             brief.challenge or "", brief.what_im_missing or "",
             " ".join(brief.watchlist or [])]
    for i in brief.items:
        parts += [i.title or "", i.thesis or "", i.evidence or "",
                  i.why_it_matters or "", i.portfolio_relevance or ""]
    return " ".join(parts)


def relevant_ticker_facts(facts, signal_set, portfolio, brief) -> dict:
    """Facts for tickers actually on screen — not the whole 900+ universe.

    Narrow scope is the primary defense against annotating English words that
    happen to be tickers: a symbol the user is not looking at is never a
    candidate. The `common_word` flag carries the stoplist verdict to the
    frontend so the JS applies the same rule instead of keeping its own list.
    """
    keys = set()
    if signal_set:
        keys |= {s.ticker for s in signal_set.signals}
    if portfolio is not None and getattr(portfolio, "available", False):
        keys |= {h.ticker for h in portfolio.holdings if h.ticker}
    if brief is not None:
        keys |= {m.group(0) for m in TICKER_RE.finditer(_brief_text(brief))
                 if m.group(0) in facts}
    out = {}
    for t in sorted(keys):
        f = resolve(t, facts)
        out[t] = {"name": f.name, "sector": f.sector,
                  "common_word": is_common_word(t)}
    return out
