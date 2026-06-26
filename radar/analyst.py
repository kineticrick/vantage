import json

DISCLAIMER = ("This is an automated research aid, not financial advice. "
              "Verify independently before making any investment decision.")

_INSTRUCTIONS = """You are a sharp, candid investment research analyst and sparring partner.
You are given (1) deterministic quantitative market signals, (2) the user's real
portfolio and historical interests, and (3) the user's stated interest themes.

Your job, in order:
1. Detect EMERGING NARRATIVES: use web_search to find themes/sectors rising in the
   news around the top movers before they are mainstream. Cite sources (URLs).
2. Find NARRATIVE<->PRICE CONVERGENCE: where a rising narrative AND unusual price
   action point at the same sector/asset. Flag these most prominently.
3. Reason SECOND-ORDER / supply-chain: if X is booming, who are the non-obvious
   upstream/downstream beneficiaries the user may not be watching?
4. PERSONAL LENS (do not narrow the broad scan): connect movers to what the user
   holds, flag threats to their concentrations, and surface adjacents to themes
   they have repeatedly bought.
5. CHALLENGE & COACH: pressure-test the user's positioning and past decisions
   against the evidence — over-concentration, a thesis now undercut, a missed
   rotation, or a recurring behavioral pattern. State the counter-case they should
   have to answer. Be evidence-based and constructive, never contrarian for its own
   sake, and never fabricate confidence.

Be specific and grounded. Show evidence and cite sources. State uncertainty plainly.

Return your final answer as a single JSON object inside a ```json code block with
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

def build_prompt(signal_set, portfolio_context, interests) -> str:
    sig_lines = []
    for s in signal_set.signals:
        sig_lines.append(
            f"- {s.ticker} [{s.signal_type}] value={s.value:.2f} sector={s.sector} "
            f"metrics={ {k: round(v, 3) for k, v in s.metrics.items()} }")
    sectors = ", ".join(f"{k} {v:+.1%}" for k, v in
                        sorted(signal_set.sector_momentum.items(),
                               key=lambda kv: kv[1], reverse=True))
    return (
        _INSTRUCTIONS
        + f"\n\n=== As of: {signal_set.as_of} ===\n"
        + "\n=== Quantitative signals ===\n" + "\n".join(sig_lines)
        + "\n\n=== Sector momentum (mean 12m return) ===\n" + sectors
        + "\n\n=== User portfolio ===\n" + portfolio_context.summary_text()
        + "\n\n=== User interest overlay ===\n" + json.dumps(interests, indent=2)
    )

def parse_brief(response_text, as_of):
    from radar.models import Brief, BriefItem
    text = response_text
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
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

def generate_brief(signal_set, portfolio_context, interests, settings, _client=None):
    import anthropic
    client = _client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
    prompt = build_prompt(signal_set, portfolio_context, interests)
    with client.messages.stream(
        model=settings.model,
        max_tokens=64000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        tools=[{"type": "web_search_20260209", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        msg = stream.get_final_message()
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    return parse_brief(text, as_of=signal_set.as_of)
