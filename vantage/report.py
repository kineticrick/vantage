import json
from pathlib import Path
from html import escape
from vantage.tickers import expand_first_mention

def _ex(text, facts, seen):
    """Expand ticker mentions in one field, or pass the text through untouched."""
    if not facts:
        return str(text)
    return expand_first_mention(str(text), facts, seen)

def render_markdown(brief, facts=None) -> str:
    out = [f"# Blind-Spot Radar — Weekly Brief ({brief.as_of})", ""]
    out += ["## Executive summary",
            _ex(brief.executive_summary, facts, set()), ""]
    if brief.trajectory_read:
        out += ["## Trajectory read",
                _ex(brief.trajectory_read, facts, set()), ""]
    out.append("## Notable items")
    for i in brief.items:
        seen = set()  # one item = one section, so names don't repeat per field
        out += [f"### {i.title}",
                f"**Thesis:** {_ex(i.thesis, facts, seen)}",
                f"**Evidence:** {_ex(i.evidence, facts, seen)}",
                f"**Why it matters:** {_ex(i.why_it_matters, facts, seen)}",
                f"**Portfolio relevance:** {_ex(i.portfolio_relevance, facts, seen)}"]
        if i.sources:
            out.append("**Sources:** " + ", ".join(i.sources))
        out.append("")
    out += ["## Challenge & coaching", _ex(brief.challenge, facts, set()), ""]
    out += ["## What I might be missing", _ex(brief.what_im_missing, facts, set()), ""]
    wl_seen = set()
    out += ["## Watchlist",
            ", ".join(_ex(w, facts, wl_seen) for w in brief.watchlist) or "—", ""]
    out += ["---", f"_{brief.disclaimer}_"]
    return "\n".join(out)

def _safe_link(url):
    es = escape(url)
    if url.startswith(("http://", "https://")):
        return f'<a href="{es}">{es}</a>'
    return es

def render_html(brief, facts=None) -> str:
    def p(s): return f"<p>{escape(str(s))}</p>"
    parts = ['<!DOCTYPE html>',
             '<html><head><meta charset="utf-8"></head><body>',
             f"<h1>Blind-Spot Radar — Weekly Brief ({escape(brief.as_of)})</h1>",
             "<h2>Executive summary</h2>",
             p(_ex(brief.executive_summary, facts, set()))]
    if brief.trajectory_read:
        parts += ["<h2>Trajectory read</h2>",
                  p(_ex(brief.trajectory_read, facts, set()))]
    parts.append("<h2>Notable items</h2>")
    for i in brief.items:
        seen = set()
        parts.append(f"<h3>{escape(i.title)}</h3>")
        parts.append(p(f"Thesis: {_ex(i.thesis, facts, seen)}"))
        parts.append(p(f"Evidence: {_ex(i.evidence, facts, seen)}"))
        parts.append(p(f"Why it matters: {_ex(i.why_it_matters, facts, seen)}"))
        parts.append(p(f"Portfolio relevance: {_ex(i.portfolio_relevance, facts, seen)}"))
        if i.sources:
            links = " ".join(_safe_link(s) for s in i.sources)
            parts.append(f"<p>Sources: {links}</p>")
    wl_seen = set()
    parts += ["<h2>Challenge &amp; coaching</h2>", p(_ex(brief.challenge, facts, set())),
              "<h2>What I might be missing</h2>", p(_ex(brief.what_im_missing, facts, set())),
              "<h2>Watchlist</h2>",
              p(", ".join(_ex(w, facts, wl_seen) for w in brief.watchlist) or "—"),
              "<hr>", f"<p><em>{escape(brief.disclaimer)}</em></p>",
              "</body></html>"]
    return "\n".join(parts)

def save_markdown(brief, reports_dir, facts=None) -> Path:
    path = Path(reports_dir) / f"brief-{brief.as_of}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(brief, facts), encoding="utf-8")
    return path

def save_html(brief, reports_dir, facts=None) -> Path:
    path = Path(reports_dir) / f"brief-{brief.as_of}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(brief, facts), encoding="utf-8")
    return path

def save_brief_json(brief, reports_dir) -> Path:
    # Persist the structured Brief so any report can be re-rendered later.
    path = Path(reports_dir) / f"brief-{brief.as_of}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(brief.to_dict(), indent=2), encoding="utf-8")
    return path

def save_report(brief, reports_dir, facts=None) -> Path:
    """Write the brief as Markdown, HTML, and JSON. Return the Markdown path.

    Markdown and HTML get inline ticker expansion; the JSON stays raw so the
    web layer can apply its own (tooltip) treatment.
    """
    md_path = save_markdown(brief, reports_dir, facts)
    save_html(brief, reports_dir, facts)
    save_brief_json(brief, reports_dir)
    return md_path
