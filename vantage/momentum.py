"""Return term structure: is an asset still working, or did it already work?

Vantage ranks on the trailing 12-month return, which describes the past. This
unit compares an asset's recent pace against its own long-run pace to say
whether it is accelerating or rolling over.

Two decisions shape everything here (see the design spec):

* Comparisons are DIFFERENCES of annualized rates, never ratios. A ratio blows
  up when the long-run base is near zero, and ranks a flat year with one good
  quarter above everything else.
* One month is not evidence of fading. Momentum is conventionally formed on
  12-minus-1 month returns precisely because short-horizon returns tend to
  reverse rather than continue, so `fading` requires decay at BOTH 3m and 6m.

Pure: no I/O, no settings, no network. Callers supply the numbers.
"""
from dataclasses import dataclass

WINDOW_MONTHS = {"ret_1m": 1, "ret_3m": 3, "ret_6m": 6, "ret_12m": 12}

# A label is contradicted by where the price actually sits relative to its own
# 52-week high; these bounds decide when to say so out loud.
_DISAGREE_ACCEL_DRAWDOWN = -0.20
_DISAGREE_FADE_DRAWDOWN = -0.05


@dataclass
class MomentumParams:
    min_recent_return: float = 0.05    # absolute strength gate on the recent window
    min_1m_return: float = -0.15       # soft floor: exclude active collapse, do not
                                       # require a positive month (see module docstring)
    recent_window: str = "ret_3m"
    use_volatility: bool = True


@dataclass
class Trajectory:
    label: str = "unknown"             # accelerating | steady | fading | unknown
    score: float | None = None
    pace_3m: float | None = None
    pace_6m: float | None = None
    pace_12m: float | None = None
    volatility: float | None = None
    drawdown_from_high: float | None = None
    disagrees: bool = False
    benchmark_adjusted: bool = False


def annualize(r, months):
    """Scale a window return to an annual rate. None when undefined."""
    if r is None:
        return None
    try:
        base = 1.0 + float(r)
    except (TypeError, ValueError):
        return None
    if base <= 0.0:          # total loss: a fractional exponent would go complex
        return None
    return base ** (12.0 / months) - 1.0


def _paces(metrics, benchmark_metrics):
    """Annualized excess pace per window, or None if any required one is missing."""
    out = {}
    for key, months in WINDOW_MONTHS.items():
        a = annualize(metrics.get(key), months)
        if a is None:
            return None
        if benchmark_metrics:
            b = annualize(benchmark_metrics.get(key), months)
            if b is not None:
                a = a - b
        out[key] = a
    return out


def classify(metrics, benchmark_metrics=None, volatility=None, drawdown=None,
             params=None) -> Trajectory:
    """Label and score a ticker's term structure. Never raises."""
    p = params or MomentumParams()
    metrics = metrics if isinstance(metrics, dict) else {}
    adjusted = bool(benchmark_metrics)

    paces = _paces(metrics, benchmark_metrics)
    if paces is None:
        return Trajectory(volatility=volatility, drawdown_from_high=drawdown,
                          benchmark_adjusted=adjusted)

    recent = paces[p.recent_window]
    long_run = paces["ret_12m"]
    gap = recent - long_run

    score = None
    if p.use_volatility:
        if volatility:                       # zero or None -> no score
            score = gap / volatility
    else:
        score = gap

    label = "steady"
    if paces["ret_3m"] < long_run and paces["ret_6m"] < long_run:
        label = "fading"
    elif gap > 0 and _passes_gates(metrics, p):
        label = "accelerating"

    disagrees = False
    if drawdown is not None:
        disagrees = ((label == "accelerating" and drawdown < _DISAGREE_ACCEL_DRAWDOWN)
                     or (label == "fading" and drawdown > _DISAGREE_FADE_DRAWDOWN))

    return Trajectory(label=label, score=score, pace_3m=paces["ret_3m"],
                      pace_6m=paces["ret_6m"], pace_12m=paces["ret_12m"],
                      volatility=volatility, drawdown_from_high=drawdown,
                      disagrees=disagrees, benchmark_adjusted=adjusted)


def _passes_gates(metrics, p) -> bool:
    """Real absolute strength, not merely a smaller decline than before."""
    recent = metrics.get(p.recent_window)
    r1 = metrics.get("ret_1m")
    r12 = metrics.get("ret_12m")
    try:
        return (recent is not None and recent >= p.min_recent_return
                and r12 is not None and r12 > 0
                and r1 is not None and r1 >= p.min_1m_return)
    except TypeError:
        return False
