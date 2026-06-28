import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

@dataclass
class Signal:
    ticker: str
    signal_type: str
    value: float
    rank: int
    sector: str | None = None
    metrics: dict = field(default_factory=dict)

@dataclass
class SignalSet:
    as_of: str
    signals: list
    sector_momentum: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of,
            "signals": [asdict(s) for s in self.signals],
            "sector_momentum": self.sector_momentum,
        }

    @staticmethod
    def from_dict(d: dict) -> "SignalSet":
        return SignalSet(
            as_of=d["as_of"],
            signals=[Signal(**s) for s in d["signals"]],
            sector_momentum=d.get("sector_momentum", {}),
        )

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @staticmethod
    def load(path) -> "SignalSet":
        return SignalSet.from_dict(json.loads(Path(path).read_text()))

@dataclass
class Holding:
    ticker: str
    name: str
    shares: float
    cost_basis: float
    current_value: float | None = None
    pct_of_portfolio: float | None = None
    sector: str | None = None
    asset_type: str | None = None

@dataclass
class PortfolioContext:
    available: bool
    holdings: list = field(default_factory=list)
    sector_concentration: dict = field(default_factory=dict)
    asset_type_concentration: dict = field(default_factory=dict)
    revealed_interests: list = field(default_factory=list)
    note: str = ""

    def summary_text(self) -> str:
        if not self.available:
            return f"Portfolio data unavailable: {self.note}"
        lines = ["Current holdings:"]
        for h in self.holdings:
            pct = f"{h.pct_of_portfolio:.0%}" if h.pct_of_portfolio is not None else "?"
            lines.append(f"  {h.ticker} ({h.name}) — {pct} of portfolio, sector {h.sector}")
        lines.append("Sector concentration: " + ", ".join(
            f"{k} {v:.0%}" for k, v in self.sector_concentration.items()))
        lines.append("Asset-type concentration: " + ", ".join(
            f"{k} {v:.0%}" for k, v in self.asset_type_concentration.items()))
        lines.append("Revealed interests (where capital has gone): " +
                     ", ".join(self.revealed_interests))
        return "\n".join(lines)

@dataclass
class BriefItem:
    title: str
    thesis: str
    evidence: str
    sources: list = field(default_factory=list)
    why_it_matters: str = ""
    portfolio_relevance: str = ""

@dataclass
class Brief:
    as_of: str
    executive_summary: str
    items: list
    watchlist: list
    challenge: str
    what_im_missing: str
    disclaimer: str

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d: dict) -> "Brief":
        return Brief(
            as_of=d["as_of"],
            executive_summary=d["executive_summary"],
            items=[BriefItem(**i) for i in d["items"]],
            watchlist=d.get("watchlist", []),
            challenge=d.get("challenge", ""),
            what_im_missing=d.get("what_im_missing", ""),
            disclaimer=d.get("disclaimer", ""),
        )
