# Conversational Analyst Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an interactive, terminal-based conversational analyst — reusing the challenge-and-coach persona and the user's live portfolio/signals context, with on-demand custom tools for grounded answers — on a web-ready conversation engine.

**Architecture:** An interface-agnostic `Conversation` engine whose `send(message)` yields a stream of structured events (text/tool_use/error/done) and never prints; a thin terminal REPL consumes it. Custom tools (`get_ticker_metrics`, `run_screen`) reuse the deterministic `data_ingest`/`screener` code so figures are real. The analyst persona is extracted to a shared module so the one-shot brief and the chat speak with one voice.

**Tech Stack:** Python 3, the `anthropic` SDK (`claude-opus-4-8`, streaming, tool use, `web_search` server tool), reusing existing `radar` units. pytest.

## Global Constraints

- **Model:** `claude-opus-4-8`, `thinking={"type": "adaptive"}`, streaming via `client.messages.stream`. Tools = the `web_search` server tool (`{"type": "web_search_20260209", "name": "web_search"}`) plus the custom tool definitions. Do NOT pass `temperature`/`top_p`/`top_k`/`budget_tokens`.
- **Engine is interface-agnostic:** `Conversation.send()` yields event dicts and never prints. Event types: `{"type":"text","text":str}`, `{"type":"tool_use","name":str,"input":dict}`, `{"type":"error","message":str}`, `{"type":"done"}`. The REPL is the only thing that writes to stdout.
- **Grounding:** custom tools return real numbers from `data_ingest`/`screener`; the model is told to prefer them over guessing.
- **Determinism/coupling:** custom tools and context loading are deterministic and unit-tested with injected fakes. Only `conversation.py` is non-deterministic (tested via an injected fake Anthropic client). No module here imports `portfolio_analysis` directly — go through `portfolio_context`.
- **Disclaimer:** the system prompt carries the existing `analyst.DISCLAIMER` (research aid, not financial advice).
- **Package:** `radar`. Project root `/home/kineticrick/code/python/market_insights`. Entry point `chat.py` at root. Run tests with `.venv/bin/python -m pytest`.
- **Reuse, don't duplicate:** persona text lives once in `radar/persona.py`; tool impls reuse `data_ingest`/`screener`; context reuses `portfolio_context`/`models`.

---

## File Structure

```
radar/persona.py        ANALYST_PERSONA constant (extracted from analyst.py)
radar/chat_tools.py     get_ticker_metrics, run_screen, TOOL_DEFINITIONS, CUSTOM_TOOL_NAMES, dispatch
radar/chat_context.py   ChatContext dataclass + load_chat_context (newest signals/brief + portfolio + interests)
radar/conversation.py   Conversation engine (send() -> event iterator; tool loop; streaming)
chat.py                 thin terminal REPL + main() + transcript save
radar/analyst.py        MODIFIED: import persona instead of inlining it
README.md               MODIFIED: add a "Chat" section
tests/test_persona.py
tests/test_chat_tools.py
tests/test_chat_context.py
tests/test_conversation.py
tests/test_chat.py
```

> Note: the spec (§5) tentatively placed `load_chat_context` inside `conversation.py`; this plan puts it in its own `radar/chat_context.py` for cleaner task isolation. The spec (§4) mentioned an `exclude_asset_types` option for `run_screen`; this plan **omits it** — asset types are not available universe-wide (only for held names), so it would be a half-working feature. `run_screen` overrides thresholds only (the spec flagged this to tune during implementation).

---

### Task 1: Extract the analyst persona

**Files:**
- Create: `radar/persona.py`
- Modify: `radar/analyst.py` (replace the inline persona portion of `_INSTRUCTIONS` with an import)
- Test: `tests/test_persona.py`

**Interfaces:**
- Produces: `radar.persona.ANALYST_PERSONA: str` — the analyst role, the five analytical jobs (emerging narratives, narrative↔price convergence, second-order/supply-chain, personal lens, challenge & coach), and the "be specific and grounded, cite sources, state uncertainty" guidance. Excludes any output-format/JSON instruction.
- Modifies: `radar/analyst.py` so `_INSTRUCTIONS == ANALYST_PERSONA + "\n\n" + <json-output instruction>`. `build_prompt`, `parse_brief`, `generate_brief`, and `DISCLAIMER` keep their current signatures and behavior.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_persona.py -v`
Expected: FAIL (`radar.persona` does not exist).

- [ ] **Step 3: Create `radar/persona.py` and refactor `radar/analyst.py`**

In `radar/analyst.py`, the current `_INSTRUCTIONS` string contains the analyst role + the five tasks + a closing paragraph, followed by a section that begins with "Return your final answer as a single JSON object inside a ```json code block ...".

Move everything **before** that JSON-output section into `radar/persona.py` as `ANALYST_PERSONA`, and keep the JSON-output section in `analyst.py`:

```python
# radar/persona.py
ANALYST_PERSONA = """<paste here verbatim the role + five tasks + the
"Be specific and grounded. Show evidence and cite sources. State uncertainty
plainly." paragraph from analyst._INSTRUCTIONS — i.e. everything EXCEPT the
"Return your final answer as a single JSON object ..." section>"""
```

Then in `radar/analyst.py`, replace the `_INSTRUCTIONS = """..."""` assignment with:

```python
from radar.persona import ANALYST_PERSONA

_JSON_OUTPUT = """Return your final answer as a single JSON object inside a ```json code block with
exactly these keys:
{
  "executive_summary": str,
  "items": [{"title": str, "thesis": str, "evidence": str, "sources": [str],
             "why_it_matters": str, "portfolio_relevance": str}],
  "watchlist": [str],
  "challenge": str,
  "what_im_missing": str
}
"""

_INSTRUCTIONS = ANALYST_PERSONA + "\n\n" + _JSON_OUTPUT
```

Keep everything else in `analyst.py` (`DISCLAIMER`, `build_prompt`, `parse_brief`, `generate_brief`) unchanged. `build_prompt` already concatenates `_INSTRUCTIONS`, so its output is byte-identical to before.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_persona.py tests/test_analyst.py -v`
Expected: PASS (new persona test plus all existing analyst tests — the refactor is behavior-preserving).

- [ ] **Step 5: Commit**

```bash
git add radar/persona.py radar/analyst.py tests/test_persona.py
git commit -m "refactor: extract analyst persona to radar/persona.py"
```

---

### Task 2: Custom chat tools

**Files:**
- Create: `radar/chat_tools.py`
- Test: `tests/test_chat_tools.py`

**Interfaces:**
- Consumes: `data_ingest.fetch_market_data` / `MarketData`; `screener._trailing_return`, `screener._volume_ratio`, `screener._WINDOWS`, `screener.run_screener`; `universe.load_universe`; `Settings` (for `cache_dir`, `config_dir`).
- Produces:
  - `get_ticker_metrics(ticker, settings, _downloader=None, _sector_fn=None) -> dict` — `{"ticker", "ret_1m", "ret_3m", "ret_6m", "ret_12m", "volume_ratio", "sector"}`, or `{"ticker", "error": <str>}` on failure / no data.
  - `run_screen(settings, return_leader_threshold=1.0, volume_spike_ratio=2.0, top_n=15, _market_data_fn=None) -> dict` — `{"leaders": [{"ticker","ret_12m"}], "volume_spikes": [{"ticker","volume_ratio"}], "sector_momentum": {sector: float}}`, or `{"error": <str>}`.
  - `TOOL_DEFINITIONS: list[dict]` — the two Anthropic tool schemas (names `get_ticker_metrics`, `run_screen`).
  - `CUSTOM_TOOL_NAMES: set[str]` — `{"get_ticker_metrics", "run_screen"}`.
  - `dispatch(name, tool_input, settings) -> dict` — routes a tool call to its impl; unknown name → `{"error": "unknown tool: <name>"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chat_tools.py
import pandas as pd
from pathlib import Path
from radar.settings import Settings
from radar.chat_tools import (get_ticker_metrics, run_screen, dispatch,
                              TOOL_DEFINITIONS, CUSTOM_TOOL_NAMES)
from radar.data_ingest import MarketData

def _settings(tmp_path):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "universe.txt").write_text("AAPL\nMU\n")
    return Settings(anthropic_api_key="", gmail_user="", gmail_app_password="",
                    email_recipient="", model="claude-opus-4-8",
                    portfolio_analysis_path="/x", project_root=tmp_path,
                    config_dir=tmp_path / "config", data_dir=tmp_path,
                    reports_dir=tmp_path, cache_dir=tmp_path)

def _fake_download(tickers, period):
    n = 300
    idx = pd.date_range("2024-06-01", periods=n, freq="D")
    cols = pd.MultiIndex.from_product([["Close", "Volume"], tickers])
    data = {}
    for t in tickers:
        data[("Close", t)] = [100.0 + i for i in range(n)]      # rising -> real returns
        data[("Volume", t)] = [1000.0] * (n - 1) + [5000.0]     # last-day spike
    return pd.DataFrame(data, index=idx, columns=cols)

def _fake_sector(t):
    return "Technology"

def test_get_ticker_metrics_returns_real_numbers(tmp_path):
    out = get_ticker_metrics("MU", _settings(tmp_path),
                             _downloader=_fake_download, _sector_fn=_fake_sector)
    assert out["ticker"] == "MU"
    assert out["sector"] == "Technology"
    assert out["ret_12m"] is not None and out["ret_12m"] > 0
    assert out["volume_ratio"] > 1.0
    assert "error" not in out

def test_get_ticker_metrics_error_on_no_data(tmp_path):
    def empty_download(tickers, period):
        return pd.DataFrame()
    out = get_ticker_metrics("ZZZZ", _settings(tmp_path),
                             _downloader=empty_download, _sector_fn=_fake_sector)
    assert "error" in out and out["ticker"] == "ZZZZ"

def test_run_screen_summarizes(tmp_path):
    md = MarketData(as_of="2026-06-27",
                    prices={"MU": pd.Series([100.0 + i for i in range(300)],
                                            index=pd.date_range("2024-06-01", periods=300, freq="D"))},
                    volumes={"MU": pd.Series([1000.0] * 300,
                                             index=pd.date_range("2024-06-01", periods=300, freq="D"))},
                    sectors={"MU": "Technology"})
    out = run_screen(_settings(tmp_path), return_leader_threshold=0.5,
                     _market_data_fn=lambda tickers, cache_dir: md)
    assert any(l["ticker"] == "MU" for l in out["leaders"])
    assert "sector_momentum" in out and "Technology" in out["sector_momentum"]

def test_tool_defs_and_dispatch(tmp_path):
    names = {d["name"] for d in TOOL_DEFINITIONS}
    assert names == CUSTOM_TOOL_NAMES == {"get_ticker_metrics", "run_screen"}
    # each tool def has an input_schema
    assert all("input_schema" in d for d in TOOL_DEFINITIONS)
    # dispatch routes to the impl
    out = dispatch("get_ticker_metrics", {"ticker": "MU"}, _settings(tmp_path))
    assert "ticker" in out  # ran (may be error if no network, but routed)
    assert dispatch("nope", {}, _settings(tmp_path))["error"].startswith("unknown tool")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_chat_tools.py -v`
Expected: FAIL (`radar.chat_tools` does not exist).

- [ ] **Step 3: Create `radar/chat_tools.py`**

```python
from radar.data_ingest import fetch_market_data
from radar.screener import _WINDOWS, _trailing_return, _volume_ratio, run_screener
from radar.universe import load_universe

def get_ticker_metrics(ticker, settings, _downloader=None, _sector_fn=None) -> dict:
    ticker = ticker.upper().strip()
    try:
        md = fetch_market_data([ticker], cache_dir=settings.cache_dir,
                               _downloader=_downloader, _sector_fn=_sector_fn)
    except Exception as e:
        return {"ticker": ticker, "error": f"data fetch failed: {e}"}
    prices = md.prices.get(ticker)
    if prices is None or len(prices) == 0:
        return {"ticker": ticker, "error": "no price data found"}
    out = {"ticker": ticker, "sector": md.sectors.get(ticker, "Unknown")}
    for name, lb in _WINDOWS.items():
        out[name] = _trailing_return(prices, lb)
    vol = md.volumes.get(ticker)
    out["volume_ratio"] = _volume_ratio(vol) if vol is not None else None
    return out

def run_screen(settings, return_leader_threshold=1.0, volume_spike_ratio=2.0,
               top_n=15, _market_data_fn=None) -> dict:
    try:
        tickers = load_universe(settings.config_dir / "universe.txt")
        md_fn = _market_data_fn or (lambda tk, cd: fetch_market_data(tk, cd))
        md = md_fn(tickers, settings.cache_dir)
        ss = run_screener(md, top_n=top_n,
                          return_leader_threshold=return_leader_threshold,
                          volume_spike_ratio=volume_spike_ratio)
    except Exception as e:
        return {"error": f"screen failed: {e}"}
    leaders = [{"ticker": s.ticker, "ret_12m": round(s.value, 3)}
               for s in ss.signals if s.signal_type == "ret_12m_leader"]
    spikes = [{"ticker": s.ticker, "volume_ratio": round(s.value, 2)}
              for s in ss.signals if s.signal_type == "volume_spike"]
    momentum = {k: round(v, 3) for k, v in ss.sector_momentum.items()}
    return {"leaders": leaders, "volume_spikes": spikes, "sector_momentum": momentum}

TOOL_DEFINITIONS = [
    {
        "name": "get_ticker_metrics",
        "description": "Get a single ticker's trailing returns (1/3/6/12 month, "
                       "as fractions) and recent volume ratio. Use for exact figures "
                       "on any ticker rather than guessing.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Ticker symbol"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "run_screen",
        "description": "Re-run the market screen over the configured universe with "
                       "optional threshold overrides; returns the top 12-month return "
                       "leaders, volume spikes, and median sector momentum.",
        "input_schema": {
            "type": "object",
            "properties": {
                "return_leader_threshold": {"type": "number",
                    "description": "Min 12mo return (fraction) to count as a leader, e.g. 1.0 = +100%"},
                "volume_spike_ratio": {"type": "number",
                    "description": "Min volume-vs-average ratio to flag a spike, e.g. 2.0"},
                "top_n": {"type": "integer", "description": "Max signals to return"},
            },
        },
    },
]

CUSTOM_TOOL_NAMES = {"get_ticker_metrics", "run_screen"}

def dispatch(name, tool_input, settings) -> dict:
    if name == "get_ticker_metrics":
        return get_ticker_metrics(tool_input.get("ticker", ""), settings)
    if name == "run_screen":
        kwargs = {k: v for k, v in tool_input.items()
                  if k in ("return_leader_threshold", "volume_spike_ratio", "top_n")}
        return run_screen(settings, **kwargs)
    return {"error": f"unknown tool: {name}"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_chat_tools.py -v`
Expected: PASS. (Note: `test_tool_defs_and_dispatch`'s `dispatch("get_ticker_metrics", ...)` runs the real impl with no injected downloader; it returns either metrics or an `{"error": ...}` dict — both contain `"ticker"`, so the assertion holds without network.)

- [ ] **Step 5: Commit**

```bash
git add radar/chat_tools.py tests/test_chat_tools.py
git commit -m "feat: custom chat tools (ticker metrics, re-screen)"
```

---

### Task 3: Chat context loading

**Files:**
- Create: `radar/chat_context.py`
- Test: `tests/test_chat_context.py`

**Interfaces:**
- Consumes: `portfolio_context.load_portfolio_context`; `models.SignalSet` / `models.Brief`; `Settings`; PyYAML.
- Produces:
  - `ChatContext` dataclass: `portfolio` (`PortfolioContext|None`), `signals` (`SignalSet|None`), `interests` (`dict`), `brief` (`Brief|None`). Method `render() -> str` (a human-readable context block; notes each missing piece rather than omitting silently).
  - `load_chat_context(settings, _portfolio_fn=None) -> ChatContext` — loads the live portfolio (via `_portfolio_fn or load_portfolio_context`), the newest `data/signals-*.json`, `config/interests.yaml`, and the newest `reports/brief-*.json`. Every piece is optional.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chat_context.py
import json
from pathlib import Path
from radar.settings import Settings
from radar.chat_context import ChatContext, load_chat_context
from radar.models import SignalSet, Signal, Brief, BriefItem, PortfolioContext

def _settings(tmp_path):
    for d in ("data", "reports", "config"):
        (tmp_path / d).mkdir(exist_ok=True)
    return Settings(anthropic_api_key="", gmail_user="", gmail_app_password="",
                    email_recipient="", model="claude-opus-4-8",
                    portfolio_analysis_path="/x", project_root=tmp_path,
                    config_dir=tmp_path / "config", data_dir=tmp_path / "data",
                    reports_dir=tmp_path / "reports", cache_dir=tmp_path)

def _pc():
    return PortfolioContext(available=True, holdings=[], sector_concentration={"Tech": 0.5},
                            asset_type_concentration={}, revealed_interests=["NVDA"], note="")

def test_load_chat_context_picks_newest_and_renders(tmp_path):
    s = _settings(tmp_path)
    # two signal files; the newest (by name/date) should win
    SignalSet("2026-06-20", [Signal("OLD", "ret_12m_leader", 1.0, 1)], {}).save(
        s.data_dir / "signals-2026-06-20.json")
    SignalSet("2026-06-27", [Signal("MU", "ret_12m_leader", 7.9, 1)], {"Tech": 0.25}).save(
        s.data_dir / "signals-2026-06-27.json")
    (s.config_dir / "interests.yaml").write_text("themes: [AI]\n")
    brief = Brief("2026-06-27", "summary", [BriefItem("t","x","x",[],"x","x")],
                  ["NVDA"], "challenge", "missing", "Not financial advice.")
    (s.reports_dir / "brief-2026-06-27.json").write_text(json.dumps(brief.to_dict()))

    ctx = load_chat_context(s, _portfolio_fn=lambda pa: _pc())
    assert ctx.signals.as_of == "2026-06-27"          # newest
    assert ctx.signals.signals[0].ticker == "MU"
    assert ctx.interests == {"themes": ["AI"]}
    assert ctx.brief.executive_summary == "summary"
    assert ctx.portfolio.available
    text = ctx.render()
    assert "MU" in text and "Tech" in text and "NVDA" in text

def test_load_chat_context_graceful_when_missing(tmp_path):
    s = _settings(tmp_path)  # no signals, no brief, no interests
    ctx = load_chat_context(s, _portfolio_fn=lambda pa: PortfolioContext(available=False, note="db down"))
    assert ctx.signals is None and ctx.brief is None and ctx.interests == {}
    text = ctx.render()
    assert "unavailable" in text.lower() or "no " in text.lower()  # notes the gaps
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_chat_context.py -v`
Expected: FAIL (`radar.chat_context` does not exist).

- [ ] **Step 3: Create `radar/chat_context.py`**

```python
import json
from dataclasses import dataclass, field
from pathlib import Path
import yaml
from radar.models import SignalSet, Brief
from radar.portfolio_context import load_portfolio_context

def _newest(directory, pattern):
    files = sorted(Path(directory).glob(pattern))
    return files[-1] if files else None

@dataclass
class ChatContext:
    portfolio: object = None          # PortfolioContext | None
    signals: object = None            # SignalSet | None
    interests: dict = field(default_factory=dict)
    brief: object = None              # Brief | None

    def render(self) -> str:
        parts = []
        if self.portfolio is not None and getattr(self.portfolio, "available", False):
            parts.append(self.portfolio.summary_text())
        else:
            note = getattr(self.portfolio, "note", "") if self.portfolio else ""
            parts.append(f"Portfolio: unavailable ({note}).")
        if self.signals is not None:
            leaders = ", ".join(f"{s.ticker}({s.value:.2f})" for s in self.signals.signals
                                if s.signal_type == "ret_12m_leader")[:800]
            mom = ", ".join(f"{k} {v:+.0%}" for k, v in self.signals.sector_momentum.items())
            parts.append(f"Latest signals ({self.signals.as_of}): 12mo leaders: "
                         f"{leaders or 'none'}. Sector momentum: {mom or 'none'}.")
        else:
            parts.append("Latest signals: none saved yet (suggest running the weekly pipeline).")
        parts.append(f"Interest overlay: {json.dumps(self.interests) if self.interests else 'none set'}.")
        if self.brief is not None:
            titles = "; ".join(i.title for i in self.brief.items)
            parts.append(f"Latest brief ({self.brief.as_of}): {self.brief.executive_summary[:400]} "
                         f"Items: {titles}.")
        else:
            parts.append("Latest brief: none saved yet.")
        return "\n".join(parts)

def load_chat_context(settings, _portfolio_fn=None) -> ChatContext:
    pf = (_portfolio_fn or load_portfolio_context)
    try:
        portfolio = pf(settings.portfolio_analysis_path)
    except Exception as e:
        from radar.models import PortfolioContext
        portfolio = PortfolioContext(available=False, note=str(e)[:200])

    signals = None
    sig_file = _newest(settings.data_dir, "signals-*.json")
    if sig_file:
        try:
            signals = SignalSet.load(sig_file)
        except Exception:
            signals = None

    interests = {}
    ipath = settings.config_dir / "interests.yaml"
    if ipath.exists():
        interests = yaml.safe_load(ipath.read_text()) or {}

    brief = None
    brief_file = _newest(settings.reports_dir, "brief-*.json")
    if brief_file:
        try:
            brief = Brief.from_dict(json.loads(brief_file.read_text()))
        except Exception:
            brief = None

    return ChatContext(portfolio=portfolio, signals=signals,
                       interests=interests, brief=brief)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_chat_context.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add radar/chat_context.py tests/test_chat_context.py
git commit -m "feat: chat context loading (portfolio + latest signals/brief/interests)"
```

---

### Task 4: Conversation engine

**Files:**
- Create: `radar/conversation.py`
- Test: `tests/test_conversation.py`

**Interfaces:**
- Consumes: `persona.ANALYST_PERSONA`; `analyst.DISCLAIMER`; `chat_context.load_chat_context` (+ `ChatContext`); `chat_tools.TOOL_DEFINITIONS` / `CUSTOM_TOOL_NAMES` / `dispatch`; `Settings`; the `anthropic` SDK.
- Produces: `Conversation` class.
  - `Conversation(settings, _client=None, _context=None)` — builds the system prompt from the persona + `(_context or load_chat_context(settings)).render()` + a tool note + the disclaimer; starts empty `messages`.
  - `send(user_message: str) -> Iterator[dict]` — drives a streaming, multi-turn tool loop and yields event dicts (`text`/`tool_use`/`error`/`done`); preserves `messages` history across calls; never prints.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_conversation.py
import types
from pathlib import Path
from radar.settings import Settings
from radar.conversation import Conversation

def _settings():
    return Settings(anthropic_api_key="k", gmail_user="", gmail_app_password="",
                    email_recipient="", model="claude-opus-4-8",
                    portfolio_analysis_path="/x", project_root=Path("."),
                    config_dir=Path("."), data_dir=Path("."), reports_dir=Path("."),
                    cache_dir=Path("."))

class _Ctx:
    def render(self): return "Portfolio: AAPL 50%. Latest signals: MU."

def _text(t): return types.SimpleNamespace(type="text", text=t)
def _tool(id_, name, inp): return types.SimpleNamespace(type="tool_use", id=id_, name=name, input=inp)
def _final(content, stop): return types.SimpleNamespace(content=content, stop_reason=stop)

class _FakeStream:
    def __init__(self, message, deltas): self._m, self._d = message, deltas
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __iter__(self):
        for d in self._d:
            yield types.SimpleNamespace(
                type="content_block_delta",
                delta=types.SimpleNamespace(type="text_delta", text=d))
    def get_final_message(self): return self._m

class _FakeMessages:
    def __init__(self, turns): self.turns = list(turns); self.calls = []
    def stream(self, **kw):
        self.calls.append(kw)
        msg, deltas = self.turns.pop(0)
        return _FakeStream(msg, deltas)

class _FakeClient:
    def __init__(self, turns): self.messages = _FakeMessages(turns)

def test_send_runs_custom_tool_loop_and_yields_events(monkeypatch):
    import radar.conversation as cm
    monkeypatch.setattr(cm, "dispatch", lambda name, inp, s: {"ticker": "MU", "ret_12m": 7.9})
    # turn 1: model calls a custom tool; turn 2: final streamed text
    turn1 = (_final([_tool("tu1", "get_ticker_metrics", {"ticker": "MU"})], "tool_use"), [])
    turn2 = (_final([_text("MU is up a lot.")], "end_turn"), ["MU is ", "up a lot."])
    conv = Conversation(_settings(), _client=_FakeClient([turn1, turn2]), _context=_Ctx())
    events = list(conv.send("how's MU?"))
    kinds = [e["type"] for e in events]
    assert kinds[-1] == "done"
    assert any(e["type"] == "tool_use" and e["name"] == "get_ticker_metrics" for e in events)
    assert any(e["type"] == "text" and "up a lot" in e["text"] for e in events)
    # history: user, assistant(tool_use), user(tool_result), assistant(final)
    assert len(conv.messages) == 4
    assert conv.messages[2]["content"][0]["type"] == "tool_result"
    assert conv.messages[2]["content"][0]["tool_use_id"] == "tu1"

def test_send_preserves_history_across_calls(monkeypatch):
    import radar.conversation as cm
    monkeypatch.setattr(cm, "dispatch", lambda *a: {})
    t1 = (_final([_text("Hi.")], "end_turn"), ["Hi."])
    t2 = (_final([_text("Still here.")], "end_turn"), ["Still here."])
    conv = Conversation(_settings(), _client=_FakeClient([t1, t2]), _context=_Ctx())
    list(conv.send("hello")); list(conv.send("again"))
    assert len(conv.messages) == 4
    assert conv.messages[0] == {"role": "user", "content": "hello"}
    assert conv.messages[2] == {"role": "user", "content": "again"}

def test_send_surfaces_api_error():
    class _BoomMessages:
        def stream(self, **kw): raise RuntimeError("api down")
    class _BoomClient:
        messages = _BoomMessages()
    conv = Conversation(_settings(), _client=_BoomClient(), _context=_Ctx())
    events = list(conv.send("hi"))
    assert any(e["type"] == "error" and "api down" in e["message"] for e in events)
    assert events[-1]["type"] == "done"

def test_system_prompt_has_persona_context_and_disclaimer():
    conv = Conversation(_settings(), _client=_FakeClient([]), _context=_Ctx())
    assert "challenge" in conv.system.lower()        # persona
    assert "AAPL 50%" in conv.system                  # rendered context
    assert "not financial advice" in conv.system.lower()  # disclaimer
    assert "get_ticker_metrics" in conv.system        # tool note
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_conversation.py -v`
Expected: FAIL (`radar.conversation` does not exist).

- [ ] **Step 3: Create `radar/conversation.py`**

```python
import json
from radar.persona import ANALYST_PERSONA
from radar.analyst import DISCLAIMER
from radar.chat_context import load_chat_context
from radar.chat_tools import TOOL_DEFINITIONS, CUSTOM_TOOL_NAMES, dispatch

_WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}
_TOOL_NOTE = ("\n\nYou have two tools for exact figures: get_ticker_metrics(ticker) "
              "and run_screen(...). Prefer calling them over guessing numbers; use "
              "web_search for news. Keep the conversation grounded and challenge the "
              "user's reasoning where the evidence warrants.\n\n")

class Conversation:
    def __init__(self, settings, _client=None, _context=None):
        self.settings = settings
        self._client = _client
        self.context = _context if _context is not None else load_chat_context(settings)
        self.system = (ANALYST_PERSONA + "\n\n=== Current context ===\n"
                       + self.context.render() + _TOOL_NOTE + DISCLAIMER)
        self.messages = []

    def _client_or_default(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
        return self._client

    def send(self, user_message):
        self.messages.append({"role": "user", "content": user_message})
        client = self._client_or_default()
        tools = [_WEB_SEARCH_TOOL] + TOOL_DEFINITIONS
        while True:
            try:
                with client.messages.stream(
                    model=self.settings.model, max_tokens=64000,
                    thinking={"type": "adaptive"}, system=self.system,
                    tools=tools, messages=self.messages,
                ) as stream:
                    for event in stream:
                        if (getattr(event, "type", None) == "content_block_delta"
                                and getattr(event.delta, "type", None) == "text_delta"):
                            yield {"type": "text", "text": event.delta.text}
                    final = stream.get_final_message()
            except Exception as e:  # API/stream failure — surface and end cleanly
                yield {"type": "error", "message": str(e)}
                break

            self.messages.append({"role": "assistant", "content": final.content})
            custom_calls = [b for b in final.content
                            if getattr(b, "type", None) == "tool_use"
                            and getattr(b, "name", None) in CUSTOM_TOOL_NAMES]

            if final.stop_reason == "tool_use" and custom_calls:
                results = []
                for call in custom_calls:
                    yield {"type": "tool_use", "name": call.name, "input": dict(call.input)}
                    out = dispatch(call.name, call.input, self.settings)
                    is_err = "error" in out
                    if is_err:
                        yield {"type": "error", "message": out["error"]}
                    results.append({"type": "tool_result", "tool_use_id": call.id,
                                    "content": json.dumps(out), "is_error": is_err})
                self.messages.append({"role": "user", "content": results})
                continue
            if final.stop_reason == "pause_turn":
                continue  # server tool (web_search) paused — resume the turn
            break
        yield {"type": "done"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_conversation.py -v`
Expected: PASS (all four tests).

- [ ] **Step 5: Commit**

```bash
git add radar/conversation.py tests/test_conversation.py
git commit -m "feat: web-ready conversation engine (streaming tool loop, event stream)"
```

> **Validation note for the executor (spec §13):** the fake-client tests cover the custom-tool loop, multi-turn history, the error path, and the system prompt. The `web_search` server tool + `pause_turn` path cannot be meaningfully faked; validate it with a single live smoke chat after Task 5 (ask a news question and confirm it searches and resumes without error).

---

### Task 5: Terminal REPL + README

**Files:**
- Create: `chat.py`
- Modify: `README.md` (add a "Chat" section)
- Test: `tests/test_chat.py`

**Interfaces:**
- Consumes: `settings.load_settings`; `conversation.Conversation`.
- Produces: `chat.main(argv=None, settings=None, _conversation=None, _input=None) -> None` — runs the REPL: read a line, stream the engine's events to stdout, repeat until `exit`/`quit`/EOF; on exit, write a dated transcript to `reports/chat-<UTC-timestamp>.md`. `_conversation` and `_input` are injectable for testing (no network, no real stdin).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chat.py
from pathlib import Path
import chat
from radar.settings import Settings

def _settings(tmp_path):
    (tmp_path / "reports").mkdir(exist_ok=True)
    return Settings(anthropic_api_key="k", gmail_user="", gmail_app_password="",
                    email_recipient="", model="claude-opus-4-8",
                    portfolio_analysis_path="/x", project_root=tmp_path,
                    config_dir=tmp_path, data_dir=tmp_path,
                    reports_dir=tmp_path / "reports", cache_dir=tmp_path)

class _FakeConversation:
    def __init__(self): self.sent = []
    def send(self, msg):
        self.sent.append(msg)
        yield {"type": "text", "text": f"echo: {msg}"}
        yield {"type": "done"}

def test_main_loops_streams_and_writes_transcript(tmp_path, capsys):
    s = _settings(tmp_path)
    conv = _FakeConversation()
    # feed two questions then EOF (StopIteration -> exit)
    lines = iter(["what's MU?", "and NVDA?"])
    chat.main(settings=s, _conversation=conv, _input=lambda _prompt: next(lines))
    assert conv.sent == ["what's MU?", "and NVDA?"]
    out = capsys.readouterr().out
    assert "echo: what's MU?" in out and "echo: and NVDA?" in out
    transcripts = list((s.reports_dir).glob("chat-*.md"))
    assert len(transcripts) == 1
    body = transcripts[0].read_text()
    assert "what's MU?" in body and "echo: and NVDA?" in body

def test_main_exits_on_quit_command(tmp_path):
    s = _settings(tmp_path)
    conv = _FakeConversation()
    lines = iter(["quit", "should-not-be-sent"])
    chat.main(settings=s, _conversation=conv, _input=lambda _prompt: next(lines))
    assert conv.sent == []  # quit before sending anything
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_chat.py -v`
Expected: FAIL (`chat` module / `chat.main` does not exist).

- [ ] **Step 3: Create `chat.py`**

```python
from datetime import datetime, timezone
from radar.settings import load_settings
from radar.conversation import Conversation

def main(argv=None, settings=None, _conversation=None, _input=None) -> None:
    s = settings or load_settings()
    conv = _conversation or Conversation(s)
    read = _input or (lambda prompt: input(prompt))
    transcript = []
    print("Conversational analyst ready. Type 'exit' or 'quit' to leave.\n")
    while True:
        try:
            line = read("you> ")
        except (EOFError, StopIteration):
            break
        if line is None:
            break
        if line.strip().lower() in ("exit", "quit"):
            break
        if not line.strip():
            continue
        transcript.append(f"**you>** {line}")
        parts = []
        print("analyst> ", end="", flush=True)
        for event in conv.send(line):
            if event["type"] == "text":
                print(event["text"], end="", flush=True)
                parts.append(event["text"])
            elif event["type"] == "tool_use":
                note = f"\n[looking up via {event['name']}({event.get('input', {})})]\n"
                print(note, end="", flush=True)
                parts.append(note)
            elif event["type"] == "error":
                note = f"\n[error: {event['message']}]\n"
                print(note, end="", flush=True)
                parts.append(note)
            # "done" ends the turn
        print("\n")
        transcript.append("**analyst>** " + "".join(parts))
    if transcript:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = s.reports_dir / f"chat-{ts}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Chat transcript {ts}\n\n" + "\n\n".join(transcript) + "\n",
                        encoding="utf-8")
        print(f"[transcript saved to {path}]")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_chat.py -v`
Expected: PASS. (`test_main_loops...` feeds two lines then `next()` raises `StopIteration`, which the loop catches as exit; the transcript is written. `test_main_exits_on_quit...` exits before sending.)

- [ ] **Step 5: Add the README "Chat" section**

Append to `README.md` (after the Run section):

```markdown
## Chat (conversational analyst)

Talk to the analyst interactively — it loads your live portfolio, the latest
saved signals, your interest overlay, and the latest brief, and can pull exact
ticker metrics or re-run the screen on demand:

```
python chat.py
```

Type questions; `exit`/`quit` to leave. Each session writes a transcript to
`reports/chat-<timestamp>.md`. Needs `ANTHROPIC_API_KEY` in `.env`.
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: ALL PASS.

- [ ] **Step 7: Commit**

```bash
git add chat.py README.md tests/test_chat.py
git commit -m "feat: terminal REPL for the conversational analyst + README"
```

---

## Self-Review

**Spec coverage:**
- §2 architecture / units → persona (Task 1), chat_tools (Task 2), chat_context (Task 3), conversation (Task 4), chat.py REPL (Task 5).
- §3 engine `send()` event contract (text/tool_use/error/done), tool loop, streaming, multi-turn history → Task 4 (tested).
- §4 custom tools `get_ticker_metrics` / `run_screen` reusing deterministic code → Task 2. (`exclude_asset_types` intentionally omitted — documented in File Structure note; threshold overrides only.)
- §5 context loading (portfolio + newest signals + interests + newest brief, graceful-missing) → Task 3.
- §6 persona extraction shared by brief + chat → Task 1.
- §7 terminal REPL + transcript + `main()` → Task 5.
- §8 error handling (tool `is_error`, API errors surfaced, missing context noted) → Task 2 (tool errors), Task 3 (missing context), Task 4 (API errors).
- §9 persistence (fresh each launch + transcript) → Task 5.
- §10 testing approach → tests in every task (fake Anthropic client in Task 4; injected fakes elsewhere).
- §11 out of scope (web UI, resume, auth) → not built; the `send()` event seam is the future hook.
- §12 README chat section → Task 5.
- §13 risks → File Structure note (`run_screen` scope / no `exclude_asset_types`) + Task 4 validation note (server-tool/`pause_turn` live smoke test).

**Placeholder scan:** the only deferred verification is the live `web_search`/`pause_turn` smoke test (Task 4 note) — a concrete manual step, not a code gap. No TBD/TODO; all code steps contain complete code.

**Type consistency:** `Settings` fields used consistently across tasks. Event dict shapes (`type`/`text`/`name`/`input`/`message`) match between Task 4's producer and Task 5's consumer. `dispatch(name, input, settings)`, `TOOL_DEFINITIONS`, `CUSTOM_TOOL_NAMES` (Task 2) used exactly as such in Task 4. `ChatContext.render()` (Task 3) consumed by Task 4. `ANALYST_PERSONA` (Task 1) consumed by Task 4. `Conversation(settings, _client, _context)` / `send()` (Task 4) consumed by Task 5.

## Notes for the executor
- Run all commands from the project root with the venv active (`.venv/bin/python`).
- Tasks are ordered by dependency (1→5); execute in order.
- After Task 5, do the one live smoke test from the Task 4 note (a news question that triggers `web_search`) to validate the server-tool path the fakes can't cover.
