import json

from vantage.evidence import load_evidence
from vantage.persona import ANALYST_PERSONA

DISCLAIMER = ("This is an automated research aid, not financial advice. "
              "Verify independently before making any investment decision.")

_JSON_OUTPUT = """Return your final answer as a single JSON object inside a ```json code block with
exactly these keys:
{
  "executive_summary": str,
  "items": [{"title": str, "thesis": str, "evidence": str, "sources": [str],
             "why_it_matters": str, "portfolio_relevance": str}],
  "watchlist": [str],
  "challenge": str,
  "what_im_missing": str
}
"""

_INSTRUCTIONS = ANALYST_PERSONA + "\n\n" + _JSON_OUTPUT

def build_prompt(signal_set, portfolio_context, interests, evidence=None) -> str:
    sig_lines = []
    for s in signal_set.signals:
        sig_lines.append(
            f"- {s.ticker} [{s.signal_type}] value={s.value:.2f} sector={s.sector} "
            f"metrics={ {k: round(v, 3) for k, v in s.metrics.items()} }")
    sectors = ", ".join(f"{k} {v:+.1%}" for k, v in
                        sorted(signal_set.sector_momentum.items(),
                               key=lambda kv: kv[1], reverse=True))
    block = evidence.render() if evidence is not None else ""
    return (
        _INSTRUCTIONS
        + f"\n\n=== As of: {signal_set.as_of} ===\n"
        + "\n=== Quantitative signals ===\n" + "\n".join(sig_lines)
        + "\n\n=== Sector momentum (mean 12m return) ===\n" + sectors
        + "\n\n=== User portfolio ===\n" + portfolio_context.summary_text()
        + (f"\n\n{block}" if block else "")
        + "\n\n=== User interest overlay ===\n" + json.dumps(interests, indent=2)
    )

def parse_brief(response_text, as_of):
    from vantage.models import Brief, BriefItem
    text = response_text
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Analyst response contained no JSON object")
    payload = json.loads(text[start:end + 1])
    items = [BriefItem(title=i.get("title", ""), thesis=i.get("thesis", ""),
                       evidence=i.get("evidence", ""), sources=i.get("sources", []),
                       why_it_matters=i.get("why_it_matters", ""),
                       portfolio_relevance=i.get("portfolio_relevance", ""))
             for i in payload.get("items", [])]
    return Brief(as_of=as_of,
                 executive_summary=payload.get("executive_summary", ""),
                 items=items, watchlist=payload.get("watchlist", []),
                 challenge=payload.get("challenge", ""),
                 what_im_missing=payload.get("what_im_missing", ""),
                 disclaimer=DISCLAIMER)

def generate_brief(signal_set, portfolio_context, interests, settings,
                   _client=None, _evidence=None):
    import anthropic
    client = _client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
    # Loaded here rather than passed in, so run_weekly's injection seam is
    # untouched and the chat and weekly analysts read the same register.
    evidence = _evidence if _evidence is not None else load_evidence(settings.config_dir)
    prompt = build_prompt(signal_set, portfolio_context, interests, evidence)
    with client.messages.stream(
        model=settings.model,
        max_tokens=64000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        tools=[{"type": "web_search_20260209", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        msg = stream.get_final_message()
    text = "".join(getattr(b, "text", "") or "" for b in msg.content if getattr(b, "type", None) == "text")
    return parse_brief(text, as_of=signal_set.as_of)
