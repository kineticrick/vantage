"""Presenting a ticker's return term structure.

The four trailing windows and the distance below the 52-week high are facts
worth showing. They are not a forecast: three studies found this shape does not
predict forward returns (see config/evidence.yaml). Nothing here ranks, sorts
or scores — it formats.

One formatter, several consumers. The chat prompt, the dashboard and the
run_screen tool must render the same number identically, so the API ships the
display strings produced here rather than letting each consumer format its own.
"""
import math

WINDOWS = (("ret_1m", "1m"), ("ret_3m", "3m"),
           ("ret_6m", "6m"), ("ret_12m", "12m"))
DRAWDOWN = ("drawdown_from_high", "off high")
MISSING = "--"

# Below this many percent a decimal carries information; above it, the decimal
# is noise on a number already measured in hundreds.
_PRECISION_BREAK = 100.0


def format_pct(value) -> str:
    """A return fraction as a signed percentage. Never raises.

    Signs are ASCII on purpose — this string reaches a prompt, an email and a
    JSON API, and a typographic minus is a decoding hazard downstream.
    """
    try:
        pct = float(value) * 100.0
    except (TypeError, ValueError):
        return MISSING
    if not math.isfinite(pct):
        return MISSING
    digits = 1 if abs(pct) < _PRECISION_BREAK else 0
    return f"{pct:+.{digits}f}%"


def term_structure(metrics) -> list:
    """The five cells, in fixed order, for one ticker.

    An absent or unusable metric keeps its column with MISSING rather than
    being dropped — a dropped entry shifts every column after it.
    """
    metrics = metrics if isinstance(metrics, dict) else {}
    out = []
    for key, label in WINDOWS + (DRAWDOWN,):
        raw = metrics.get(key)
        display = format_pct(raw)
        out.append({"label": label,
                    "value": raw if display != MISSING else None,
                    "display": display})
    return out


def render_text_table(rows, limit=25) -> str:
    """Aligned block for the chat prompt. `rows` is an iterable of (ticker, metrics)."""
    rows = list(rows)[:limit]
    if not rows:
        return ""
    labels = [label for _, label in WINDOWS] + [DRAWDOWN[1]]
    cells = [(str(t), [e["display"] for e in term_structure(m)]) for t, m in rows]
    tick_w = max([len(t) for t, _ in cells] + [6])
    widths = [max([len(c[i]) for _, c in cells] + [len(labels[i])])
              for i in range(len(labels))]
    def _line(head, values):
        return f"{head:<{tick_w}}" + "".join(
            f"  {values[i]:>{widths[i]}}" for i in range(len(labels)))
    return "\n".join([_line("", labels)] + [_line(t, c) for t, c in cells])
