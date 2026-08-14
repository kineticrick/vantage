import json
from dataclasses import dataclass, field
from pathlib import Path
import yaml
from vantage.evidence import load_evidence
from vantage.models import SignalSet, Brief, PortfolioContext
from vantage.portfolio_context import load_portfolio_context

def _newest(directory, pattern):
    files = sorted(Path(directory).glob(pattern))
    return files[-1] if files else None

@dataclass
class ChatContext:
    portfolio: object = None          # PortfolioContext | None
    signals: object = None            # SignalSet | None
    interests: dict = field(default_factory=dict)
    brief: object = None              # Brief | None
    evidence: object = None           # Evidence | None

    def render(self) -> str:
        parts = []
        if self.portfolio is not None and getattr(self.portfolio, "available", False):
            parts.append(self.portfolio.summary_text())
        else:
            note = getattr(self.portfolio, "note", "") if self.portfolio else ""
            parts.append(f"Portfolio: unavailable ({note}).")
        if self.signals is not None:
            leader_items = [f"{s.ticker}({s.value:.2f})" for s in self.signals.signals
                            if s.signal_type == "ret_12m_leader"]
            leaders = ", ".join(leader_items[:40])
            mom = ", ".join(f"{k} {v:+.0%}" for k, v in self.signals.sector_momentum.items())
            parts.append(f"Latest signals ({self.signals.as_of}): 12mo leaders: "
                         f"{leaders or 'none'}. Sector momentum: {mom or 'none'}.")
        else:
            parts.append("Latest signals: none saved yet (suggest running the weekly pipeline).")
        parts.append(f"Interest overlay: {json.dumps(self.interests) if self.interests else 'none set'}.")
        block = self.evidence.render() if self.evidence is not None else ""
        if block:
            parts.append(block)
        if self.brief is not None:
            titles = "; ".join(i.title for i in self.brief.items)
            parts.append(f"Latest brief ({self.brief.as_of}): {self.brief.executive_summary[:400]} "
                         f"Items: {titles}.")
        else:
            parts.append("Latest brief: none saved yet.")
        return "\n".join(parts)

def load_chat_context(settings, _portfolio_fn=None) -> ChatContext:
    pf = (_portfolio_fn or load_portfolio_context)
    try:
        portfolio = pf(settings.portfolio_analysis_path)
    except Exception as e:
        portfolio = PortfolioContext(available=False, note=str(e)[:200])

    signals = None
    sig_file = _newest(settings.data_dir, "signals-*.json")
    if sig_file:
        try:
            signals = SignalSet.load(sig_file)
        except Exception:
            signals = None

    interests = {}
    ipath = settings.config_dir / "interests.yaml"
    if ipath.exists():
        try:
            interests = yaml.safe_load(ipath.read_text()) or {}
        except Exception:
            interests = {}

    brief = None
    brief_file = _newest(settings.reports_dir, "brief-*.json")
    if brief_file:
        try:
            brief = Brief.from_dict(json.loads(brief_file.read_text()))
        except Exception:
            brief = None

    evidence = load_evidence(settings.config_dir)

    return ChatContext(portfolio=portfolio, signals=signals,
                       interests=interests, brief=brief, evidence=evidence)
