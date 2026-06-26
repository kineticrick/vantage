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
    brief = an_fn(signal_set, portfolio, interests, s)

    path = save_markdown(brief, s.reports_dir)
    html = render_html(brief)
    subject = f"Blind-Spot Radar — Weekly Brief ({brief.as_of})"
    send = _send_fn or (lambda subject, html, st: send_email(subject, html, st))
    send(subject, html, s)
    return path

if __name__ == "__main__":
    out = run()
    print(f"Brief written to {out} and emailed.")
