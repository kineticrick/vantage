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

from vantage.tickers import TickerFacts

_FACTS = {"MU": TickerFacts("MU", "Micron Technology", "Technology"),
          "NVDA": TickerFacts("NVDA", "NVIDIA Corporation", "Technology"),
          "WDC": TickerFacts("WDC", "Western Digital", "Technology")}

def test_render_markdown_without_facts_is_unchanged():
    assert render_markdown(_brief()) == render_markdown(_brief(), facts=None)

def test_render_markdown_expands_first_mention():
    md = render_markdown(_brief(), facts=_FACTS)
    assert "MU (Micron Technology, Technology)" in md
    assert "WDC (Western Digital, Technology)" in md      # challenge section
    assert "NVDA (NVIDIA Corporation, Technology)" in md  # watchlist

def test_render_html_expands_and_still_escapes():
    from vantage.models import Brief, BriefItem
    b = Brief(as_of="2026-06-26", executive_summary="MU <script>x</script> up",
              items=[], watchlist=[], challenge="", what_im_missing="",
              disclaimer="d")
    html = render_html(b, facts=_FACTS)
    assert "MU (Micron Technology, Technology)" in html
    assert "<script>" not in html and "&lt;script&gt;" in html

def test_expansion_resets_between_sections():
    from vantage.models import Brief
    b = Brief(as_of="2026-06-26", executive_summary="MU leads",
              items=[], watchlist=[], challenge="MU again",
              what_im_missing="", disclaimer="d")
    md = render_markdown(b, facts=_FACTS)
    assert md.count("MU (Micron Technology, Technology)") == 2

def test_save_report_annotates_md_and_html_but_not_json(tmp_path):
    import json
    save_report(_brief(), tmp_path, facts=_FACTS)
    md = (tmp_path / "brief-2026-06-26.md").read_text(encoding="utf-8")
    html = (tmp_path / "brief-2026-06-26.html").read_text(encoding="utf-8")
    raw = json.loads((tmp_path / "brief-2026-06-26.json").read_text(encoding="utf-8"))
    assert "Micron Technology" in md and "Micron Technology" in html
    assert "Micron Technology" not in json.dumps(raw)

def test_rendering_does_not_mutate_the_brief():
    b = _brief()
    before = b.items[0].evidence
    render_markdown(b, facts=_FACTS)
    assert b.items[0].evidence == before
