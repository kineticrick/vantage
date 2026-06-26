from radar.models import Brief, BriefItem
from radar.report import render_markdown, render_html, save_markdown

def _brief():
    return Brief(as_of="2026-06-26", executive_summary="Big week.",
                 items=[BriefItem(title="Memory boom", thesis="AI demand",
                                  evidence="MU +140%", sources=["http://x"],
                                  why_it_matters="cycle", portfolio_relevance="you hold none")],
                 watchlist=["NVDA"], challenge="You exited WDC too early.",
                 what_im_missing="small caps", disclaimer="Not financial advice.")

def test_render_markdown_contains_sections():
    md = render_markdown(_brief())
    assert "# " in md and "Memory boom" in md
    assert "Challenge" in md and "WDC" in md
    assert "Watchlist" in md and "NVDA" in md
    assert "Not financial advice" in md

def test_render_html_is_html():
    html = render_html(_brief())
    assert "<html" in html.lower() and "Memory boom" in html

def test_save_markdown_writes_dated_file(tmp_path):
    p = save_markdown(_brief(), tmp_path)
    assert p.exists() and p.name == "brief-2026-06-26.md"
