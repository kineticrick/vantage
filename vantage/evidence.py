"""What has actually been tested about this market universe.

The analyst finds some ideas compelling that the data does not support — most
sharply, that a stock's returns "accelerating" says anything useful about its
future. The findings live in docs/, which the analyst never reads. This carries
them into the prompt so a refuted idea is not rediscovered every week.

Hand-maintained: append an entry to config/evidence.yaml after each study.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

VERDICTS = ("refuted", "supported", "inconclusive")
REQUIRED_KEYS = ("id", "claim", "verdict", "tested", "evidence", "implication",
                 "finding")


@dataclass
class Claim:
    id: str
    claim: str
    verdict: str
    tested: str
    evidence: str
    implication: str
    finding: str
    universe: str | None = None


@dataclass
class Evidence:
    universe: str = ""
    limits: list = field(default_factory=list)
    claims: list = field(default_factory=list)

    def by_verdict(self, verdict) -> list:
        return [c for c in self.claims if c.verdict == verdict]

    def render(self) -> str:
        """The block injected into analyst prompts. Empty register -> ''."""
        if not self.claims:
            return ""
        out = ["=== Evidence register — claims tested against this universe ==="]
        if self.universe:
            out.append(f"Universe: {_flat(self.universe)}")
        if self.limits:
            out.append("Limits applying to every claim below:")
            out += [f"  - {_flat(x)}" for x in self.limits]
        for c in self.claims:
            out.append("")
            out.append(f"[{c.verdict.upper()}] {_flat(c.claim)}  (tested {c.tested})")
            if c.universe:
                out.append(f"  Universe: {_flat(c.universe)}")
            out.append(f"  Evidence: {_flat(c.evidence)}")
            out.append(f"  Implication: {_flat(c.implication)}")
            out.append(f"  Source: {c.finding}")
        return "\n".join(out)


def _flat(text) -> str:
    """YAML block scalars carry newlines; prompts read better on one line."""
    return " ".join(str(text).split())


def load_evidence(config_dir) -> Evidence:
    """Read config/evidence.yaml. Never raises; degrades to an empty register."""
    path = Path(config_dir) / "evidence.yaml"
    if not path.exists():
        return Evidence()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        # Deliberately unconditional: the contract above is unconditional, and
        # both callers lean on it — chat.py builds a Conversation unguarded, and
        # run_weekly catches the analyst wholesale, so anything escaping here
        # costs the user their brief. A cp1252 em dash in this hand-edited,
        # dash-heavy file raises UnicodeDecodeError, which is a ValueError and
        # slipped past the previous (yaml.YAMLError, OSError) tuple.
        logger.warning("evidence.yaml unreadable (%s); continuing without it", e)
        return Evidence()
    if not isinstance(raw, dict):
        return Evidence()

    entries = raw.get("claims")
    claims = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            logger.warning("evidence claim entry %r is not a mapping; skipped",
                           entry)
            continue
        missing = [k for k in REQUIRED_KEYS if not entry.get(k)]
        if missing:
            # One malformed entry must not silence the whole register.
            logger.warning("evidence claim %r missing %s; skipped",
                           entry.get("id", "?"), ", ".join(missing))
            continue
        verdict = str(entry["verdict"])
        if verdict not in VERDICTS:
            # §5: an unknown verdict is not dropped or normalized — it loads
            # and renders verbatim, but this makes a hand-edit that never ran
            # the tests visible in the logs.
            logger.warning("evidence claim %r has unknown verdict %r "
                           "(expected one of %s); loading verbatim",
                           entry.get("id", "?"), verdict, VERDICTS)
        claims.append(Claim(
            id=str(entry["id"]), claim=str(entry["claim"]),
            verdict=verdict, tested=str(entry["tested"]),
            evidence=str(entry["evidence"]), implication=str(entry["implication"]),
            finding=str(entry["finding"]),
            # Optional, but declared str | None, and a hand-edited YAML list
            # here would otherwise render as a Python repr into the prompt.
            universe=str(entry["universe"]) if entry.get("universe") else None))

    limits = raw.get("limits")
    top_universe = raw.get("universe")
    return Evidence(universe=str(top_universe) if top_universe else "",
                    limits=[str(x) for x in limits] if isinstance(limits, list) else [],
                    claims=claims)
