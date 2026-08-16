# Chat Persistence — Design

**Date:** 2026-08-15
**Status:** Design — pending user review
**Project root:** `/home/kineticrick/code/python/vantage`

## 1. Purpose

Conversations with the analyst are not saved anywhere.

The dashboard holds one `Conversation` on `app.state.conversation`. It exists
only in the server process, and three ordinary actions destroy it with no
recovery: clicking **New chat**, restarting the server, and the process dying.
`chat.py` does write `reports/chat-<stamp>.md`, but only on a clean exit — a
Ctrl-C loses the session. Nothing has ever been written: `reports/` contains no
chat transcript. There is no client-side storage either.

The user reports these conversations are high-value and wants to refer back to
them. This builds the store that makes that possible.

### Success criteria
- A conversation survives a server restart, a browser close, and a crash mid-answer.
- Past conversations are listed with meaningful titles and can be read.
- A past conversation can be resumed and continued.
- Transcripts are readable from a shell with the server down.
- Both the dashboard and `chat.py` produce the same artifact, in one place.

### Non-goal
The analyst gaining memory of prior conversations. That is the second piece,
specced separately against the store this one builds — see §6.

## 2. Decomposition and why

The user asked for three things: read past conversations, continue them, and
have the analyst remember them. These are two projects.

Reading and resuming share one store; resuming is "load a saved conversation
back into a live one." Building them separately would design the store twice.

Analyst memory is a different problem. Storage is the easy part of it. The hard
part is choosing what the analyst recalls, and there is a hazard specific to
this domain: a conversation from three weeks ago says MU is +683% over 12m.
That was true when said. An analyst that "remembers" it and quotes it later
presents a stale number as current — the same class of error as the
cache-vintage bug and the reason `termstructure.py` is the single formatter.
Any memory design must date its recollections and treat remembered figures as
historical, never live.

`config/evidence.yaml` is a precedent worth weighing there: it already is
durable analyst memory — five curated claims, each with a verdict and a link to
its evidence, loaded into both the brief and the chat analyst on every run. It
works because it is small, distilled and human-approved rather than a raw dump.
Memory may well be a curation feature rather than a retrieval one. That
question is deferred, not answered here.

## 3. Architecture

Two new modules, plus integration.

### 3.1 `vantage/chatstore.py` (new) — the single owner of persistence

The role `tickers.py` plays for ticker identity and `termstructure.py` plays
for number formatting: one module owns the concern, and every surface goes
through it.

```
ChatSession:
    id           "20260815T195412123456Z"   sortable, unique, matches chat.py's
                 stamp (microseconds included so two sessions minted in the
                 same second still get distinct ids)
    started_at   ISO-8601 UTC
    updated_at   ISO-8601 UTC
    title        auto-generated; "" until the first titling call succeeds
    title_turns  turn count when the title was last generated
    messages     normalized plain-dict Anthropic messages
```

**Public surface:**

| Function | Behavior |
|---|---|
| `new_session()` | fresh `ChatSession` with a UTC-stamped id |
| `save(chats_dir, session)` | writes both files atomically |
| `load(chats_dir, id)` | `ChatSession` or `None` |
| `list_sessions(chats_dir)` | reverse-chronological summaries |
| `render_markdown(session)` | readable transcript |
| `normalize(messages)` | SDK content blocks → plain dicts |

`list_sessions` returns, per conversation and newest first:
`{id, title, started_at, updated_at, turns}`. It reads each JSON file but never
the markdown, and returns no message bodies — the list view needs none.

**"Turn" means one user-initiated exchange — one `/api/chat` request.** A
single turn may append several entries to `messages` when the analyst calls
tools (`vantage/conversation.py:58,73`), so turn count is *not* `len(messages)`.
It is the count of `role: "user"` messages whose content is a plain string,
which excludes the tool-result messages that are also sent as `role: "user"`
(`conversation.py:73`). This definition drives both the titling thresholds and
the `turns` field above.

**Files.** `reports/chats/chat-<id>.json` is the source of truth;
`reports/chats/chat-<id>.md` is a readable render written beside it. Its own
subdirectory so `reports/` does not accumulate a file per conversation
alongside the weekly briefs. `save` creates `reports/chats/` if absent —
`load_settings` creates `reports_dir` but knows nothing of this subdirectory.

Writing the markdown too is deliberate: it makes transcripts greppable from a
shell with the server down, which is the minimum bar for "easily access them."
Both files are rewritten whole on each turn; at conversation sizes (a few KB)
this is not worth optimizing.

**Atomicity.** `save` writes to a temp file in the same directory and
`os.replace`s it into position, so a crash mid-write cannot truncate an
existing conversation.

**`normalize` exists because `Conversation.messages` is mixed.** User turns are
plain dicts, but assistant content comes from `final.content`
(`vantage/conversation.py:58`) as SDK block objects, which are not
JSON-serializable. Normalizing to plain dicts on the way out is sufficient in
both directions: the Anthropic API accepts plain dicts, so a normalized message
list round-trips back into a resumed conversation with no reverse converter.

**`list_sessions` skips unreadable files** rather than failing the listing,
matching the existing `except (ValueError, OSError): continue` in
`artifacts.list_briefs`. One corrupt conversation must not hide the others.

**Tool calls are preserved and rendered.** The JSON keeps `tool_use` and
`tool_result` blocks because resume must replay them faithfully. The markdown
annotates them compactly — `[get_ticker_metrics MU → +683% 12m]`. A transcript
showing the analyst asserting a figure with no trace of the call that produced
it discards exactly the provenance the rest of the system maintains.

### 3.2 `vantage/chattitle.py` (new) — title generation

Separate from the store because the store does files and this makes an API
call. Follows the project's established `_client=None` injection pattern so
tests run against a fake.

`generate_title(messages, settings, _client=None) -> str` sends a trimmed,
tool-stripped rendering of the conversation to Haiku
(`claude-haiku-4-5-20251001`, a module constant — deliberately not a `Settings`
field, since `settings.model` is the analyst's model and the two should not be
confused) and asks for a 4–8 word title naming the specific subject.

**Re-titling.** A conversation that opens on MU and ends on portfolio
concentration outgrows its first title. Re-title when the turn count reaches
the next threshold in **1, 3, 6, 12, 24, 48**; `title_turns` records when the
title was last generated. This tracks growth without a call every turn.
**48 is the last threshold** — beyond it the title stands, on the reasoning
that a 48-turn conversation's subject is established.

Titles are auto-only — there is no rename. This keeps the title a pure function
of the conversation: always recomputable, with no pinned user override to
respect, so improving the titling prompt later improves every existing title.

**Titling can never break or delay a chat.** It runs after the turn is saved,
best-effort, by which point the full answer has already streamed to the client.
On failure the stored `title` is left exactly as it was — including `""` for a
conversation never successfully titled — and `title_turns` is not advanced, so
the next turn retries. The `Chat <YYYY-MM-DD>` fallback is a **display**
concern: `list_sessions` substitutes it for an empty title. Nothing writes a
placeholder title to disk, so a stored title is always a real generated one.

### 3.3 Dashboard integration

`app.state.session` holds the active `ChatSession` alongside the existing
`app.state.conversation`.

`/api/chat` creates a session if none is active, streams as it does today, then
saves. **Persistence hooks into the SSE wrapper, not into `Conversation`** —
the wrapper iterates `conv.send()` inside `try/finally` and saves
`conv.messages` in the `finally`. `Conversation` is not modified.

The `finally` placement is the point: abandoning the stream — closing the tab
mid-answer — raises `GeneratorExit` into the wrapper, so the turn is still
saved. A hard process kill loses at most the in-flight turn.

New endpoints:

| Endpoint | Behavior |
|---|---|
| `GET /api/chats` | the titled list, reverse-chronological |
| `GET /api/chats/{id}` | one conversation, for reading |
| `POST /api/chats/{id}/resume` | load as active; later messages continue it |

`GET /api/chats/{id}` returns `{id, title, started_at, updated_at, turns,
messages}` — the normalized messages, which the panel renders directly. It does
not return the markdown; that file exists for shell access, not for the UI.

**Resume rebuilds context, not just history.** It constructs a fresh
`Conversation` — which builds its system prompt from *today's* brief,
portfolio and evidence register (`conversation.py:20-21`) — and assigns the
loaded messages onto `.messages`. So a resumed conversation carries last
week's discussion against this week's data. That is the correct behavior and a
deliberate consequence: the analyst's grounding is always current even when the
history is not, which is the same hazard §2 defers to piece 2, contained here
by never re-deriving context from stored messages.

`POST /api/chat/new` already exists and keeps its meaning: clear the active
session so the next message starts a new one.

**Opening the dashboard shows a fresh, empty chat.** Because sessions live
server-side, the frontend must `POST /api/chat/new` on page load — otherwise it
silently inherits whatever session the server still held from the last sitting.

**UI.** A history list in the chat panel: title and date per conversation,
click to read, with an action to continue it. Rendering follows the existing
XSS posture — brief and chat prose is built as DOM text nodes, never assigned
through `innerHTML` (commits `5107bda`, `dd94d10`).

### 3.4 `chat.py` integration

The REPL switches to `chatstore` and its bespoke transcript writer is removed,
so REPL conversations append per turn like dashboard ones, survive a Ctrl-C,
and appear in the same list.

## 4. Error handling

- **Save fails** → an SSE `error` event reports that persistence is broken; the
  answer still streams. Silently failing to save is the only outcome worse than
  not having the feature.
- **Titling fails** → previous title kept, or the date fallback; never surfaced
  as a chat error.
- **Unreadable session file** → skipped in the listing; `404` on direct load.
- **Resume of an unknown id** → `404`.

## 5. Testing

- `chatstore` round-trip, including `normalize` against fake SDK content blocks.
- Atomic write: an interrupted write leaves the previous file intact.
- `list_sessions` ordering, and that one corrupt file does not hide the others.
- `render_markdown` includes tool-call annotations.
- Title thresholds fire at 1/3/6/12/24/48 and not between; a titling failure
  keeps the previous title. Both against a fake client.
- App-level tests through the existing injectable `conversation_factory`: a
  turn persists a session; **abandoning the stream mid-answer still persists**;
  `/api/chat/new` starts a new session; resume continues an existing one.
- `chat.py` writes through `chatstore`.

## 6. Out of scope

- **Analyst memory of prior conversations** — the second piece, specced against
  this store once it exists, with the stale-figure hazard of §2 as its central
  problem.
- **Full-text search.** The chosen way to find a conversation is a titled list.
- **Renaming a conversation** — see §3.2 on why titles stay derived.
- **Retention or pruning.** Weekly conversations at a few KB each do not need it.

## 7. Accepted limitation

The active session is a single server-side global, so two browser tabs would
fight over it. That is acceptable for a localhost single-user tool and wrong
the moment it is not. Recorded rather than designed around.
