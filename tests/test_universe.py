# tests/test_universe.py
from vantage.universe import load_universe

def test_load_universe_parses_and_dedupes(tmp_path):
    f = tmp_path / "universe.txt"
    f.write_text("# comment\nAAPL\n\nmsft\nAAPL\n  NVDA  \n")
    out = load_universe(f)
    assert out == ["AAPL", "MSFT", "NVDA"]
