# Conversational Analyst — Design

**Date:** 2026-06-27
**Status:** Design — pending user review
**Project root:** `/home/kineticrick/code/python/market_insights`

## 1. Purpose

Turn the radar from a one-way weekly newsletter into an interactive partner the
user can argue with about their portfolio and the market. It reuses the
existing analyst's challenge-and-coach persona and the user's real context
(portfolio, latest signals, interests, latest brief), and can fetch exact
quantitative data on demand so its claims are grounded, not fabricated.

This is the "conversational analyst" mode the original radar spec anticipated
as a future capability (the one-shot analyst was built to be reusable for it).

### Success criteria
- The user can hold a multi-turn conversation in the terminal about their
  portfolio and the market, and the analyst pushes back on their reasoning
  (the same challenge-and-coach voice as the weekly brief).
- When asked for specific numbers (a ticker's trailing returns/volume, a
  re-run screen), the analyst returns **real values from the project's own
  data**, not guesses.
- The conversation engine is interface-agnostic: a future web UI can drive it
  without re-architecting (it consumes an event stream, the terminal is just
  one consumer).

### Motivating decision
Chosen capability model is **hybrid**: portfolio + latest signals + interests
preloaded, `web_search` always available, plus a small set of custom tools for
on-demand depth. Rationale: grounding/trust matters for an investing tool
(preload-only risks fabricated figures); full-agentic is over-built for a
single user. Interface: terminal REPL now, on a web-ready engine (a full web UI
is a deliberately deferred, larger separate project).

## 2. Architecture

Interface-agnostic **conversation engine** + a thin terminal interface. New
units:

```
radar/persona.py        analyst challenge-&-coach instructions, extracted so both
                        the one-shot brief and the conversation share one source.
radar/chat_tools.py     custom tools the model can call live (definitions + impls):
                          • get_ticker_metrics(ticker)
                          • run_screen(...)
radar/conversation.py   Conversation engine (web-ready; yields events, never prints).
chat.py                 thin terminal REPL — one consumer of the engine.
```

Existing units reused unchanged: `settings`, `models`, `portfolio_context`,
`data_ingest`, `screener`, `universe`, and `analyst` (which gains its persona
text from `persona.py`).

### Determinism / coupling
The custom tools reuse the deterministic `data_ingest` + `screener` code, so
quantitative answers are real. Only `conversation.py` and `analyst.py` are
non-deterministic (LLM). `conversation.py` does not import `portfolio_analysis`
directly — it goes through `portfolio_context`.

## 3. The conversation engine (`radar/conversation.py`)

The central, web-ready unit.

### Construction
`Conversation(settings, _client=None, _context=None)`:
- Loads context (see §5) and builds the system prompt = persona (§6) + a
  rendered context block + a note that the custom tools exist + the
  research-aid disclaimer.
- Initializes an empty message history.
- `_client` (injectable Anthropic client) and `_context` (injectable loaded
  context) are test seams — the engine is unit-tested without network/DB/API.

### The `send` seam (the web-ready interface)
`send(user_message: str) -> Iterator[Event]`:
- Appends the user message to history.
- Runs the Claude turn with streaming + tools; drives the **tool loop**:
  stream the assistant turn, and if it requests tool use, execute the
  tool(s), append the `tool_use`/`tool_result` blocks to history, and continue
  until the turn ends (`stop_reason == "end_turn"`).
- **Yields structured events** as they occur; it never prints. Event shapes:
  - `{"type": "text", "text": <delta>}` — streamed assistant text.
  - `{"type": "tool_use", "name": <tool>, "input": <dict>}` — a tool call (for
    UI to show "looking up MU…").
  - `{"type": "error", "message": <str>}` — a recoverable error to surface.
  - `{"type": "done"}` — the turn is complete.
- Conversation state (the message history, including tool blocks) persists
  across `send()` calls, so it is genuinely multi-turn.

The terminal REPL renders these events to stdout; a future web backend
serializes the same events to SSE. This event contract is the decoupling seam.

### Model / API
`settings.model` (`claude-opus-4-8`), `thinking={"type":"adaptive"}`,
streaming via `client.messages.stream`, `tools = [web_search_20260209] +
custom tool defs`. No `temperature`/`top_p`/`top_k`/`budget_tokens`. Assistant
turns (including `tool_use`/`tool_result` content) are appended to history each
turn so the multi-turn context is preserved.

## 4. Custom tools (`radar/chat_tools.py`)

Each tool is `(json_schema_definition, python_impl)`. Implementations reuse
existing code so results are real and the module stays thin.

- **`get_ticker_metrics(ticker)`** → `{ticker, ret_1m, ret_3m, ret_6m, ret_12m,
  volume_ratio, sector}`. Fetches that single ticker via
  `data_ingest.fetch_market_data([ticker], …)` and computes metrics with the
  `screener` helpers (`_trailing_return`, `_volume_ratio`). On failure returns
  an error result (the engine marks the `tool_result` `is_error`).
- **`run_screen(return_leader_threshold?, volume_spike_ratio?,
  exclude_asset_types?)`** → a compact summary of the resulting `SignalSet`
  (top leaders with values, volume spikes, sector momentum). Reuses
  `load_universe` + `fetch_market_data` + `run_screener` with the supplied
  overrides; `exclude_asset_types` filters tickers by the portfolio/sector
  asset-type where known (best-effort; documented).

Both rely on the long-lived caches already in `data_ingest`, so repeated calls
in a session are cheap.

`chat_tools` exposes: `TOOL_DEFINITIONS` (the JSON schemas passed to the API)
and `dispatch(name, input, settings) -> dict` (executes the named tool). This
keeps the engine's tool loop generic.

## 5. Context loading

A `load_chat_context(settings, _portfolio_fn=None) -> ChatContext` helper (in
`conversation.py`) gathers:
- **Portfolio** — live `PortfolioContext` (via `portfolio_context`).
- **Latest signals** — newest `data/signals-*.json` parsed to a `SignalSet`
  (or none, noted).
- **Interests** — `config/interests.yaml` (or `{}`).
- **Latest brief** — newest `reports/brief-*.json` parsed to a `Brief` (or
  none, noted) so the user can reference "this week's brief."

`ChatContext.render() -> str` produces the context block embedded in the system
prompt. Every piece is optional; missing pieces are noted in the rendered
context rather than being fatal (e.g. "No saved signals yet — suggest running
the weekly pipeline.").

## 6. Persona reuse (`radar/persona.py`)

Extract the analyst's challenge-and-coach instructions (currently inline in
`analyst.py`'s `_INSTRUCTIONS`) into `persona.py` as a shared constant
(`ANALYST_PERSONA` — the role, the five analytical jobs, and the
evidence-based-challenge mandate). `analyst.generate_brief` keeps its
JSON-output instruction by composing `ANALYST_PERSONA` + the brief's
output-format text; the conversation builds a **conversational** system prompt
= `ANALYST_PERSONA` + context block + tool note + disclaimer (no JSON
constraint — free-form dialogue). This keeps one source of truth for the voice.

## 7. Terminal REPL (`chat.py`)

A thin consumer (~30–40 lines):
- Instantiate `Conversation(load_settings())`.
- Loop: print a prompt, read a line (`input()`), `for event in conv.send(line):`
  render — stream `text` deltas inline, show a dim "[looking up MU…]" for
  `tool_use`, print errors.
- Exit on `exit`/`quit`/EOF; on exit, write a dated transcript to
  `reports/chat-<UTC-timestamp>.md`.
- `main(argv)` wraps the loop for testability (like `run_weekly.main`).

## 8. Error handling

- Tool execution errors → returned as `tool_result` with `is_error: true` so
  the model can adjust; also surfaced as an `error` event for visibility.
- API/streaming errors in `send()` → caught, yielded as an `error` event, and
  the turn ends cleanly; the REPL stays alive for the next message.
- Missing context (no DB, no signals) → noted in the context block; the chat
  still runs (degraded), consistent with the rest of the project.

## 9. Persistence

Fresh conversation each launch, primed with current context. On exit a dated
Markdown transcript is written to `reports/chat-<timestamp>.md`. No
cross-session thread resume — that rides along with the future web UI.

## 10. Testing

- **Engine** (`conversation.py`): with an injected fake Anthropic client that
  scripts a tool-use turn then a final turn, assert `send()` executes the
  custom tool, appends the tool blocks, and yields the expected event sequence
  (`tool_use` → `text` → `done`); assert multi-turn history is preserved across
  two `send()` calls.
- **Context loading**: newest-file selection among multiple
  `signals-*`/`brief-*`; graceful when each is absent (injected `_portfolio_fn`,
  temp dirs).
- **Custom tools** (`chat_tools.py`): `get_ticker_metrics` and `run_screen`
  with injected downloader/sector fakes (reuse existing test fakes) → real
  metrics / summary; error path returns an error dict.
- **Persona**: `analyst.generate_brief`'s prompt still contains the persona and
  the JSON instruction after the extraction (guards the refactor).
- **REPL**: a `main()` wiring smoke test with an injected engine/stub
  (no network), asserting it reads input, calls `send`, and writes a transcript.

## 11. Out of scope (deferred)

- The full **web UI** (backend API + SSE + frontend + deployment) — its own
  later spec; the `send() → event stream` seam is what makes it a clean add.
- Cross-session conversation resume / stored threads.
- Auth, multi-user, voice.

## 12. Deliverables / conventions

- README gains a "Chat" section: `python chat.py`, what it loads, the two
  tools, transcripts in `reports/`.
- Unit tests for the deterministic pieces (tools, context loading) and the
  engine's tool loop (via the fake client).

## 13. Open risks / validate during implementation

- **Mixing the server `web_search` tool with custom tools in one request**:
  confirm the manual tool loop handles a turn that contains both a server-tool
  result and a custom `tool_use` (and `pause_turn`) correctly; the engine must
  only execute/return results for the custom tools and let server tools resolve
  server-side.
- **`run_screen` cost/latency**: a full re-screen pulls the universe; rely on
  the existing caches and consider a smaller default scope if a single call is
  too slow interactively (tune during implementation).
- **`exclude_asset_types` fidelity**: asset-type is only known for held names
  and via sector data; document it as best-effort for v1.
