from vantage.data_ingest import fetch_market_data
from vantage.momentum import drawdown_from_high
from vantage.screener import _WINDOWS, _trailing_return, _volume_ratio, run_screener
from vantage.termstructure import term_structure
from vantage.universe import load_universe

def get_ticker_metrics(ticker, settings, _downloader=None, _info_fn=None) -> dict:
    ticker = ticker.upper().strip()
    try:
        md = fetch_market_data([ticker], cache_dir=settings.cache_dir,
                               _downloader=_downloader, _info_fn=_info_fn)
        prices = md.prices.get(ticker)
        if prices is None or len(prices) == 0:
            return {"ticker": ticker, "error": "no price data found"}
        out = {"ticker": ticker, "name": md.names.get(ticker),
               "sector": md.sectors.get(ticker, "Unknown")}
        for name, lb in _WINDOWS.items():
            out[name] = _trailing_return(prices, lb)
        vol = md.volumes.get(ticker)
        out["volume_ratio"] = _volume_ratio(vol) if vol is not None else None
        # Omitted rather than set to None when unavailable — the same rule
        # screener.py applies to this key (spec 2.1), so the one number both
        # units produce is shaped the same either way it is fetched.
        dd = drawdown_from_high(prices)
        if dd is not None:
            out["drawdown_from_high"] = dd
        return out
    except Exception as e:
        return {"ticker": ticker, "error": f"metrics failed: {e}"}

def run_screen(settings, return_leader_threshold=1.0, volume_spike_ratio=2.0,
               top_n=15, _market_data_fn=None) -> dict:
    try:
        tickers = load_universe(settings.config_dir / "universe.txt")
        md_fn = _market_data_fn or fetch_market_data
        md = md_fn(tickers, cache_dir=settings.cache_dir)
        ss = run_screener(md, top_n=top_n,
                          return_leader_threshold=return_leader_threshold,
                          volume_spike_ratio=volume_spike_ratio)
        leaders = [{"ticker": s.ticker, "ret_12m": round(s.value, 3),
                    "term_structure": term_structure(s.metrics)}
                   for s in ss.signals if s.signal_type == "ret_12m_leader"]
        spikes = [{"ticker": s.ticker, "volume_ratio": round(s.value, 2),
                   "term_structure": term_structure(s.metrics)}
                  for s in ss.signals if s.signal_type == "volume_spike"]
        momentum = {k: round(v, 3) for k, v in ss.sector_momentum.items()}
        return {"leaders": leaders, "volume_spikes": spikes, "sector_momentum": momentum}
    except Exception as e:
        return {"error": f"screen failed: {e}"}

TOOL_DEFINITIONS = [
    {
        "name": "get_ticker_metrics",
        "description": "Get a single ticker's trailing returns (1/3/6/12 month, "
                       "as fractions), its recent volume ratio, and "
                       "drawdown_from_high — how far below its trailing 52-week "
                       "high it now sits, as a negative fraction (omitted when "
                       "the price history is too short). Use for exact figures "
                       "on any ticker rather than guessing. These are "
                       "descriptive: this shape does not predict forward "
                       "returns (see the evidence register).",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Ticker symbol"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "run_screen",
        "description": "Re-run the market screen over the configured universe with "
                       "optional threshold overrides; returns the top 12-month return "
                       "leaders, volume spikes, and median sector momentum. Every "
                       "leader and spike carries a term_structure: the 1m/3m/6m/12m "
                       "trailing returns and the distance below the 52-week high, "
                       "each as {label, value, display} with display pre-formatted "
                       "for quoting. Descriptive only — nothing is ranked, sorted or "
                       "filtered on it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "return_leader_threshold": {"type": "number",
                    "description": "Min 12mo return (fraction) to count as a leader, e.g. 1.0 = +100%"},
                "volume_spike_ratio": {"type": "number",
                    "description": "Min volume-vs-average ratio to flag a spike, e.g. 2.0"},
                "top_n": {"type": "integer", "description": "Max signals to return"},
            },
        },
    },
]

CUSTOM_TOOL_NAMES = {"get_ticker_metrics", "run_screen"}

def dispatch(name, tool_input, settings) -> dict:
    if name == "get_ticker_metrics":
        return get_ticker_metrics(tool_input.get("ticker", ""), settings)
    if name == "run_screen":
        kwargs = {k: v for k, v in tool_input.items()
                  if k in ("return_leader_threshold", "volume_spike_ratio", "top_n")}
        return run_screen(settings, **kwargs)
    return {"error": f"unknown tool: {name}"}
