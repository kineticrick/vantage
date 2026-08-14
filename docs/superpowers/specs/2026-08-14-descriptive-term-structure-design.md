# Descriptive Term Structure — Design

**Date:** 2026-08-14
**Status:** Design — pending user review
**Project root:** `/home/kineticrick/code/python/vantage`

## 1. Purpose

Vantage shows one number per ticker: the trailing 12-month return. It computes
three more — 1, 3 and 6 months — and discards their shape at every display
surface. The result is a brief that presents MU at +632% without mentioning it
is down 7% on the month, which reads as a recommendation whether or not one is
intended.

Three studies established that this shape does **not** predict forward returns
(`docs/superpowers/findings/2026-08-13-momentum-backtest.md` and
`docs/superpowers/findings/2026-08-14-conditional-and-sector-breadth.md`). That
settles what to do with it: surface it as **description**, so a reader sees what
a name has actually been doing, and make no claim about what it will do next.

### Success criteria
- Every surface that shows a ticker shows all four return windows and the
  distance below its 52-week high.
- The chat analyst receives the term structure in its context, instead of
  reconstructing it with a per-ticker tool call as it does today.
- The weekly brief carries a section describing what the term structure shows.
- **Nothing ranks, sorts, filters or gates on any of it.** The screener's leader
  selection is byte-for-byte unchanged.
- No `accelerating` / `fading` / `steady` label ships anywhere.

### What already exists
`Signal.metrics` already carries `ret_1m`, `ret_3m`, `ret_6m`, `ret_12m` and
`volume_ratio`; those are persisted in `data/signals-*.json` and already
serialized by `/api/signals`. The weekly analyst prompt already receives them.
This project is mostly display and prompt-context work.

The one genuinely new number is the 52-week-high distance.
`vantage/momentum.drawdown_from_high` exists and has no caller.

## 2. Architecture

Five units.

### 2.1 `vantage/screener.py` — compute the drawdown

The screener holds each ticker's price series, so it computes the distance below
the trailing 52-week high there and attaches it to the existing metrics dict as
`drawdown_from_high`. No dataclass change and no migration: `metrics` is already
a free-form dict of floats, and artifacts written before this change simply lack
the key.

`drawdown_from_high` returns `None` when the series is too short or contains a
non-positive price; in that case the key is **omitted** rather than set to
`None`, matching how the existing return windows are handled.

Phase 1 of the momentum project forbade modifying `screener.py`. That
constraint belonged to Phase 1, which shipped measurement only. It is lifted here.

**Selection is untouched.** `run_screener`'s leader threshold, ranking, sector
momentum and `top_n` truncation are unchanged. The only edit adds a key to a
dict that is already being built.

### 2.2 `vantage/termstructure.py` (new) — one formatter

Small and presentational. It exists because the same number must read identically
in the chat prompt, the dashboard and the tool output, and the ticker-identity
project already demonstrated what happens when two consumers each implement the
same formatting rule.

```python
WINDOWS = (("ret_1m", "1m"), ("ret_3m", "3m"),
           ("ret_6m", "6m"), ("ret_12m", "12m"))
DRAWDOWN = ("drawdown_from_high", "off high")
MISSING = "--"

def format_pct(value) -> str
def term_structure(metrics) -> list          # [{"label","value","display"}, ...]
def render_text_table(rows, limit=25) -> str
```

**`format_pct` contract.** Input is a fraction (`0.092` means +9.2%; `6.317`
means +631.7%). Output carries an explicit sign, and adapts precision so wide
columns do not fill with meaningless digits:

- `abs(pct) < 100` → one decimal: `+9.2%`, `-7.3%`, `-12.3%`
- `abs(pct) >= 100` → no decimals: `+632%`, `+127%`
- `None`, non-numeric, or non-finite → `MISSING`

**One rule for every percentage, including the drawdown.** The mockups approved
during design rendered the drawdown with no decimals (`-12%`); this spec applies
the shared rule instead, so it renders `-12.3%`. Two formatting rules in one
table is how the two consumers drift apart, and consistency is worth one extra
character.

**Sign characters are ASCII** (`-`, not U+2212). This file's output reaches a
YAML-adjacent prompt, an email, and a JSON API; the evidence-register project
just spent a fix round on a `UnicodeDecodeError` from a non-ASCII character in a
hand-edited file, and there is no reason to reintroduce that class of hazard for
typographic polish.

`term_structure(metrics)` returns the five entries in fixed order — four windows
then the drawdown — each as `{"label": "1m", "value": -0.0731, "display":
"-7.3%"}`, with `value: None` and `display: "--"` for anything absent. Callers
never index into `metrics` themselves.

`render_text_table` produces the aligned block used in the chat context.

### 2.3 Chat — `chat_context.py` and `chat_tools.py`

`ChatContext.render()` currently emits leaders as `MU(6.32), LITE(6.06), ...`
and nothing more. That is why the analyst, asked which names had promise, made a
`get_ticker_metrics` call per ticker to rebuild a shape Vantage had already
computed. It is replaced with the aligned table from §2.2.

`chat_tools.run_screen` currently returns `{"ticker", "ret_12m"}` per leader,
discarding the rest. Each leader gains a `term_structure` entry in the same
shape the API uses, so the tool and the context agree.

`get_ticker_metrics` already returns all four windows and needs no change beyond
adding the drawdown, which it can compute from the series it already fetches.

### 2.4 Dashboard — `web/artifacts.py`, `web/app.py`, `static/app.js`, `static/styles.css`

The API sends **pre-formatted display strings** alongside raw values, so the
JavaScript never formats a percentage. `artifacts.signals_payload(signal_set)`
returns the existing `to_dict()` with each signal enriched by a `term_structure`
list; `/api/signals` returns that instead of the bare `to_dict()`.
`build_overview`'s leader and spike entries gain the same list.

Rows render as three lines, per the approved layout:

```
MU                              +631.7%
Micron Technology · Technology
  -7.3%   +9.2%   +127%   +632%   -12.3%
```

The identity subtitle shipped by the ticker-identity project is preserved. The
third line is a fixed-column grid so values align down the panel and a reader can
scan the 1-month column across every name at once — which is the whole point of
the layout, and the reason a wrapped inline list was rejected.

A column whose value is missing renders `--` and keeps its column position.

### 2.5 The brief — `models.py`, `analyst.py`, `report.py`, `web/static/app.js`

`Brief` gains `trajectory_read: str = ""`. `Brief.from_dict` reads it with a
default, so every brief written before this change loads unchanged. The analyst's
JSON schema gains the key with a one-line description; `parse_brief` reads it;
`render_markdown` and `render_html` emit a "Trajectory read" section **only when
the field is non-empty**, so old briefs re-rendered from JSON produce their
original output. The dashboard's brief detail renders it through the existing
`annotate()` path, so tickers named in it get the same tooltips as the rest of
the brief's prose.

**The instruction is deliberately short**, because the evidence register already
carries the prohibition and the two must read as one voice rather than two:

> `trajectory_read`: describe what the return term structure shows across this
> week's names — where recent pace diverges from the 12-month figure, and which
> names sit far below their highs. Description only: the register records that
> this shape does not predict forward returns, so draw no forward conclusion
> from it.

No change to `persona.py`. Its EVIDENCE DISCIPLINE block already states that term
structure is fact worth describing but carries no forward claim.

## 3. Data flow

```
screener ──> Signal.metrics{ret_1m..12m, drawdown_from_high} ──> signals-*.json
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
  termstructure.term_structure()   │                   analyst prompt
        │                          │                   (already had metrics)
        ├─> chat_context table     ├─> /api/signals ──> dashboard rows
        └─> run_screen tool        └─> build_overview      (display strings)
                                                              │
                                              Brief.trajectory_read ──> md/html/web
```

## 4. Error handling

- A missing return window or drawdown renders `--` and keeps its column.
- `format_pct` never raises: `None`, a string, `nan` and `inf` all yield `--`.
- `drawdown_from_high` returning `None` omits the key; nothing downstream
  distinguishes "absent" from "unknown", and both render `--`.
- A `signals-*.json` written before this change has no drawdown key and renders
  with that column blank — no migration, no error.
- A brief written before this change has no `trajectory_read`; the section is
  omitted from every renderer.

## 5. Testing

`vantage/termstructure.py` is pure and gets the bulk of the coverage:
- `format_pct` at the precision boundary (99.9% → one decimal, 100% → none),
  both signs, zero, and the `None` / non-numeric / `nan` / `inf` cases.
- Sign characters are ASCII — asserted explicitly, since this is a stated
  constraint and easy to undo with a well-meaning typographic edit.
- `term_structure` returns five entries in fixed order, with absent metrics
  yielding `value: None` and `display: "--"` rather than being dropped, so
  columns cannot shift.
- `render_text_table` aligns columns across rows of differing widths.

Elsewhere:
- The screener attaches `drawdown_from_high`, omits it when the series is too
  short, and **its selection output is unchanged** — a test comparing signals
  before and after on the same fixture guards the "nothing ranks on this"
  criterion.
- `chat_context.render()` includes the table; `run_screen` includes
  `term_structure`.
- `signals_payload` and `build_overview` include `term_structure` with display
  strings; a signal lacking the drawdown still yields five entries.
- `Brief` round-trips `trajectory_read`; a brief JSON without the key loads;
  `render_markdown` and `render_html` omit the section when empty and include it
  when set.

No JavaScript test harness exists in this project, so the row rendering and
column alignment are verified in the browser.

## 6. Out of scope

- Any `accelerating` / `fading` / `steady` label. The studies refuted the
  labels; only the numbers ship.
- Ranking, sorting, filtering or gating on the term structure or the drawdown.
- A rendered data table in the emailed brief. The prose section was chosen, the
  analyst already receives every number in its prompt, and a five-column table
  is fragile across mail clients.
- Surfacing `sector_breadth`. It was refuted as a predictor and has no
  descriptive home in the current UI.
- `single_day_share`, which remains uncalled.
