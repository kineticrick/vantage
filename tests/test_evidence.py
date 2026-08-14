import pytest
import yaml
from vantage.evidence import (VERDICTS, REQUIRED_KEYS, Claim, Evidence,
                              load_evidence)

_CLAIM = {
    "id": "acceleration-beats-12m",
    "claim": "Ranking by return acceleration beats ranking by 12-month return.",
    "verdict": "refuted",
    "tested": "2026-08-13",
    "evidence": "36 of 36 paired estimates negative.",
    "implication": "Do not rank on the trajectory score.",
    "finding": "docs/superpowers/findings/2026-08-13-momentum-backtest.md",
}

def _write(tmp_path, payload):
    (tmp_path / "evidence.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    return tmp_path

def test_loads_claims_universe_and_limits(tmp_path):
    _write(tmp_path, {"universe": "913 tickers", "limits": ["survivorship bias"],
                      "claims": [_CLAIM]})
    ev = load_evidence(tmp_path)
    assert ev.universe == "913 tickers"
    assert ev.limits == ["survivorship bias"]
    assert len(ev.claims) == 1
    assert ev.claims[0].id == "acceleration-beats-12m"
    assert ev.claims[0].verdict == "refuted"
    assert ev.claims[0].universe is None

def test_missing_file_yields_empty_register(tmp_path):
    ev = load_evidence(tmp_path)
    assert ev.claims == [] and ev.universe == "" and ev.limits == []

def test_malformed_yaml_yields_empty_register(tmp_path):
    (tmp_path / "evidence.yaml").write_text("claims: [oops: :", encoding="utf-8")
    assert load_evidence(tmp_path).claims == []

@pytest.mark.parametrize("payload", ["just a string", ["a", "list"], None])
def test_non_mapping_payload_yields_empty_register(tmp_path, payload):
    (tmp_path / "evidence.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    assert load_evidence(tmp_path).claims == []

def test_claims_not_a_list_yields_no_claims(tmp_path):
    _write(tmp_path, {"claims": {"id": "x"}})
    assert load_evidence(tmp_path).claims == []

def test_claim_missing_a_required_key_is_skipped_siblings_survive(tmp_path):
    broken = {k: v for k, v in _CLAIM.items() if k != "implication"}
    broken["id"] = "broken"
    _write(tmp_path, {"claims": [broken, _CLAIM]})
    ev = load_evidence(tmp_path)
    assert [c.id for c in ev.claims] == ["acceleration-beats-12m"]

def test_claim_with_empty_required_value_is_skipped(tmp_path):
    empty = dict(_CLAIM, id="empty-evidence", evidence="")
    _write(tmp_path, {"claims": [empty, _CLAIM]})
    assert [c.id for c in load_evidence(tmp_path).claims] == ["acceleration-beats-12m"]

def test_yaml_date_is_coerced_to_string(tmp_path):
    # An unquoted ISO date in YAML parses to datetime.date, which must not
    # reach the prompt as a repr.
    (tmp_path / "evidence.yaml").write_text(
        "claims:\n"
        "  - id: d\n"
        "    claim: c\n"
        "    verdict: refuted\n"
        "    tested: 2026-08-13\n"
        "    evidence: e\n"
        "    implication: i\n"
        "    finding: f.md\n", encoding="utf-8")
    assert load_evidence(tmp_path).claims[0].tested == "2026-08-13"

def test_per_claim_universe_override_is_kept(tmp_path):
    _write(tmp_path, {"universe": "default",
                      "claims": [dict(_CLAIM, universe="a different dataset")]})
    assert load_evidence(tmp_path).claims[0].universe == "a different dataset"

def test_by_verdict_filters():
    a = Claim("a", "c", "refuted", "d", "e", "i", "f")
    b = Claim("b", "c", "supported", "d", "e", "i", "f")
    ev = Evidence(claims=[a, b])
    assert [c.id for c in ev.by_verdict("supported")] == ["b"]
    assert ev.by_verdict("inconclusive") == []

def test_render_contains_every_field_of_every_claim(tmp_path):
    _write(tmp_path, {"universe": "913 tickers", "limits": ["survivorship bias"],
                      "claims": [_CLAIM]})
    text = load_evidence(tmp_path).render()
    assert "REFUTED" in text
    assert "913 tickers" in text
    assert "survivorship bias" in text
    assert "Ranking by return acceleration" in text
    assert "36 of 36 paired estimates negative." in text
    assert "Do not rank on the trajectory score." in text
    assert "2026-08-13-momentum-backtest.md" in text

def test_render_flattens_block_scalars(tmp_path):
    wrapped = dict(_CLAIM, claim="a claim\nwrapped over\nthree lines\n")
    _write(tmp_path, {"claims": [wrapped]})
    text = load_evidence(tmp_path).render()
    assert "a claim wrapped over three lines" in text

def test_render_of_empty_register_is_empty_string():
    assert Evidence().render() == ""

def test_verdict_vocabulary_is_exactly_three():
    assert set(VERDICTS) == {"refuted", "supported", "inconclusive"}
    assert "finding" in REQUIRED_KEYS
