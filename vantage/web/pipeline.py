import logging
from vantage.universe import load_universe
from vantage.data_ingest import fetch_market_data
from vantage.screener import run_screener
from vantage.portfolio_context import load_portfolio_context

logger = logging.getLogger(__name__)

def run_refresh(settings, _market_data_fn=None, _portfolio_fn=None):
    md_fn = _market_data_fn or (lambda tickers, cache_dir:
                                fetch_market_data(tickers, cache_dir))
    pf_fn = _portfolio_fn or (lambda pa_path: load_portfolio_context(pa_path))
    try:
        yield {"type": "progress", "stage": "fetching market data"}
        tickers = load_universe(settings.config_dir / "universe.txt")
        market_data = md_fn(tickers, settings.cache_dir)
        yield {"type": "progress", "stage": "screening"}
        signal_set = run_screener(market_data)
        signal_set.save(settings.data_dir / f"signals-{signal_set.as_of}.json")
        yield {"type": "progress", "stage": "loading portfolio"}
        pf_fn(settings.portfolio_analysis_path)
        yield {"type": "done", "as_of": signal_set.as_of}
    except Exception as e:
        logger.warning("refresh failed: %s", e)
        yield {"type": "error", "message": str(e)}
