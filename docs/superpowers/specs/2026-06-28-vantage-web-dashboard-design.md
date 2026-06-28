# Vantage Web Dashboard — Design Spec

**Date:** 2026-06-28
**Status:** Approved (pending spec review)
**Feature:** A local, single-user web dashboard for Vantage — the conversational
analyst plus read views of signals, portfolio, and briefs.

This is the first of two remaining Vantage follow-ups (web UI, then daily alerts).
Each gets its own spec → plan → build cycle. This spec covers the web UI only.

## 1. Goal & context

Vantage already has a working analysis engine: a streaming conversational analyst
(`vantage/conversation.py`, `Conversation.send()` yielding an event stream), a
deterministic screener, a portfolio-context adapter onto the Wake project, and a
weekly brief pipeline that writes artifacts to `reports/` and `data/`.

The dashboard puts a browser surface on top of that engine. It is **transport +
presentation**: it reuses the existing analysis code unchanged and adds no new
analytical logic. The centerpiece is the analyst chat; the data views give it
context to talk about.

## 2. Locked decisions

- **Scope:** Full dashboard — analyst chat + brief viewer + live data views
  (signals/screener, portfolio context, watchlist).
- **Deployment:** Local-only, single user. No auth, no public hosting. Secrets
  stay in `.env`. Binds `127.0.0.1`.
- **Backend:** FastAPI.
- **Frontend:** No-build vanilla HTML + JS + CSS served by FastAPI. No Node, no
  build step. Project stays one-command, pure-Python.
- **Layout (B):** Scrollable overview/data column on the left, analyst chat
  docked persistently on the right.
- **Data strategy:** Render the latest saved artifacts on load; a **Refresh**
  button re-runs the quantitative pipeline on demand with streamed progress.
- **Visual style:** Calm editorial — soft dark background, serif headings,
  generous spacing, a muted accent, green/red reserved for figures.

## 3. Architecture & run model

New subpackage `vantage/web/`. Launched with **`python -m vantage.web`**, which
starts uvicorn on `127.0.0.1:8000`. FastAPI serves both the static SPA and a
small JSON/SSE API from one process.

```
vantage/web/
  __init__.py
  __main__.py        # uvicorn launcher: python -m vantage.web
  app.py             # FastAPI app: routes, SSE helpers, holds the single Conversation (kept thin)
  artifacts.py       # pure functions: locate/load latest signals, list/load briefs, build overview summary
  pipeline.py        # refresh job: data_ingest -> screener (+ portfolio reload), yields progress stages
  static/
    index.html       # the SPA shell (layout B)
    app.js           # fetch/render panels + SSE chat + SSE refresh
    styles.css       # calm-editorial design language
```

`artifacts.py` and `pipeline.py` hold the non-HTTP logic so they are unit-testable
without a server. `app.py` stays a thin routing/streaming layer.

## 4. API surface

All endpoints are local and unauthenticated.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serve `index.html` |
| GET | `/static/*` | Serve `app.js`, `styles.css` |
| GET | `/api/overview` | Assembled summary (see below) |
| GET | `/api/signals` | Full signals table from latest `data/signals-*.json` |
| GET | `/api/portfolio` | Holdings + sector exposure via `load_portfolio_context()` |
| GET | `/api/briefs` | List of available briefs (date + summary) |
| GET | `/api/briefs/{date}` | One brief — rendered HTML + structured JSON |
| POST | `/api/chat` | Body `{message}`; SSE stream of `Conversation.send()` events |
| POST | `/api/chat/new` | Reset the conversation; optionally save transcript |
| POST | `/api/refresh` | Re-run quantitative pipeline; SSE stream of progress stages |

**`/api/overview` payload** assembles, from saved artifacts + the (fast) portfolio
loader:
- top signal leaders/laggards and sector momentum (from latest signals),
- portfolio snapshot: holdings count, top positions, sector exposure,
- current watchlist (from the latest brief),
- latest-brief metadata (date, executive-summary excerpt).

## 5. Data flow

1. Browser loads the SPA → `app.js` calls `/api/overview` (and section endpoints
   as panels mount) → renders the left column in the editorial style.
2. **Chat:** user message → `POST /api/chat` → server drives `conv.send()` →
   `text` / `tool_use` / `error` / `done` events are forwarded over SSE → `app.js`
   appends streaming text and tool/web-search indicators live.
3. **Refresh:** Refresh button → `POST /api/refresh` → `pipeline.py` runs
   `data_ingest → screener` and reloads portfolio, yielding coarse progress
   stages (e.g. "fetching market data", "screening", "loading portfolio",
   "done") over SSE → on `done`, `app.js` re-fetches `/api/overview`,
   `/api/signals`, `/api/portfolio`. Old data stays on screen until then.

The screener, portfolio loader, conversation engine, and brief artifacts are all
reused as-is.

## 6. Streaming transport

Chat and refresh both stream via **SSE over `POST`** (FastAPI
`StreamingResponse` with `media_type="text/event-stream"`; the browser reads it
with `fetch` + a `ReadableStream` reader, since `EventSource` is GET-only). Each
event is one `data: <json>\n\n` frame mirroring the engine's event dicts. The
chat reuses the exact event shapes already emitted by `Conversation.send()`.

## 7. Conversation state

Single-user → one server-side `Conversation` instance per process, created lazily
on first chat. `POST /api/chat/new` discards it and starts fresh; on reset it
optionally writes a transcript to `reports/chat-*.md`, mirroring `chat.py`. Chat
history is in-memory and does not survive a server restart — acceptable for v1.
(Multiple browser tabs share the one conversation; fine for a single local user.)

## 8. Error & empty states

- **No artifacts yet** (fresh checkout, pipeline never run): data endpoints return
  empty-state payloads; UI shows "No data yet — run a refresh or the weekly
  pipeline."
- **Wake DB unreachable:** `/api/portfolio` and the portfolio part of
  `/api/overview` return a market-wide-only state (mirrors existing pipeline
  fallback); UI shows a notice instead of erroring.
- **Chat / stream / API-key errors:** the engine already yields `{type: error}`;
  SSE forwards it; UI renders an inline error bubble and history stays valid for
  the next message (the engine already balances history on error).
- **Refresh failure:** the progress stream emits an error stage; previously
  loaded data remains on screen.

## 9. Visual design language (calm editorial)

- Soft dark background (not pure black), warm-neutral text.
- Serif headings (e.g. Georgia/served system serif); sans-serif body.
- Generous spacing and clear section labels (small uppercase).
- A single muted accent (desaturated violet) for interactive/active elements.
- Green/red reserved strictly for figures (returns, deltas).
- Chat bubbles: analyst messages set apart with the accent; user messages plain.
- Desktop-first; not optimized for mobile in v1.

Frontend implementation will use the `frontend-design` skill for execution-level
polish within this language.

## 10. Testing

Use FastAPI `TestClient` and the dependency-injection seams the suite already
relies on (`_conversation`, fake `settings`, injected `_market_data_fn` /
`_portfolio_fn`). No live network or DB in tests, consistent with the existing
suite.

- `artifacts.py`: load latest signals / list+load briefs / build overview against
  temp dirs seeded with sample JSON; empty-dir case.
- `pipeline.py`: refresh stages with injected fake market-data + screener; error
  path.
- Endpoints: happy path + empty-state for `/api/overview`, `/api/signals`,
  `/api/portfolio`, `/api/briefs[/{date}]`.
- Chat SSE: a fake `Conversation` whose `send()` yields canned
  text/tool_use/error/done events; assert the SSE frames match (mirrors
  `test_chat.py`).
- Refresh SSE: assert progress stages stream and a failure surfaces as an error
  stage.
- A smoke test that `/` serves the SPA shell.

No JS test harness — the frontend is intentionally logic-light.

## 11. Dependencies

Add to `requirements.txt`: `fastapi`, `uvicorn[standard]`. Nothing else.

## 12. Out of scope (v1 — YAGNI)

- Authentication / login (local-only single user).
- Multi-user or persistent-across-restart chat sessions.
- **Generating or emailing briefs from the UI** — the brief pipeline (the slow,
  paid analyst call + email) stays in `run_weekly` / cron. The web app never
  sends email.
- Editing `universe.txt` / `interests.yaml` from the browser.
- Mobile-responsive layout.

## 13. Follow-ups (noted, not built here)

- Trigger a full brief generation from the UI (long-running, paid; needs its own
  progress/streaming and probably a confirmation).
- The second remaining Vantage feature — daily alerts — is a separate spec.
