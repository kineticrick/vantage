import logging
import yaml
from pathlib import Path
from radar.settings import load_settings
from radar.universe import load_universe
from radar.data_ingest import fetch_market_data
from radar.screener import run_screener
from radar.portfolio_context import load_portfolio_context
from radar.analyst import generate_brief
from radar.report import save_markdown, render_html
from radar.deliver import send_email

logger = logging.getLogger(__name__)


def _fallback_brief(signal_set, error):
    from radar.models import Brief
    from radar.analyst import DISCLAIMER
    leaders = ", ".join(s.ticker for s in signal_set.signals[:15]) or "none"
    return Brief(
        as_of=signal_set.as_of,
        executive_summary=("The AI analyst step failed this week; this is a fallback "
                           "brief built directly from the quantitative screen. "
                           f"Error: {error}"),
        items=[], watchlist=[], challenge="",
        what_im_missing=f"Top quantitative movers this week: {leaders}.",
        disclaimer=DISCLAIMER,
    )


def run(settings=None, _market_data_fn=None, _portfolio_fn=None,
        _analyst_fn=None, _send_fn=None) -> Path:
    s = settings or load_settings()
    tickers = load_universe(s.config_dir / "universe.txt")
    md_fn = _market_data_fn or (lambda tickers, cache_dir: fetch_market_data(tickers, cache_dir))
    market_data = md_fn(tickers, s.cache_dir)

    signal_set = run_screener(market_data)
    signal_set.save(s.data_dir / f"signals-{signal_set.as_of}.json")

    pf_fn = _portfolio_fn or (lambda pa_path: load_portfolio_context(pa_path))
    portfolio = pf_fn(s.portfolio_analysis_path)

    interests_path = s.config_dir / "interests.yaml"
    interests = yaml.safe_load(interests_path.read_text()) if interests_path.exists() else {}

    an_fn = _analyst_fn or (lambda ss, pc, it, st: generate_brief(ss, pc, it, st))
    try:
        brief = an_fn(signal_set, portfolio, interests, s)
    except Exception as e:
        logger.warning("Analyst step failed: %s — sending fallback brief", e)
        brief = _fallback_brief(signal_set, str(e))

    path = save_markdown(brief, s.reports_dir)
    html = render_html(brief)
    subject = f"Blind-Spot Radar — Weekly Brief ({brief.as_of})"
    send = _send_fn or (lambda subject, html, st: send_email(subject, html, st))
    send(subject, html, s)
    return path

if __name__ == "__main__":
    out = run()
    print(f"Brief written to {out} and emailed.")
