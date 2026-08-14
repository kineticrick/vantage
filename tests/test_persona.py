# tests/test_persona.py
def test_persona_extracted_and_reused_by_analyst():
    from vantage.persona import ANALYST_PERSONA
    import vantage.analyst as analyst
    # the voice/jobs live in the shared persona
    assert "challenge" in ANALYST_PERSONA.lower()
    assert "second-order" in ANALYST_PERSONA.lower()
    assert "convergence" in ANALYST_PERSONA.lower()
    # output-format instruction is NOT part of the shared persona
    assert "json" not in ANALYST_PERSONA.lower()
    # analyst still composes persona + its JSON-output instruction
    assert ANALYST_PERSONA in analyst._INSTRUCTIONS
    assert "json" in analyst._INSTRUCTIONS.lower()


def test_persona_carries_evidence_discipline():
    from vantage.persona import ANALYST_PERSONA
    lowered = ANALYST_PERSONA.lower()
    # collapse whitespace/newlines so multi-line operative sentences can be
    # asserted on as contiguous phrases
    normalized = " ".join(lowered.split())
    assert "evidence register" in normalized
    # both failure modes must be addressed: crediting refuted claims, and
    # overcorrecting into blanket dismissal
    assert "refuted" in normalized
    assert "absence of evidence" in normalized
    # the label phrases above only catch wholesale deletion. Assert the
    # operative clauses themselves so a semantic gutting of either guardrail
    # (while leaving the label words in place as decoys) also fails.
    assert (
        "never present a refuted claim as an insight or as a reason to act"
        in normalized
    )
    assert "do not become reflexively dismissive" in normalized
    assert 'do not treat "not measured" as "false"' in normalized
