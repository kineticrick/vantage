# tests/test_persona.py
def test_persona_extracted_and_reused_by_analyst():
    from radar.persona import ANALYST_PERSONA
    import radar.analyst as analyst
    # the voice/jobs live in the shared persona
    assert "challenge" in ANALYST_PERSONA.lower()
    assert "second-order" in ANALYST_PERSONA.lower()
    assert "convergence" in ANALYST_PERSONA.lower()
    # output-format instruction is NOT part of the shared persona
    assert "json" not in ANALYST_PERSONA.lower()
    # analyst still composes persona + its JSON-output instruction
    assert ANALYST_PERSONA in analyst._INSTRUCTIONS
    assert "json" in analyst._INSTRUCTIONS.lower()
