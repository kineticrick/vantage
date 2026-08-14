import math
import pytest
from vantage.termstructure import (DRAWDOWN, MISSING, WINDOWS, format_pct,
                                   render_text_table, term_structure)

def test_format_pct_one_decimal_below_the_break():
    assert format_pct(0.092) == "+9.2%"
    assert format_pct(-0.073) == "-7.3%"
    assert format_pct(0.0) == "+0.0%"

def test_format_pct_no_decimals_at_and_above_the_break():
    assert format_pct(6.317) == "+632%"
    assert format_pct(1.0) == "+100%"
    assert format_pct(-1.27) == "-127%"

def test_format_pct_precision_boundary():
    assert format_pct(0.999) == "+99.9%"     # 99.9% -> one decimal
    assert format_pct(1.0) == "+100%"        # 100%  -> none

def test_format_pct_signs_are_ascii():
    # This output reaches a prompt, an email and a JSON API. A typographic
    # minus here is a UnicodeDecodeError waiting to happen downstream.
    for v in (0.5, -0.5, 6.0, -6.0):
        assert "−" not in format_pct(v)
    assert format_pct(-0.5).startswith("-")
    assert format_pct(0.5).startswith("+")

@pytest.mark.parametrize("bad", [None, "x", [], {}, float("nan"),
                                 float("inf"), float("-inf")])
def test_format_pct_never_raises(bad):
    assert format_pct(bad) == MISSING

def test_term_structure_returns_five_entries_in_fixed_order():
    m = {"ret_1m": -0.073, "ret_3m": 0.092, "ret_6m": 1.266,
         "ret_12m": 6.317, "drawdown_from_high": -0.123}
    ts = term_structure(m)
    assert [e["label"] for e in ts] == ["1m", "3m", "6m", "12m", "off high"]
    assert [e["display"] for e in ts] == ["-7.3%", "+9.2%", "+127%", "+632%", "-12.3%"]
    assert ts[0]["value"] == pytest.approx(-0.073)

def test_absent_metric_keeps_its_column():
    # A dropped entry would shift every later column in the rendered row.
    ts = term_structure({"ret_1m": 0.05})
    assert len(ts) == 5
    assert ts[0]["display"] == "+5.0%"
    assert [e["display"] for e in ts[1:]] == [MISSING] * 4
    assert ts[1]["value"] is None

def test_unusable_value_yields_missing_and_none_value():
    ts = term_structure({"ret_1m": "banana", "ret_3m": float("nan")})
    assert ts[0]["display"] == MISSING and ts[0]["value"] is None
    assert ts[1]["display"] == MISSING and ts[1]["value"] is None

def test_term_structure_tolerates_a_non_dict():
    assert [e["display"] for e in term_structure(None)] == [MISSING] * 5
    assert len(term_structure("nope")) == 5

def test_render_text_table_aligns_columns_across_rows():
    rows = [("MU", {"ret_1m": -0.073, "ret_12m": 6.317}),
            ("LONGTICK", {"ret_1m": 0.208, "ret_12m": 0.226})]
    lines = render_text_table(rows).splitlines()
    assert len(lines) == 3                      # header + two rows
    # every line is the same width, which is what makes a column scannable
    assert len({len(x) for x in lines}) == 1
    assert "1m" in lines[0] and "off high" in lines[0]
    assert lines[1].startswith("MU")
    assert "-7.3%" in lines[1] and "+632%" in lines[1]

def test_render_text_table_respects_the_limit():
    rows = [(f"T{i}", {"ret_1m": 0.01}) for i in range(40)]
    assert len(render_text_table(rows, limit=5).splitlines()) == 6

def test_render_text_table_empty_is_empty_string():
    assert render_text_table([]) == ""

def test_window_labels_are_stable():
    assert [label for _, label in WINDOWS] == ["1m", "3m", "6m", "12m"]
    assert DRAWDOWN == ("drawdown_from_high", "off high")
