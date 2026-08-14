from pathlib import Path
import yaml
from vantage.evidence import VERDICTS, REQUIRED_KEYS, load_evidence

CONFIG = Path(__file__).resolve().parents[1] / "config"
REPO = Path(__file__).resolve().parents[1]

def test_shipped_register_parses_and_has_claims():
    ev = load_evidence(CONFIG)
    assert len(ev.claims) >= 5
    assert ev.universe and ev.limits

def test_every_claim_has_every_required_key():
    raw = yaml.safe_load((CONFIG / "evidence.yaml").read_text(encoding="utf-8"))
    for entry in raw["claims"]:
        missing = [k for k in REQUIRED_KEYS if not entry.get(k)]
        assert not missing, f"{entry.get('id')} missing {missing}"

def test_every_verdict_is_in_the_vocabulary():
    for c in load_evidence(CONFIG).claims:
        assert c.verdict in VERDICTS, f"{c.id} has verdict {c.verdict!r}"

def test_claim_ids_are_unique():
    ids = [c.id for c in load_evidence(CONFIG).claims]
    assert len(ids) == len(set(ids))

def test_every_cited_finding_exists_on_disk():
    # Without this the register accumulates citations to evidence nobody can
    # open, which is worse than having no register.
    for c in load_evidence(CONFIG).claims:
        assert (REPO / c.finding).exists(), f"{c.id} cites missing {c.finding}"

def test_register_records_at_least_one_supported_claim():
    # A register of nothing but refutations teaches the analyst that
    # measurement only ever destroys ideas. See the design spec, §3.
    assert load_evidence(CONFIG).by_verdict("supported")

def test_the_four_refuted_claims_are_present():
    ids = {c.id for c in load_evidence(CONFIG).by_verdict("refuted")}
    assert {"acceleration-beats-12m",
            "fade-flag-predicts-underperformance",
            "trajectory-discriminates-within-leaders",
            "sector-breadth-predicts-sector-returns"} <= ids
