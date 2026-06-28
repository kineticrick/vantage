# Vantage Web Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local, single-user FastAPI web dashboard for Vantage — the streaming analyst chat plus read views of signals, portfolio, and briefs, with a button to refresh the quantitative data.

**Architecture:** A new `vantage/web/` subpackage. FastAPI serves a no-build vanilla SPA and a small JSON/SSE API. All analysis logic is reused unchanged from the existing engine (`Conversation`, `run_screener`, `load_portfolio_context`, brief artifacts); the web layer is transport + presentation only. Non-HTTP logic lives in `artifacts.py` (reading saved artifacts) and `pipeline.py` (the refresh job) so it is unit-testable without a server.

**Tech Stack:** Python, FastAPI, uvicorn, vanilla HTML/CSS/JS (no build step). Tests use `fastapi.testclient.TestClient` (needs `httpx`) and pytest.

## Global Constraints

- Binds `127.0.0.1` only; no auth (local single-user). Verbatim default: host `127.0.0.1`, port `8000`.
- No Node / no build step. Frontend is three static files served by FastAPI.
- No live network or DB access in tests — use the dependency-injection seams (`conversation_factory`, `refresh_runner`, `portfolio_loader`, `_market_data_fn`, `_portfolio_fn`).
- Reuse existing engine code; add no new analysis logic.
- The web app never sends email and never generates a brief (that stays in `run_weekly`/cron).
- Follow existing test style: dataclass `Settings` built directly with tmp dirs (see `tests/test_chat.py`), fakes via injected factories.
- Streaming uses SSE frames: each event dict serialized as `data: <json>\n\n`.

---

### Task 1: Web package skeleton, app factory, static serving, launcher

**Files:**
- Modify: `requirements.txt`
- Create: `vantage/web/__init__.py` (empty)
- Create: `vantage/web/app.py`
- Create: `vantage/web/__main__.py`
- Create: `vantage/web/static/index.html` (stub; fleshed out in Task 6)
- Create: `vantage/web/static/app.js` (stub)
- Create: `vantage/web/static/styles.css` (stub)
- Test: `tests/test_web_app.py`

**Interfaces:**
- Produces: `vantage.web.app.create_app(settings=None, conversation_factory=None, refresh_runner=None, portfolio_loader=None) -> fastapi.FastAPI`. Stores deps on `app.state` (`settings`, `conversation_factory`, `refresh_runner`, `portfolio_loader`, `conversation=None`). Serves `GET /` → `index.html` and mounts `/static`.
- Produces: `vantage.web.app._sse(events) -> generator` yielding `f"data: {json.dumps(ev)}\n\n"`.

- [ ] **Step 1: Add dependencies**

In `requirements.txt`, append:

```
fastapi>=0.110
uvicorn[standard]>=0.29
httpx>=0.27
```

Install: `pip install -r requirements.txt` (or `pip install fastapi 'uvicorn[standard]' httpx`).

- [ ] **Step 2: Write the failing test**

Create `tests/test_web_app.py`:

```python
from pathlib import Path
from fastapi.testclient import TestClient
from vantage.settings import Settings
from vantage.web.app import create_app, _sse

def _settings(tmp_path):
    for sub in ("reports", "data", "config", "cache"):
        (tmp_path / sub).mkdir(exist_ok=True)
    return Settings(anthropic_api_key="k", gmail_user="", gmail_app_password="",
                    email_recipient="", model="claude-opus-4-8",
                    portfolio_analysis_path="/nonexistent", project_root=tmp_path,
                    config_dir=tmp_path / "config", data_dir=tmp_path / "data",
                    reports_dir=tmp_path / "reports", cache_dir=tmp_path / "cache")

def test_sse_formats_frames():
    out = list(_sse([{"type": "text", "text": "hi"}, {"type": "done"}]))
    assert out[0] == 'data: {"type": "text", "text": "hi"}\n\n'
    assert out[1] == 'data: {"type": "done"}\n\n'

def test_index_and_static_served(tmp_path):
    app = create_app(settings=_settings(tmp_path))
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Vantage" in r.text
    assert client.get("/static/app.js").status_code == 200
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_web_app.py -v`
Expected: FAIL — `ModuleNotFoundError: vantage.web`.

- [ ] **Step 4: Create the package and stub static files**

`vantage/web/__init__.py`: empty file.

`vantage/web/static/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Vantage</title>
<link rel="stylesheet" href="/static/styles.css"></head>
<body>
  <main id="app"><h1>Vantage</h1></main>
  <script src="/static/app.js"></script>
</body>
</html>
```

`vantage/web/static/app.js`: `// Vantage dashboard — implemented in Task 6`
`vantage/web/static/styles.css`: `/* Vantage dashboard styles — implemented in Task 6 */`

- [ ] **Step 5: Implement the app factory**

`vantage/web/app.py`:

```python
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from vantage.settings import load_settings
from vantage.conversation import Conversation

STATIC_DIR = Path(__file__).parent / "static"

def _sse(events):
    for ev in events:
        yield f"data: {json.dumps(ev)}\n\n"

def create_app(settings=None, conversation_factory=None,
               refresh_runner=None, portfolio_loader=None) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings or load_settings()
    app.state.conversation_factory = conversation_factory or (lambda s: Conversation(s))
    app.state.portfolio_loader = portfolio_loader
    app.state.refresh_runner = refresh_runner
    app.state.conversation = None

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_web_app.py -v`
Expected: PASS (both tests).

- [ ] **Step 7: Add the launcher**

`vantage/web/__main__.py`:

```python
import uvicorn
from vantage.web.app import create_app

def main():
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)

if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Commit**

```bash
git add requirements.txt vantage/web tests/test_web_app.py
git commit -m "feat(web): app factory, static serving, launcher skeleton"
```

---

### Task 2: Artifact readers and overview builder

**Files:**
- Create: `vantage/web/artifacts.py`
- Test: `tests/test_web_artifacts.py`

**Interfaces:**
- Consumes: `vantage.models.SignalSet` (`.load(path)`, `.to_dict()`, `.as_of`, `.signals` of `Signal(ticker, signal_type, value, rank, sector, metrics)`, `.sector_momentum: dict`), `vantage.models.Brief` (`.from_dict`, `.as_of`, `.executive_summary`, `.watchlist`), `vantage.models.PortfolioContext` (`.available`, `.holdings` of `Holding(ticker, name, pct_of_portfolio, sector, current_value, ...)`, `.sector_concentration`, `.note`).
- Produces:
  - `latest_signals(data_dir) -> SignalSet | None`
  - `list_briefs(reports_dir) -> list[dict]` — `[{"as_of": str, "summary": str}]`, newest first
  - `load_brief(reports_dir, as_of) -> Brief | None`
  - `read_brief_html(reports_dir, as_of) -> str | None`
  - `build_overview(signal_set, portfolio, latest_brief) -> dict`

- [ ] **Step 1: Write the failing test**

Create `tests/test_web_artifacts.py`:

```python
import json
from pathlib import Path
from vantage.models import SignalSet, Signal, Brief, PortfolioContext, Holding
from vantage.web import artifacts as art

def _write_signals(data_dir, as_of, signals, momentum):
    SignalSet(as_of=as_of, signals=signals, sector_momentum=momentum).save(
        data_dir / f"signals-{as_of}.json")

def test_latest_signals_picks_newest(tmp_path):
    _write_signals(tmp_path, "2026-06-20", [], {})
    _write_signals(tmp_path, "2026-06-27", [Signal("NVDA", "ret_12m_leader", 1.8, 1)], {})
    ss = art.latest_signals(tmp_path)
    assert ss.as_of == "2026-06-27"
    assert ss.signals[0].ticker == "NVDA"

def test_latest_signals_none_when_empty(tmp_path):
    assert art.latest_signals(tmp_path) is None

def test_list_and_load_briefs(tmp_path):
    b = Brief(as_of="2026-06-27", executive_summary="Summary text.", items=[],
              watchlist=["MU", "AVGO"], challenge="c", what_im_missing="m",
              disclaimer="d")
    (tmp_path / "brief-2026-06-27.json").write_text(json.dumps(b.to_dict()))
    (tmp_path / "brief-2026-06-27.html").write_text("<h1>Brief</h1>")
    listing = art.list_briefs(tmp_path)
    assert listing == [{"as_of": "2026-06-27", "summary": "Summary text."}]
    loaded = art.load_brief(tmp_path, "2026-06-27")
    assert loaded.watchlist == ["MU", "AVGO"]
    assert art.read_brief_html(tmp_path, "2026-06-27") == "<h1>Brief</h1>"
    assert art.load_brief(tmp_path, "2099-01-01") is None

def test_build_overview_shape():
    ss = SignalSet(as_of="2026-06-27",
                   signals=[Signal("NVDA", "ret_12m_leader", 1.8, 1, "Technology"),
                            Signal("XYZ", "volume_spike", 3.1, 0, "Energy")],
                   sector_momentum={"Technology": 0.4, "Energy": -0.1})
    pf = PortfolioContext(available=True,
                          holdings=[Holding("NVDA", "Nvidia", 10, 100,
                                            current_value=1000, pct_of_portfolio=0.5,
                                            sector="Technology")],
                          sector_concentration={"Technology": 0.5})
    brief = Brief("2026-06-27", "exec", [], ["MU"], "c", "m", "d")
    ov = art.build_overview(ss, pf, brief)
    assert ov["signals_as_of"] == "2026-06-27"
    assert ov["top_leaders"][0]["ticker"] == "NVDA"
    assert ov["top_volume_spikes"][0]["ticker"] == "XYZ"
    assert ov["sector_momentum_top"][0]["sector"] == "Technology"
    assert ov["portfolio"]["available"] is True
    assert ov["portfolio"]["top_positions"][0]["ticker"] == "NVDA"
    assert ov["watchlist"] == ["MU"]
    assert ov["latest_brief"]["as_of"] == "2026-06-27"

def test_build_overview_empty():
    ov = art.build_overview(None, PortfolioContext(available=False, note="db down"), None)
    assert ov["signals_as_of"] is None
    assert ov["top_leaders"] == []
    assert ov["portfolio"] == {"available": False, "note": "db down"}
    assert ov["watchlist"] == []
    assert ov["latest_brief"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_artifacts.py -v`
Expected: FAIL — `ModuleNotFoundError: vantage.web.artifacts`.

- [ ] **Step 3: Implement `artifacts.py`**

`vantage/web/artifacts.py`:

```python
import json
from pathlib import Path
from vantage.models import SignalSet, Brief

def latest_signals(data_dir):
    files = sorted(Path(data_dir).glob("signals-*.json"))
    return SignalSet.load(files[-1]) if files else None

def list_briefs(reports_dir):
    out = []
    for p in sorted(Path(reports_dir).glob("brief-*.json"), reverse=True):
        try:
            d = json.loads(p.read_text())
        except (ValueError, OSError):
            continue
        out.append({"as_of": d.get("as_of"),
                    "summary": (d.get("executive_summary") or "")[:280]})
    return out

def load_brief(reports_dir, as_of):
    p = Path(reports_dir) / f"brief-{as_of}.json"
    return Brief.from_dict(json.loads(p.read_text())) if p.exists() else None

def read_brief_html(reports_dir, as_of):
    p = Path(reports_dir) / f"brief-{as_of}.html"
    return p.read_text(encoding="utf-8") if p.exists() else None

def build_overview(signal_set, portfolio, latest_brief):
    leaders, spikes = [], []
    if signal_set:
        for s in signal_set.signals:
            entry = {"ticker": s.ticker, "value": s.value, "sector": s.sector}
            if s.signal_type == "ret_12m_leader":
                leaders.append(entry)
            elif s.signal_type == "volume_spike":
                spikes.append(entry)
    mom = sorted((signal_set.sector_momentum.items() if signal_set else []),
                 key=lambda kv: kv[1], reverse=True)
    if portfolio is not None and portfolio.available:
        top = sorted(portfolio.holdings, key=lambda h: h.pct_of_portfolio or 0,
                     reverse=True)[:8]
        pf = {"available": True, "holdings_count": len(portfolio.holdings),
              "top_positions": [{"ticker": h.ticker, "name": h.name,
                                 "pct": h.pct_of_portfolio, "sector": h.sector}
                                for h in top],
              "sector_concentration": portfolio.sector_concentration}
    else:
        pf = {"available": False, "note": portfolio.note if portfolio else ""}
    return {
        "signals_as_of": signal_set.as_of if signal_set else None,
        "top_leaders": leaders[:5],
        "top_volume_spikes": spikes[:5],
        "sector_momentum_top": [{"sector": k, "value": v} for k, v in mom[:5]],
        "sector_momentum_bottom": [{"sector": k, "value": v} for k, v in mom[-5:][::-1]],
        "portfolio": pf,
        "watchlist": latest_brief.watchlist if latest_brief else [],
        "latest_brief": ({"as_of": latest_brief.as_of,
                          "executive_summary": latest_brief.executive_summary}
                         if latest_brief else None),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_artifacts.py -v`
Expected: PASS (all five tests).

- [ ] **Step 5: Commit**

```bash
git add vantage/web/artifacts.py tests/test_web_artifacts.py
git commit -m "feat(web): artifact readers and overview builder"
```

---

### Task 3: Read-only data API endpoints

**Files:**
- Modify: `vantage/web/app.py`
- Test: `tests/test_web_api.py`

**Interfaces:**
- Consumes: `create_app(..., portfolio_loader=...)` from Task 1; `vantage.web.artifacts` from Task 2.
- Produces endpoints: `GET /api/overview`, `GET /api/signals`, `GET /api/portfolio`, `GET /api/briefs`, `GET /api/briefs/{as_of}`. The portfolio is loaded via `app.state.portfolio_loader` (defaults to `vantage.portfolio_context.load_portfolio_context`) so tests inject a fake.

- [ ] **Step 1: Write the failing test**

Create `tests/test_web_api.py`:

```python
import json
from pathlib import Path
from fastapi.testclient import TestClient
from vantage.settings import Settings
from vantage.models import SignalSet, Signal, Brief, PortfolioContext, Holding
from vantage.web.app import create_app

def _settings(tmp_path):
    for sub in ("reports", "data", "config", "cache"):
        (tmp_path / sub).mkdir(exist_ok=True)
    return Settings(anthropic_api_key="k", gmail_user="", gmail_app_password="",
                    email_recipient="", model="m", portfolio_analysis_path="/x",
                    project_root=tmp_path, config_dir=tmp_path / "config",
                    data_dir=tmp_path / "data", reports_dir=tmp_path / "reports",
                    cache_dir=tmp_path / "cache")

def _seed(s):
    SignalSet("2026-06-27", [Signal("NVDA", "ret_12m_leader", 1.8, 1, "Technology")],
              {"Technology": 0.4}).save(s.data_dir / "signals-2026-06-27.json")
    b = Brief("2026-06-27", "exec summary", [], ["MU"], "c", "m", "d")
    (s.reports_dir / "brief-2026-06-27.json").write_text(json.dumps(b.to_dict()))
    (s.reports_dir / "brief-2026-06-27.html").write_text("<h1>Brief</h1>")

def _client(s, available=True):
    pf = (PortfolioContext(available=True,
                           holdings=[Holding("NVDA", "Nvidia", 10, 100,
                                             current_value=1000, pct_of_portfolio=0.5,
                                             sector="Technology")],
                           sector_concentration={"Technology": 0.5})
          if available else PortfolioContext(available=False, note="db down"))
    return TestClient(create_app(settings=s, portfolio_loader=lambda path: pf))

def test_overview(tmp_path):
    s = _settings(tmp_path); _seed(s)
    r = _client(s).get("/api/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["top_leaders"][0]["ticker"] == "NVDA"
    assert body["portfolio"]["available"] is True
    assert body["watchlist"] == ["MU"]

def test_signals_and_empty(tmp_path):
    s = _settings(tmp_path); _seed(s)
    assert _client(s).get("/api/signals").json()["as_of"] == "2026-06-27"
    s2 = _settings(tmp_path / "empty")
    assert _client(s2).get("/api/signals").json() == {
        "as_of": None, "signals": [], "sector_momentum": {}}

def test_portfolio_unavailable(tmp_path):
    s = _settings(tmp_path)
    body = _client(s, available=False).get("/api/portfolio").json()
    assert body["available"] is False and body["note"] == "db down"

def test_briefs_list_and_fetch_and_404(tmp_path):
    s = _settings(tmp_path); _seed(s)
    c = _client(s)
    assert c.get("/api/briefs").json()[0]["as_of"] == "2026-06-27"
    one = c.get("/api/briefs/2026-06-27").json()
    assert one["brief"]["watchlist"] == ["MU"]
    assert one["html"] == "<h1>Brief</h1>"
    assert c.get("/api/briefs/2099-01-01").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_api.py -v`
Expected: FAIL — endpoints return 404 (not yet defined).

- [ ] **Step 3: Implement the endpoints**

In `vantage/web/app.py`, update imports at top:

```python
from dataclasses import asdict
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from vantage.web import artifacts as art
```

Set the portfolio loader default inside `create_app` (replace the `portfolio_loader` line):

```python
    from vantage.portfolio_context import load_portfolio_context
    app.state.portfolio_loader = portfolio_loader or load_portfolio_context
```

Add these routes inside `create_app`, before `return app`:

```python
    @app.get("/api/overview")
    def overview():
        s = app.state.settings
        ss = art.latest_signals(s.data_dir)
        pf = app.state.portfolio_loader(s.portfolio_analysis_path)
        briefs = art.list_briefs(s.reports_dir)
        latest = art.load_brief(s.reports_dir, briefs[0]["as_of"]) if briefs else None
        return art.build_overview(ss, pf, latest)

    @app.get("/api/signals")
    def signals():
        ss = art.latest_signals(app.state.settings.data_dir)
        return ss.to_dict() if ss else {"as_of": None, "signals": [],
                                         "sector_momentum": {}}

    @app.get("/api/portfolio")
    def portfolio():
        pf = app.state.portfolio_loader(app.state.settings.portfolio_analysis_path)
        return asdict(pf)

    @app.get("/api/briefs")
    def briefs():
        return art.list_briefs(app.state.settings.reports_dir)

    @app.get("/api/briefs/{as_of}")
    def brief(as_of: str):
        s = app.state.settings
        b = art.load_brief(s.reports_dir, as_of)
        if b is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {"brief": b.to_dict(), "html": art.read_brief_html(s.reports_dir, as_of)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_api.py -v`
Expected: PASS (all four tests).

- [ ] **Step 5: Commit**

```bash
git add vantage/web/app.py tests/test_web_api.py
git commit -m "feat(web): read-only data API (overview, signals, portfolio, briefs)"
```

---

### Task 4: Chat SSE endpoint and reset

**Files:**
- Modify: `vantage/web/app.py`
- Test: `tests/test_web_chat.py`

**Interfaces:**
- Consumes: `app.state.conversation_factory(settings) -> object` with `.send(message)` yielding event dicts (the real `Conversation`); `_sse` from Task 1.
- Produces: `POST /api/chat` (body `{"message": str}`) → `text/event-stream` of the conversation events; `POST /api/chat/new` → `{"ok": True}` after discarding the current conversation. The conversation is created lazily on first chat and cached on `app.state.conversation`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_web_chat.py`:

```python
from pathlib import Path
from fastapi.testclient import TestClient
from vantage.settings import Settings
from vantage.web.app import create_app

def _settings(tmp_path):
    for sub in ("reports", "data", "config", "cache"):
        (tmp_path / sub).mkdir(exist_ok=True)
    return Settings(anthropic_api_key="k", gmail_user="", gmail_app_password="",
                    email_recipient="", model="m", portfolio_analysis_path="/x",
                    project_root=tmp_path, config_dir=tmp_path / "config",
                    data_dir=tmp_path / "data", reports_dir=tmp_path / "reports",
                    cache_dir=tmp_path / "cache")

class _FakeConversation:
    def send(self, message):
        yield {"type": "text", "text": f"echo: {message}"}
        yield {"type": "done"}

def test_chat_streams_sse(tmp_path):
    created = []
    def factory(s):
        c = _FakeConversation(); created.append(c); return c
    app = create_app(settings=_settings(tmp_path), conversation_factory=factory)
    client = TestClient(app)
    r = client.post("/api/chat", json={"message": "what's MU?"})
    assert r.status_code == 200
    assert 'data: {"type": "text", "text": "echo: what\'s MU?"}' in r.text
    assert 'data: {"type": "done"}' in r.text
    # second message reuses the same conversation
    client.post("/api/chat", json={"message": "again"})
    assert len(created) == 1

def test_chat_new_resets(tmp_path):
    created = []
    def factory(s):
        c = _FakeConversation(); created.append(c); return c
    client = TestClient(create_app(settings=_settings(tmp_path),
                                   conversation_factory=factory))
    client.post("/api/chat", json={"message": "one"})
    assert client.post("/api/chat/new").json() == {"ok": True}
    client.post("/api/chat", json={"message": "two"})
    assert len(created) == 2  # new conversation built after reset
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_chat.py -v`
Expected: FAIL — `/api/chat` returns 404.

- [ ] **Step 3: Implement the chat endpoints**

In `vantage/web/app.py`, add to the imports: `from fastapi import FastAPI, Request` and `from fastapi.responses import StreamingResponse` (merge with existing response imports).

Add inside `create_app`, before `return app`:

```python
    def _get_conversation():
        if app.state.conversation is None:
            app.state.conversation = app.state.conversation_factory(app.state.settings)
        return app.state.conversation

    @app.post("/api/chat")
    async def chat(request: Request):
        body = await request.json()
        conv = _get_conversation()
        return StreamingResponse(_sse(conv.send(body.get("message", ""))),
                                 media_type="text/event-stream")

    @app.post("/api/chat/new")
    def chat_new():
        app.state.conversation = None
        return {"ok": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_chat.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add vantage/web/app.py tests/test_web_chat.py
git commit -m "feat(web): streaming chat SSE endpoint and reset"
```

---

### Task 5: Refresh pipeline and SSE endpoint

**Files:**
- Create: `vantage/web/pipeline.py`
- Modify: `vantage/web/app.py`
- Test: `tests/test_web_refresh.py`

**Interfaces:**
- Consumes: `vantage.universe.load_universe(path)`, `vantage.data_ingest.fetch_market_data(tickers, cache_dir) -> MarketData`, `vantage.screener.run_screener(market_data) -> SignalSet`, `vantage.portfolio_context.load_portfolio_context(pa_path)`.
- Produces: `vantage.web.pipeline.run_refresh(settings, _market_data_fn=None, _portfolio_fn=None)` — a generator yielding `{"type":"progress","stage":str}` events, then `{"type":"done","as_of":str}`, or `{"type":"error","message":str}` on failure. Writes the new signals to `settings.data_dir / f"signals-{as_of}.json"`.
- Produces: `POST /api/refresh` → `text/event-stream` driven by `app.state.refresh_runner(settings)` (defaults to `run_refresh`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_web_refresh.py`:

```python
from pathlib import Path
from fastapi.testclient import TestClient
from vantage.settings import Settings
from vantage.models import MarketData
from vantage.web.app import create_app
from vantage.web.pipeline import run_refresh
import pandas as pd

def _settings(tmp_path):
    for sub in ("reports", "data", "config", "cache"):
        (tmp_path / sub).mkdir(exist_ok=True)
    (tmp_path / "config" / "universe.txt").write_text("NVDA\nMU\n")
    return Settings(anthropic_api_key="k", gmail_user="", gmail_app_password="",
                    email_recipient="", model="m", portfolio_analysis_path="/x",
                    project_root=tmp_path, config_dir=tmp_path / "config",
                    data_dir=tmp_path / "data", reports_dir=tmp_path / "reports",
                    cache_dir=tmp_path / "cache")

def _fake_market_data(tickers, cache_dir):
    idx = range(300)
    prices = {t: pd.Series([100 + i for i in idx]) for t in tickers}
    volumes = {t: pd.Series([1000 for _ in idx]) for t in tickers}
    sectors = {t: "Technology" for t in tickers}
    return MarketData(as_of="2026-06-27", prices=prices, volumes=volumes, sectors=sectors)

def test_run_refresh_emits_stages_and_writes(tmp_path):
    s = _settings(tmp_path)
    events = list(run_refresh(s, _market_data_fn=_fake_market_data,
                              _portfolio_fn=lambda p: None))
    stages = [e["stage"] for e in events if e["type"] == "progress"]
    assert stages == ["fetching market data", "screening", "loading portfolio"]
    assert events[-1] == {"type": "done", "as_of": "2026-06-27"}
    assert (s.data_dir / "signals-2026-06-27.json").exists()

def test_run_refresh_error(tmp_path):
    s = _settings(tmp_path)
    def boom(tickers, cache_dir):
        raise RuntimeError("network down")
    events = list(run_refresh(s, _market_data_fn=boom))
    assert events[-1] == {"type": "error", "message": "network down"}

def test_refresh_endpoint_streams(tmp_path):
    runner = lambda s: iter([{"type": "progress", "stage": "x"}, {"type": "done"}])
    client = TestClient(create_app(settings=_settings(tmp_path), refresh_runner=runner))
    r = client.post("/api/refresh")
    assert r.status_code == 200
    assert 'data: {"type": "progress", "stage": "x"}' in r.text
    assert 'data: {"type": "done"}' in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_refresh.py -v`
Expected: FAIL — `ModuleNotFoundError: vantage.web.pipeline`.

- [ ] **Step 3: Implement `pipeline.py`**

`vantage/web/pipeline.py`:

```python
import logging
from vantage.universe import load_universe
from vantage.data_ingest import fetch_market_data
from vantage.screener import run_screener
from vantage.portfolio_context import load_portfolio_context

logger = logging.getLogger(__name__)

def run_refresh(settings, _market_data_fn=None, _portfolio_fn=None):
    md_fn = _market_data_fn or (lambda tickers, cache_dir:
                                fetch_market_data(tickers, cache_dir))
    pf_fn = _portfolio_fn or (lambda pa_path: load_portfolio_context(pa_path))
    try:
        yield {"type": "progress", "stage": "fetching market data"}
        tickers = load_universe(settings.config_dir / "universe.txt")
        market_data = md_fn(tickers, settings.cache_dir)
        yield {"type": "progress", "stage": "screening"}
        signal_set = run_screener(market_data)
        signal_set.save(settings.data_dir / f"signals-{signal_set.as_of}.json")
        yield {"type": "progress", "stage": "loading portfolio"}
        pf_fn(settings.portfolio_analysis_path)
        yield {"type": "done", "as_of": signal_set.as_of}
    except Exception as e:
        logger.warning("refresh failed: %s", e)
        yield {"type": "error", "message": str(e)}
```

- [ ] **Step 4: Wire the refresh endpoint**

In `vantage/web/app.py`, set the refresh runner default inside `create_app` (replace the `refresh_runner` line):

```python
    from vantage.web.pipeline import run_refresh
    app.state.refresh_runner = refresh_runner or run_refresh
```

Add inside `create_app`, before `return app`:

```python
    @app.post("/api/refresh")
    def refresh():
        return StreamingResponse(_sse(app.state.refresh_runner(app.state.settings)),
                                 media_type="text/event-stream")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_web_refresh.py -v`
Expected: PASS (all three tests).

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: PASS — all pre-existing tests plus the new web tests.

- [ ] **Step 7: Commit**

```bash
git add vantage/web/pipeline.py vantage/web/app.py tests/test_web_refresh.py
git commit -m "feat(web): quantitative refresh pipeline and SSE endpoint"
```

---

### Task 6: Frontend — layout B, editorial style, chat + refresh

**Files:**
- Modify: `vantage/web/static/index.html`
- Modify: `vantage/web/static/styles.css`
- Modify: `vantage/web/static/app.js`

**Interfaces:**
- Consumes the API from Tasks 3–5: `GET /api/overview`, `/api/signals`, `/api/portfolio`, `/api/briefs`, `/api/briefs/{as_of}`; `POST /api/chat` (SSE), `/api/chat/new`, `/api/refresh` (SSE).
- No automated tests (intentionally logic-light vanilla JS). Verified manually — see the verification checklist at the end of this task. Frontend polish within the calm-editorial language may use the `frontend-design` skill.

- [ ] **Step 1: Write `index.html` (layout B shell)**

`vantage/web/static/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Vantage</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <div class="shell">
    <section class="data-col">
      <header class="topbar">
        <h1>Vantage</h1>
        <button id="refresh-btn">Refresh data</button>
        <span id="refresh-status" class="status"></span>
      </header>
      <div id="overview" class="panel"></div>
      <div id="portfolio" class="panel"></div>
      <div id="signals" class="panel"></div>
      <div id="briefs" class="panel"></div>
    </section>
    <aside class="chat-col">
      <div class="chat-head"><span>Analyst</span>
        <button id="chat-new">New conversation</button></div>
      <div id="chat-log" class="chat-log"></div>
      <form id="chat-form" class="chat-form">
        <textarea id="chat-input" rows="2" placeholder="Ask the analyst…"></textarea>
        <button type="submit">Send</button>
      </form>
    </aside>
  </div>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `styles.css` (calm editorial)**

`vantage/web/static/styles.css`:

```css
:root {
  --bg: #15131a; --panel: #1c1a24; --ink: #e8e3ef; --muted: #9b8fb0;
  --accent: #8c7bb5; --line: #2a2733; --up: #7fd6a8; --down: #e08a8a;
  --serif: Georgia, "Times New Roman", serif;
  --sans: system-ui, -apple-system, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
       font-family: var(--sans); font-size: 15px; }
.shell { display: grid; grid-template-columns: 1fr 380px; height: 100vh; }
.data-col { overflow-y: auto; padding: 24px 28px; }
.chat-col { border-left: 1px solid var(--line); display: flex;
            flex-direction: column; background: var(--panel); }
.topbar { display: flex; align-items: center; gap: 14px; margin-bottom: 20px; }
.topbar h1 { font-family: var(--serif); font-weight: 600; margin: 0; flex: 0 0 auto; }
.status { color: var(--muted); font-size: 13px; }
button { background: var(--accent); color: #14121a; border: 0; border-radius: 7px;
         padding: 7px 13px; font-weight: 600; cursor: pointer; }
button:hover { filter: brightness(1.08); }
.panel { background: var(--panel); border: 1px solid var(--line);
         border-radius: 10px; padding: 16px 18px; margin-bottom: 16px; }
.panel h2 { font-family: var(--serif); font-weight: 600; font-size: 18px;
            margin: 0 0 12px; }
.label { text-transform: uppercase; letter-spacing: 1.5px; font-size: 11px;
         color: var(--muted); margin: 14px 0 6px; }
.row { display: flex; justify-content: space-between; padding: 4px 0;
       border-bottom: 1px solid var(--line); font-size: 14px; }
.row:last-child { border-bottom: 0; }
.up { color: var(--up); } .down { color: var(--down); }
.note { color: var(--muted); font-style: italic; }
.chat-head { display: flex; justify-content: space-between; align-items: center;
             padding: 14px 16px; border-bottom: 1px solid var(--line);
             font-family: var(--serif); }
.chat-log { flex: 1; overflow-y: auto; padding: 16px; }
.msg { margin-bottom: 14px; line-height: 1.5; white-space: pre-wrap; }
.msg.user { color: var(--ink); }
.msg.analyst { background: rgba(140,123,181,.14); border-radius: 10px;
               padding: 10px 12px; }
.msg.tool { color: var(--muted); font-size: 13px; font-style: italic; }
.msg.error { color: var(--down); }
.chat-form { display: flex; gap: 8px; padding: 12px; border-top: 1px solid var(--line); }
.chat-form textarea { flex: 1; resize: none; background: var(--bg);
  color: var(--ink); border: 1px solid var(--line); border-radius: 7px; padding: 8px;
  font-family: var(--sans); }
```

- [ ] **Step 3: Write `app.js` (render + SSE chat + refresh)**

`vantage/web/static/app.js`:

```javascript
const $ = (id) => document.getElementById(id);
const pct = (v) => (v == null ? "—" : (v * 100).toFixed(1) + "%");
const cls = (v) => (v >= 0 ? "up" : "down");

async function getJSON(url) { const r = await fetch(url); return r.json(); }

function rows(items, render) {
  return items.length ? items.map(render).join("") : '<div class="note">None</div>';
}

async function loadOverview() {
  const o = await getJSON("/api/overview");
  $("overview").innerHTML = `<h2>Overview</h2>
    <div class="note">Signals as of ${o.signals_as_of || "—"}</div>
    <div class="label">Top 12-month leaders</div>
    ${rows(o.top_leaders, (l) => `<div class="row"><span>${l.ticker}</span>
      <span class="${cls(l.value)}">${pct(l.value)}</span></div>`)}
    <div class="label">Sector momentum</div>
    ${rows(o.sector_momentum_top, (m) => `<div class="row"><span>${m.sector}</span>
      <span class="${cls(m.value)}">${pct(m.value)}</span></div>`)}
    ${o.latest_brief ? `<div class="label">Latest brief — ${o.latest_brief.as_of}</div>
      <div>${o.latest_brief.executive_summary}</div>` : ""}`;
}

async function loadPortfolio() {
  const p = await getJSON("/api/portfolio");
  if (!p.available) {
    $("portfolio").innerHTML =
      `<h2>Portfolio</h2><div class="note">Unavailable: ${p.note || "—"}</div>`;
    return;
  }
  $("portfolio").innerHTML = `<h2>Portfolio</h2>
    <div class="label">Top positions</div>
    ${rows(p.holdings.slice().sort((a, b) => (b.pct_of_portfolio || 0) -
        (a.pct_of_portfolio || 0)).slice(0, 8),
      (h) => `<div class="row"><span>${h.ticker} — ${h.name || ""}</span>
        <span>${pct(h.pct_of_portfolio)}</span></div>`)}`;
}

async function loadSignals() {
  const s = await getJSON("/api/signals");
  $("signals").innerHTML = `<h2>Signals</h2>
    ${rows(s.signals, (sig) => `<div class="row">
      <span>${sig.ticker} · ${sig.signal_type}</span>
      <span class="${cls(sig.value)}">${sig.signal_type === "volume_spike"
        ? sig.value.toFixed(1) + "×" : pct(sig.value)}</span></div>`)}`;
}

async function loadBriefs() {
  const briefs = await getJSON("/api/briefs");
  $("briefs").innerHTML = `<h2>Briefs</h2>
    ${rows(briefs, (b) => `<div class="row"><span>${b.as_of}</span>
      <span class="note">${b.summary.slice(0, 60)}…</span></div>`)}`;
}

function loadData() { loadOverview(); loadPortfolio(); loadSignals(); loadBriefs(); }

// --- SSE helper: POST a JSON body, invoke onEvent per parsed event dict ---
async function streamPost(url, body, onEvent) {
  const resp = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop();
    for (const f of frames) {
      const line = f.trim();
      if (line.startsWith("data:")) onEvent(JSON.parse(line.slice(5).trim()));
    }
  }
}

// --- Chat ---
function addMsg(kind, text) {
  const el = document.createElement("div");
  el.className = "msg " + kind;
  el.textContent = text;
  $("chat-log").appendChild(el);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
  return el;
}

$("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("chat-input");
  const msg = input.value.trim();
  if (!msg) return;
  addMsg("user", msg);
  input.value = "";
  let bubble = null;
  await streamPost("/api/chat", { message: msg }, (ev) => {
    if (ev.type === "text") {
      if (!bubble) bubble = addMsg("analyst", "");
      bubble.textContent += ev.text;
      $("chat-log").scrollTop = $("chat-log").scrollHeight;
    } else if (ev.type === "tool_use") {
      addMsg("tool", `[looking up via ${ev.name}(${JSON.stringify(ev.input || {})})]`);
      bubble = null;
    } else if (ev.type === "error") {
      addMsg("error", `[error: ${ev.message}]`);
    }
  });
});

$("chat-new").addEventListener("click", async () => {
  await fetch("/api/chat/new", { method: "POST" });
  $("chat-log").innerHTML = "";
});

// --- Refresh ---
$("refresh-btn").addEventListener("click", async () => {
  const btn = $("refresh-btn");
  btn.disabled = true;
  await streamPost("/api/refresh", {}, (ev) => {
    if (ev.type === "progress") $("refresh-status").textContent = ev.stage + "…";
    else if (ev.type === "error") $("refresh-status").textContent = "error: " + ev.message;
    else if (ev.type === "done") { $("refresh-status").textContent = "updated"; loadData(); }
  });
  btn.disabled = false;
});

loadData();
```

- [ ] **Step 4: Manual verification**

Run: `python -m vantage.web` and open `http://127.0.0.1:8000`.

Confirm:
1. Two-column layout — data on the left, analyst chat docked right; editorial styling (serif headings, soft dark, muted violet accent).
2. With existing artifacts present (run `python run_weekly.py --no-email` first if `data/`/`reports/` are empty): Overview, Portfolio, Signals, Briefs panels populate. With none present, panels show "None"/"Unavailable" without errors.
3. Chat: type a question → analyst text streams token-by-token; a `[looking up via …]` line appears on tool/web-search use. "New conversation" clears the log.
4. Refresh: click "Refresh data" → status cycles through "fetching market data…", "screening…", "loading portfolio…", "updated", then panels reload. (This makes a real market-data fetch — it takes minutes.)

- [ ] **Step 5: Update the README**

Add a "Web dashboard" section to `README.md` documenting `python -m vantage.web`, the `127.0.0.1:8000` URL, that it reads the latest artifacts, that Refresh re-runs the quantitative pipeline, and that it requires `ANTHROPIC_API_KEY` for chat. Keep it consistent with the existing README's tone and the genericized `~` paths.

- [ ] **Step 6: Commit**

```bash
git add vantage/web/static README.md
git commit -m "feat(web): editorial dashboard frontend (chat + data views + refresh)"
```

---

## Self-Review Notes

- **Spec coverage:** §3 architecture → Task 1; §4 endpoints → Tasks 3 (data), 4 (chat), 5 (refresh); §4 overview payload → Task 2 `build_overview`; §5 data flow → Tasks 3/6; §6 SSE-over-POST → `_sse` (Task 1) + `streamPost` (Task 6); §7 conversation state → Task 4; §8 error/empty states → empty-state tests (Tasks 2/3), portfolio-unavailable (Task 3), chat error (engine, surfaced in Task 6), refresh error (Task 5); §9 visual language → Task 6; §10 testing → tests in Tasks 1–5; §11 deps → Task 1; §12 out-of-scope respected (no email/brief-gen endpoints). 
- **Deferred from spec:** §7's optional transcript-on-reset is intentionally NOT built in v1 (reset only clears) to keep scope tight — noted as a follow-up.
- **Type consistency:** event dicts use `type`/`text`/`name`/`input`/`message`/`stage`/`as_of` consistently across `pipeline.py`, `app.py`, tests, and `app.js`. `build_overview` keys match between Task 2 impl/test and Task 6 consumer. `create_app` keyword args (`settings`, `conversation_factory`, `refresh_runner`, `portfolio_loader`) are consistent across Tasks 1/3/4/5.
```
