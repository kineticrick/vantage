from vantage.models import Brief, BriefItem
from vantage.report import (render_markdown, render_html, save_markdown,
                          save_html, save_brief_json, save_report)

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
    assert "Not financial advice" in html
    assert "Challenge" in html and "Watchlist" in html and "NVDA" in html
    assert "executive summary" in html.lower()

def test_render_html_escapes_and_sanitizes_links():
    b = _brief()
    b.items[0].title = "<script>alert(1)</script>"
    b.items[0].sources = ["javascript:alert(1)", "https://ok.com/a?b=1&c=2"]
    html = render_html(b)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert 'href="javascript:' not in html
    assert '<a href="https://ok.com' in html

def test_save_markdown_writes_dated_file(tmp_path):
    p = save_markdown(_brief(), tmp_path)
    assert p.exists() and p.name == "brief-2026-06-26.md"

def test_save_html_writes_dated_file(tmp_path):
    p = save_html(_brief(), tmp_path)
    assert p.exists() and p.name == "brief-2026-06-26.html"
    assert "<html" in p.read_text().lower() and "Memory boom" in p.read_text()

def test_save_brief_json_roundtrips(tmp_path):
    p = save_brief_json(_brief(), tmp_path)
    assert p.exists() and p.name == "brief-2026-06-26.json"
    import json
    restored = Brief.from_dict(json.loads(p.read_text()))
    assert restored.items[0].title == "Memory boom"
    assert restored.challenge == "You exited WDC too early."

def test_save_report_writes_all_three(tmp_path):
    md_path = save_report(_brief(), tmp_path)
    assert md_path.name == "brief-2026-06-26.md"
    for ext in ("md", "html", "json"):
        assert (tmp_path / f"brief-2026-06-26.{ext}").exists()
