from pathlib import Path
from html import escape

def render_markdown(brief) -> str:
    out = [f"# Blind-Spot Radar — Weekly Brief ({brief.as_of})", ""]
    out += ["## Executive summary", brief.executive_summary, ""]
    out.append("## Notable items")
    for i in brief.items:
        out += [f"### {i.title}",
                f"**Thesis:** {i.thesis}",
                f"**Evidence:** {i.evidence}",
                f"**Why it matters:** {i.why_it_matters}",
                f"**Portfolio relevance:** {i.portfolio_relevance}"]
        if i.sources:
            out.append("**Sources:** " + ", ".join(i.sources))
        out.append("")
    out += ["## Challenge & coaching", brief.challenge, ""]
    out += ["## What I might be missing", brief.what_im_missing, ""]
    out += ["## Watchlist", ", ".join(brief.watchlist) or "—", ""]
    out += ["---", f"_{brief.disclaimer}_"]
    return "\n".join(out)

def _safe_link(url):
    es = escape(url)
    if url.startswith(("http://", "https://")):
        return f'<a href="{es}">{es}</a>'
    return es

def render_html(brief) -> str:
    def p(s): return f"<p>{escape(str(s))}</p>"
    parts = ['<!DOCTYPE html>',
             '<html><head><meta charset="utf-8"></head><body>',
             f"<h1>Blind-Spot Radar — Weekly Brief ({escape(brief.as_of)})</h1>",
             "<h2>Executive summary</h2>", p(brief.executive_summary),
             "<h2>Notable items</h2>"]
    for i in brief.items:
        parts.append(f"<h3>{escape(i.title)}</h3>")
        parts.append(p(f"Thesis: {i.thesis}"))
        parts.append(p(f"Evidence: {i.evidence}"))
        parts.append(p(f"Why it matters: {i.why_it_matters}"))
        parts.append(p(f"Portfolio relevance: {i.portfolio_relevance}"))
        if i.sources:
            links = " ".join(_safe_link(s) for s in i.sources)
            parts.append(f"<p>Sources: {links}</p>")
    parts += ["<h2>Challenge &amp; coaching</h2>", p(brief.challenge),
              "<h2>What I might be missing</h2>", p(brief.what_im_missing),
              "<h2>Watchlist</h2>", p(", ".join(brief.watchlist) or "—"),
              "<hr>", f"<p><em>{escape(brief.disclaimer)}</em></p>",
              "</body></html>"]
    return "\n".join(parts)

def save_markdown(brief, reports_dir) -> Path:
    path = Path(reports_dir) / f"brief-{brief.as_of}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(brief), encoding="utf-8")
    return path
