# Chat Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save every analyst conversation to disk so it survives restarts and crashes, list past conversations by auto-generated title, and resume one to keep talking in it.

**Architecture:** A new `vantage/chatstore.py` owns all conversation persistence — both the dashboard and `chat.py` go through it, and nothing else writes a chat file. A new `vantage/chattitle.py` generates titles with a cheap model. The dashboard wraps its chat event stream so each completed turn is saved, and gains three read/resume endpoints. `vantage/conversation.py` is NOT modified.

**Tech Stack:** Python 3.14, pandas 3.0.5, FastAPI + `fastapi.testclient`, pytest, vanilla JS/CSS with no build step and no JS test harness.

**Spec:** `docs/superpowers/specs/2026-08-15-chat-persistence-design.md`

## Global Constraints

- **`vantage/chatstore.py` is the single owner of chat persistence.** No other module writes or names a chat file. This is the same rule that makes `tickers.py` the sole owner of ticker identity and `termstructure.py` the sole formatter.
- **`vantage/conversation.py` must not be modified.** Persistence hooks into the dashboard's event-stream wrapper, not into `Conversation`.
- **Files are `reports/chats/chat-<id>.json` (source of truth) and `reports/chats/chat-<id>.md` (readable render).** `save` creates `reports/chats/` if absent.
- **Writes are atomic:** temp file in the same directory, then `os.replace`. A crash mid-write must not truncate an existing conversation.
- **A "turn" is one user-initiated exchange** — the count of `role: "user"` messages whose `content` is a plain string. It is NOT `len(messages)`: one turn appends several entries when tools are called, and tool results are also sent with `role: "user"` (`vantage/conversation.py:58,73`).
- **Titling never breaks or delays a chat.** It runs after the turn is saved. On failure the stored title is left as-is and `title_turns` is not advanced, so the next turn retries.
- **No placeholder title is ever written to disk.** `""` means never successfully titled; the `Chat <YYYY-MM-DD>` fallback is applied by `list_sessions` for display only.
- **Titling model is `claude-haiku-4-5-20251001`**, a module constant in `chattitle.py` — deliberately not a `Settings` field, because `settings.model` is the analyst's model.
- **Title thresholds are 1, 3, 6, 12, 24, 48. 48 is the last** — beyond it the title stands.
- **A save failure surfaces as an SSE `error` event, and the answer still streams.** Silently failing to save is the only outcome worse than not having the feature.
- **Frontend prose is built as DOM text nodes, never `innerHTML`** (commits `5107bda`, `dd94d10`).
- **Opening the dashboard shows a fresh, empty chat.**

---

### Task 1: `chatstore.py` — the store

**Files:**
- Create: `vantage/chatstore.py`
- Test: `tests/test_chatstore.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `ChatSession` dataclass: `id: str`, `started_at: str`, `updated_at: str`, `title: str`, `title_turns: int`, `messages: list`
  - `new_session(now=None) -> ChatSession`
  - `normalize(messages: list) -> list[dict]`
  - `turn_count(messages: list) -> int`
  - `save(chats_dir, session: ChatSession, now=None) -> None`
  - `load(chats_dir, session_id: str) -> ChatSession | None`
  - `list_sessions(chats_dir) -> list[dict]` with keys `id, title, started_at, updated_at, turns`
  - `render_markdown(session: ChatSession) -> str`
  - `chats_dir(settings) -> Path` — returns `settings.reports_dir / "chats"`
  - `ID_RE` — compiled `^[0-9]{8}T[0-9]{6}Z$`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_chatstore.py
import json
from pathlib import Path
import pytest
from vantage import chatstore


class _FakeBlock:
    """Stands in for an SDK content block: has model_dump, is not a dict."""
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self, mode=None, exclude_none=False):
        return dict(self._payload)


def test_normalize_converts_sdk_blocks_to_plain_dicts():
    messages = [
        {"role": "user", "content": "what about MU?"},
        {"role": "assistant", "content": [_FakeBlock({"type": "text", "text": "hi"})]},
    ]
    out = chatstore.normalize(messages)
    assert out == [
        {"role": "user", "content": "what about MU?"},
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
    ]
    json.dumps(out)  # must be serializable


def test_normalize_leaves_plain_dicts_untouched():
    messages = [{"role": "user", "content": [{"type": "tool_result",
                                              "tool_use_id": "t1",
                                              "content": "{}"}]}]
    assert chatstore.normalize(messages) == messages


def test_turn_count_ignores_tool_result_user_messages():
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": [{"type": "text", "text": "a"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1",
                                      "content": "{}"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "b"}]},
        {"role": "user", "content": "second"},
    ]
    assert chatstore.turn_count(messages) == 2


def test_save_and_load_round_trip(tmp_path):
    s = chatstore.new_session(now="2026-08-15T19:54:12Z")
    s.messages = [{"role": "user", "content": "hello"}]
    s.title = "A test conversation"
    s.title_turns = 1
    chatstore.save(tmp_path, s, now="2026-08-15T20:00:00Z")

    back = chatstore.load(tmp_path, s.id)
    assert back.id == s.id
    assert back.title == "A test conversation"
    assert back.title_turns == 1
    assert back.messages == [{"role": "user", "content": "hello"}]
    assert back.updated_at == "2026-08-15T20:00:00Z"


def test_save_creates_the_chats_directory(tmp_path):
    target = tmp_path / "chats"
    assert not target.exists()
    chatstore.save(target, chatstore.new_session(now="2026-08-15T19:54:12Z"))
    assert target.is_dir()


def test_save_writes_both_json_and_markdown(tmp_path):
    s = chatstore.new_session(now="2026-08-15T19:54:12Z")
    s.messages = [{"role": "user", "content": "hello"}]
    chatstore.save(tmp_path, s)
    assert (tmp_path / f"chat-{s.id}.json").exists()
    assert (tmp_path / f"chat-{s.id}.md").exists()


def test_load_returns_none_for_missing(tmp_path):
    assert chatstore.load(tmp_path, "20260815T000000Z") is None


def test_list_sessions_is_reverse_chronological(tmp_path):
    for stamp in ("20260813T100000Z", "20260815T100000Z", "20260814T100000Z"):
        s = chatstore.ChatSession(id=stamp, started_at=stamp, updated_at=stamp,
                                  title=f"t-{stamp}", title_turns=1,
                                  messages=[{"role": "user", "content": "x"}])
        chatstore.save(tmp_path, s, now=stamp)
    ids = [row["id"] for row in chatstore.list_sessions(tmp_path)]
    assert ids == ["20260815T100000Z", "20260814T100000Z", "20260813T100000Z"]


def test_list_sessions_skips_corrupt_files_without_hiding_others(tmp_path):
    s = chatstore.ChatSession(id="20260815T100000Z", started_at="20260815T100000Z",
                              updated_at="20260815T100000Z", title="good",
                              title_turns=1,
                              messages=[{"role": "user", "content": "x"}])
    chatstore.save(tmp_path, s)
    (tmp_path / "chat-20260814T100000Z.json").write_text("{not json",
                                                         encoding="utf-8")
    rows = chatstore.list_sessions(tmp_path)
    assert [r["id"] for r in rows] == ["20260815T100000Z"]


def test_list_sessions_reports_turns_and_falls_back_for_empty_title(tmp_path):
    s = chatstore.ChatSession(id="20260815T100000Z",
                              started_at="2026-08-15T10:00:00Z",
                              updated_at="2026-08-15T10:00:00Z",
                              title="", title_turns=0,
                              messages=[{"role": "user", "content": "a"},
                                        {"role": "assistant",
                                         "content": [{"type": "text", "text": "b"}]},
                                        {"role": "user", "content": "c"}])
    chatstore.save(tmp_path, s)
    row = chatstore.list_sessions(tmp_path)[0]
    assert row["turns"] == 2
    assert row["title"] == "Chat 2026-08-15"


def test_stored_title_is_never_a_placeholder(tmp_path):
    """The fallback is display-only; disk keeps the empty string."""
    s = chatstore.ChatSession(id="20260815T100000Z",
                              started_at="2026-08-15T10:00:00Z",
                              updated_at="2026-08-15T10:00:00Z",
                              title="", title_turns=0, messages=[])
    chatstore.save(tmp_path, s)
    raw = json.loads((tmp_path / "chat-20260815T100000Z.json").read_text())
    assert raw["title"] == ""


def test_atomic_write_leaves_previous_file_intact_on_failure(tmp_path, monkeypatch):
    s = chatstore.new_session(now="2026-08-15T19:54:12Z")
    s.messages = [{"role": "user", "content": "original"}]
    chatstore.save(tmp_path, s)

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(chatstore.os, "replace", boom)
    s.messages = [{"role": "user", "content": "replacement"}]
    with pytest.raises(OSError):
        chatstore.save(tmp_path, s)

    back = chatstore.load(tmp_path, s.id)
    assert back.messages == [{"role": "user", "content": "original"}]


def test_render_markdown_annotates_tool_calls(tmp_path):
    s = chatstore.new_session(now="2026-08-15T19:54:12Z")
    s.title = "MU term structure"
    s.messages = [
        {"role": "user", "content": "what about MU?"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "name": "get_ticker_metrics",
             "input": {"ticker": "MU"}, "id": "t1"}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "content": '{"ret_12m": 6.83}'}]},
        {"role": "assistant", "content": [
            {"type": "text", "text": "MU is up 683% over 12m."}]},
    ]
    md = chatstore.render_markdown(s)
    assert "MU term structure" in md
    assert "**you>** what about MU?" in md
    assert "[called get_ticker_metrics(ticker=MU)]" in md
    assert '[-> {"ret_12m": 6.83}]' in md
    assert "MU is up 683% over 12m." in md


def test_id_re_rejects_path_traversal():
    assert chatstore.ID_RE.match("20260815T195412Z")
    assert not chatstore.ID_RE.match("../../etc/passwd")
    assert not chatstore.ID_RE.match("20260815T195412Z/../x")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_chatstore.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vantage.chatstore'`

- [ ] **Step 3: Write the implementation**

```python
# vantage/chatstore.py
"""Single owner of analyst-conversation persistence.

Every surface that saves a chat — the dashboard and chat.py — goes through
this module. Nothing else writes or names a chat file, for the same reason
tickers.py alone owns ticker identity: one rule, one place, no drift.
"""
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Conversation ids are UTC stamps. They land in a filename, so anything that
# does not match is refused rather than joined onto a path.
ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")

_TOOL_RESULT_CAP = 200


@dataclass
class ChatSession:
    id: str
    started_at: str
    updated_at: str
    title: str = ""
    title_turns: int = 0
    messages: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ChatSession":
        return cls(id=d["id"], started_at=d.get("started_at", ""),
                   updated_at=d.get("updated_at", ""), title=d.get("title", ""),
                   title_turns=int(d.get("title_turns", 0)),
                   messages=d.get("messages", []))


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def chats_dir(settings) -> Path:
    return Path(settings.reports_dir) / "chats"


def new_session(now=None) -> ChatSession:
    ts = now or _utc_now()
    return ChatSession(id=_stamp_id(), started_at=ts, updated_at=ts)


def _block_to_dict(block):
    """One assistant content block as a plain, JSON-safe dict.

    Conversation.messages is mixed: user turns are plain dicts, but assistant
    content comes off the SDK as block objects (conversation.py:58). Plain
    dicts are what the API accepts on the way back in, so normalizing one
    direction is enough — resume needs no reverse converter.
    """
    if isinstance(block, dict):
        return block
    dump = getattr(block, "model_dump", None)
    if dump is not None:
        return dump(mode="json", exclude_none=True)
    return {"type": "text", "text": str(block)}


def normalize(messages) -> list:
    out = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
        else:
            out.append({"role": m["role"],
                        "content": [_block_to_dict(b) for b in content]})
    return out


def turn_count(messages) -> int:
    """User-initiated exchanges — NOT len(messages).

    Tool results are also sent with role "user" (conversation.py:73); only a
    plain-string user message is a turn the person actually took.
    """
    return sum(1 for m in messages
               if m.get("role") == "user" and isinstance(m.get("content"), str))


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save(chats_directory, session: ChatSession, now=None) -> None:
    d = Path(chats_directory)
    d.mkdir(parents=True, exist_ok=True)
    session.updated_at = now or _utc_now()
    _atomic_write(d / f"chat-{session.id}.json",
                  json.dumps(session.to_dict(), indent=2))
    _atomic_write(d / f"chat-{session.id}.md", render_markdown(session))


def load(chats_directory, session_id: str) -> ChatSession | None:
    if not ID_RE.match(session_id or ""):
        return None
    p = Path(chats_directory) / f"chat-{session_id}.json"
    if not p.exists():
        return None
    try:
        return ChatSession.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except (ValueError, OSError, KeyError):
        return None


def list_sessions(chats_directory) -> list:
    """Newest first. One unreadable conversation must not hide the rest —
    the same tolerance artifacts.list_briefs already applies."""
    rows = []
    for p in Path(chats_directory).glob("chat-*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        started = d.get("started_at", "")
        rows.append({"id": d.get("id", ""),
                     "title": d.get("title") or f"Chat {started[:10]}",
                     "started_at": started,
                     "updated_at": d.get("updated_at", ""),
                     "turns": turn_count(d.get("messages", []))})
    rows.sort(key=lambda r: r["updated_at"], reverse=True)
    return rows


def _render_blocks(content) -> list:
    parts = []
    for b in content:
        kind = b.get("type")
        if kind == "text":
            parts.append(b.get("text", ""))
        elif kind == "tool_use":
            args = ", ".join(f"{k}={v}" for k, v in (b.get("input") or {}).items())
            parts.append(f"_[called {b.get('name')}({args})]_")
        elif kind == "tool_result":
            body = str(b.get("content", ""))
            if len(body) > _TOOL_RESULT_CAP:
                body = body[:_TOOL_RESULT_CAP] + "..."
            parts.append(f"_[-> {body}]_")
    return [p for p in parts if p]


def render_markdown(session: ChatSession) -> str:
    """Readable transcript, greppable from a shell with the server down.

    Tool calls are kept: a transcript showing the analyst asserting +683% with
    no trace of the call behind it throws away the provenance the rest of the
    system works to maintain.
    """
    head = [f"# {session.title or 'Chat ' + session.started_at[:10]}", "",
            f"- id: {session.id}", f"- started: {session.started_at}",
            f"- updated: {session.updated_at}", ""]
    body = []
    for m in session.messages:
        content = m.get("content")
        if isinstance(content, str):
            body.append(f"**{'you' if m.get('role') == 'user' else 'analyst'}>** "
                        f"{content}")
            continue
        rendered = _render_blocks(content)
        if not rendered:
            continue
        label = "you" if m.get("role") == "user" else "analyst"
        body.append(f"**{label}>** " + "\n\n".join(rendered))
    return "\n".join(head) + "\n" + "\n\n".join(body) + "\n"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_chatstore.py -q`
Expected: PASS (14 tests)

- [ ] **Step 5: Run the full suite for regressions**

Run: `.venv/bin/python -m pytest -q`
Expected: 346 + 14 = 360 passing

- [ ] **Step 6: Commit**

```bash
git add vantage/chatstore.py tests/test_chatstore.py
git commit -m "feat(chat): chatstore owns conversation persistence"
```

---

### Task 2: `chattitle.py` — auto-generated titles

**Files:**
- Create: `vantage/chattitle.py`
- Test: `tests/test_chattitle.py`

**Interfaces:**
- Consumes: `chatstore.ChatSession`, `chatstore.turn_count` from Task 1.
- Produces:
  - `TITLE_MODEL = "claude-haiku-4-5-20251001"`
  - `THRESHOLDS = (1, 3, 6, 12, 24, 48)`
  - `should_title(turns: int, title_turns: int) -> bool`
  - `generate_title(messages: list, settings, _client=None) -> str` — raises on API failure
  - `maybe_retitle(session, settings, _client=None) -> bool` — best-effort; swallows every exception and returns whether the title changed

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_chattitle.py
from vantage import chatstore, chattitle


class _FakeMessages:
    def __init__(self, text=None, error=None):
        self._text = text
        self._error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error

        class _Block:
            type = "text"
            text = self._text

        class _Resp:
            content = [_Block()]

        return _Resp()


class _FakeClient:
    def __init__(self, text=None, error=None):
        self.messages = _FakeMessages(text=text, error=error)


def _settings():
    class S:
        anthropic_api_key = "k"
        model = "analyst-model"
    return S()


def test_should_title_fires_on_first_turn():
    assert chattitle.should_title(turns=1, title_turns=0) is True


def test_should_title_does_not_fire_between_thresholds():
    assert chattitle.should_title(turns=2, title_turns=1) is False
    assert chattitle.should_title(turns=5, title_turns=3) is False


def test_should_title_fires_at_each_threshold():
    for turns, prev in ((3, 1), (6, 3), (12, 6), (24, 12), (48, 24)):
        assert chattitle.should_title(turns, prev) is True, turns


def test_forty_eight_is_the_last_threshold():
    assert chattitle.should_title(turns=100, title_turns=48) is False


def test_generate_title_uses_the_cheap_model_not_the_analyst_model():
    client = _FakeClient(text="MU term structure and memory pricing")
    out = chattitle.generate_title(
        [{"role": "user", "content": "what about MU?"}], _settings(),
        _client=client)
    assert out == "MU term structure and memory pricing"
    assert client.messages.calls[0]["model"] == chattitle.TITLE_MODEL
    assert client.messages.calls[0]["model"] != "analyst-model"


def test_generate_title_strips_quotes_and_newlines():
    client = _FakeClient(text='  "Optical names overextended?"\n')
    out = chattitle.generate_title([{"role": "user", "content": "x"}],
                                   _settings(), _client=client)
    assert out == "Optical names overextended?"


def test_generate_title_omits_tool_blocks_from_the_prompt():
    client = _FakeClient(text="a title")
    messages = [
        {"role": "user", "content": "what about MU?"},
        {"role": "user", "content": [{"type": "tool_result",
                                      "tool_use_id": "t1",
                                      "content": "SECRETBLOB"}]},
    ]
    chattitle.generate_title(messages, _settings(), _client=client)
    sent = str(client.messages.calls[0]["messages"])
    assert "what about MU?" in sent
    assert "SECRETBLOB" not in sent


def test_maybe_retitle_sets_title_and_records_turn_count():
    s = chatstore.new_session(now="2026-08-15T10:00:00Z")
    s.messages = [{"role": "user", "content": "what about MU?"}]
    changed = chattitle.maybe_retitle(s, _settings(),
                                      _client=_FakeClient(text="MU trajectory"))
    assert changed is True
    assert s.title == "MU trajectory"
    assert s.title_turns == 1


def test_maybe_retitle_keeps_previous_title_on_failure():
    s = chatstore.new_session(now="2026-08-15T10:00:00Z")
    s.title = "existing title"
    s.title_turns = 1
    s.messages = [{"role": "user", "content": "a"},
                  {"role": "assistant", "content": [{"type": "text", "text": "b"}]},
                  {"role": "user", "content": "c"},
                  {"role": "assistant", "content": [{"type": "text", "text": "d"}]},
                  {"role": "user", "content": "e"}]
    changed = chattitle.maybe_retitle(
        s, _settings(), _client=_FakeClient(error=RuntimeError("api down")))
    assert changed is False
    assert s.title == "existing title"
    # not advanced, so the next turn retries
    assert s.title_turns == 1


def test_maybe_retitle_never_writes_a_placeholder_title():
    s = chatstore.new_session(now="2026-08-15T10:00:00Z")
    s.messages = [{"role": "user", "content": "a"}]
    chattitle.maybe_retitle(s, _settings(),
                            _client=_FakeClient(error=RuntimeError("down")))
    assert s.title == ""


def test_maybe_retitle_is_a_noop_between_thresholds():
    s = chatstore.new_session(now="2026-08-15T10:00:00Z")
    s.title = "kept"
    s.title_turns = 1
    s.messages = [{"role": "user", "content": "a"},
                  {"role": "assistant", "content": [{"type": "text", "text": "b"}]},
                  {"role": "user", "content": "c"}]
    client = _FakeClient(text="should not be used")
    assert chattitle.maybe_retitle(s, _settings(), _client=client) is False
    assert s.title == "kept"
    assert client.messages.calls == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_chattitle.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vantage.chattitle'`

- [ ] **Step 3: Write the implementation**

```python
# vantage/chattitle.py
"""Auto-generated conversation titles.

Kept apart from chatstore because the store does files and this makes an API
call. Titles are derived, never user-edited: that keeps a title a pure
function of the conversation, so improving this prompt later improves every
existing title, and there is no pinned override to respect.
"""
from vantage import chatstore

TITLE_MODEL = "claude-haiku-4-5-20251001"

# Re-title as a conversation grows — one that opens on MU and ends on
# portfolio concentration outgrows its first title. 48 is the last: by then
# the subject is established.
THRESHOLDS = (1, 3, 6, 12, 24, 48)

_PROMPT_CAP = 4000

_INSTRUCTION = (
    "Below is a conversation between an investor and a market analyst. "
    "Give it a title of 4-8 words naming the specific subject discussed — "
    "the tickers, sectors or question at issue. No quotes, no trailing "
    "punctuation, no preamble. Reply with the title alone.\n\n"
)


def should_title(turns: int, title_turns: int) -> bool:
    crossed = [t for t in THRESHOLDS if t <= turns]
    return bool(crossed) and max(crossed) > title_turns


def _transcript(messages) -> str:
    """User prose and assistant prose only.

    Tool blocks are dropped: they are bulk, they are not what the
    conversation is *about*, and they would crowd out the prose the title
    has to be drawn from.
    """
    lines = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            lines.append(f"{m.get('role')}: {content}")
            continue
        for b in content:
            if b.get("type") == "text":
                lines.append(f"{m.get('role')}: {b.get('text', '')}")
    return "\n".join(lines)[:_PROMPT_CAP]


def generate_title(messages, settings, _client=None) -> str:
    client = _client
    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model=TITLE_MODEL, max_tokens=32,
        messages=[{"role": "user",
                   "content": _INSTRUCTION + _transcript(messages)}])
    text = "".join(getattr(b, "text", "") for b in resp.content
                   if getattr(b, "type", None) == "text")
    return text.strip().strip('"').strip()


def maybe_retitle(session, settings, _client=None) -> bool:
    """Best-effort. Never raises, never blocks a chat.

    On failure the stored title is left exactly as it was and title_turns is
    not advanced, so the next turn retries. Nothing writes a placeholder: an
    empty title means never successfully titled, and list_sessions supplies
    the display fallback.
    """
    turns = chatstore.turn_count(session.messages)
    if not should_title(turns, session.title_turns):
        return False
    try:
        title = generate_title(session.messages, settings, _client=_client)
    except Exception:
        return False
    if not title:
        return False
    session.title = title
    session.title_turns = turns
    return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_chattitle.py -q`
Expected: PASS (11 tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: 371 passing

- [ ] **Step 6: Commit**

```bash
git add vantage/chattitle.py tests/test_chattitle.py
git commit -m "feat(chat): auto-generated conversation titles"
```

---

### Task 3: Persist each dashboard turn

**Files:**
- Modify: `vantage/web/app.py` (the `/api/chat` handler and `create_app` state)
- Modify: `tests/test_web_chat.py` (the fake conversation needs a `.messages`)
- Test: `tests/test_web_chat_persistence.py`

**Interfaces:**
- Consumes: `chatstore.new_session`, `chatstore.normalize`, `chatstore.save`, `chatstore.chats_dir` (Task 1); `chattitle.maybe_retitle` (Task 2).
- Produces: `app.state.session` — the active `ChatSession` or `None`. Task 4 reads and replaces it.

**Note for the implementer:** the existing `_FakeConversation` in `tests/test_web_chat.py` has no `messages` attribute, and persistence reads `conv.messages`. Add `self.messages = []` to it and append the exchange in `send`, so the existing tests keep passing against the new code path. `_sse` is shared with `/api/refresh` — do NOT put persistence in `_sse`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_chat_persistence.py
import json
from pathlib import Path
from fastapi.testclient import TestClient
from vantage import chatstore
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
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append({"role": "user", "content": message})
        yield {"type": "text", "text": f"echo: {message}"}
        self.messages.append({"role": "assistant",
                              "content": [{"type": "text", "text": f"echo: {message}"}]})
        yield {"type": "done"}


class _AbandonedConversation(_FakeConversation):
    """Yields text, then more than the client will read."""
    def send(self, message):
        self.messages.append({"role": "user", "content": message})
        yield {"type": "text", "text": "partial"}
        self.messages.append({"role": "assistant",
                              "content": [{"type": "text", "text": "partial"}]})
        for i in range(1000):
            yield {"type": "text", "text": f"chunk{i}"}
        yield {"type": "done"}


def _app(tmp_path, conv=None, **kw):
    c = conv or _FakeConversation()
    return create_app(settings=_settings(tmp_path),
                      conversation_factory=lambda s: c, **kw), c


def test_a_turn_is_persisted(tmp_path):
    app, _ = _app(tmp_path)
    client = TestClient(app)
    client.post("/api/chat", json={"message": "what about MU?"})

    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert len(rows) == 1
    assert rows[0]["turns"] == 1
    sess = chatstore.load(tmp_path / "reports" / "chats", rows[0]["id"])
    assert sess.messages[0] == {"role": "user", "content": "what about MU?"}


def test_second_turn_appends_to_the_same_session(tmp_path):
    app, _ = _app(tmp_path)
    client = TestClient(app)
    client.post("/api/chat", json={"message": "one"})
    client.post("/api/chat", json={"message": "two"})

    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert len(rows) == 1
    assert rows[0]["turns"] == 2


def test_chat_new_starts_a_separate_session(tmp_path):
    settings = _settings(tmp_path)
    convs = []

    def factory(s):
        c = _FakeConversation()
        convs.append(c)
        return c

    client = TestClient(create_app(settings=settings, conversation_factory=factory))
    client.post("/api/chat", json={"message": "one"})
    client.post("/api/chat/new")
    client.post("/api/chat", json={"message": "two"})

    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert len(rows) == 2
    assert len(convs) == 2


def test_markdown_transcript_is_written(tmp_path):
    app, _ = _app(tmp_path)
    TestClient(app).post("/api/chat", json={"message": "what about MU?"})
    mds = list((tmp_path / "reports" / "chats").glob("chat-*.md"))
    assert len(mds) == 1
    assert "what about MU?" in mds[0].read_text(encoding="utf-8")


def test_save_failure_surfaces_an_error_event_but_still_streams(tmp_path,
                                                               monkeypatch):
    app, _ = _app(tmp_path)

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr("vantage.web.app.chatstore.save", boom)

    r = TestClient(app).post("/api/chat", json={"message": "hello"})
    assert r.status_code == 200
    assert "echo: hello" in r.text          # the answer still reached the client
    assert "not saved" in r.text            # and the failure was reported


def test_titling_failure_never_breaks_a_turn(tmp_path, monkeypatch):
    app, _ = _app(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("titling exploded")
    monkeypatch.setattr("vantage.web.app.chattitle.maybe_retitle", boom)

    r = TestClient(app).post("/api/chat", json={"message": "hello"})
    assert r.status_code == 200
    assert "echo: hello" in r.text
    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert rows[0]["turns"] == 1            # the turn was still saved


def test_abandoning_the_stream_still_persists_the_turn(tmp_path):
    """Closing the tab mid-answer must not lose the exchange."""
    app, conv = _app(tmp_path, conv=_AbandonedConversation())
    client = TestClient(app)
    with client.stream("POST", "/api/chat", json={"message": "hello"}) as r:
        for _ in r.iter_lines():
            break                            # read one line, then walk away

    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert len(rows) == 1
    sess = chatstore.load(tmp_path / "reports" / "chats", rows[0]["id"])
    assert sess.messages[0] == {"role": "user", "content": "hello"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_chat_persistence.py -q`
Expected: FAIL — no chat files are written; `list_sessions` returns `[]`

- [ ] **Step 3: Update the existing fake so current tests exercise the new path**

In `tests/test_web_chat.py`, replace `_FakeConversation` with:

```python
class _FakeConversation:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append({"role": "user", "content": message})
        yield {"type": "text", "text": f"echo: {message}"}
        self.messages.append({"role": "assistant",
                              "content": [{"type": "text", "text": f"echo: {message}"}]})
        yield {"type": "done"}
```

- [ ] **Step 4: Write the implementation**

In `vantage/web/app.py`, add to the imports:

```python
from vantage import chatstore, chattitle
```

In `create_app`, beside `app.state.conversation = None`:

```python
    app.state.session = None
```

Add the persistence wrapper above `create_app`:

```python
def _persist(conv, session, settings):
    """Save the turn, then best-effort re-title.

    Titling runs after the save so a titling problem can never cost a
    conversation, and it is best-effort inside maybe_retitle, which swallows
    its own failures. The second save only happens when the title changed.
    """
    session.messages = chatstore.normalize(conv.messages)
    d = chatstore.chats_dir(settings)
    chatstore.save(d, session)
    if chattitle.maybe_retitle(session, settings):
        chatstore.save(d, session)


def _chat_events(conv, session, settings, message):
    """Forward the conversation's events, persisting the completed turn.

    The save is attempted just before "done" so a failure can be reported as
    an event the client is still listening for. The finally covers the other
    path — a client that walks away mid-answer — where yielding is no longer
    legal, so that failure can only be swallowed.
    """
    saved = False
    try:
        for ev in conv.send(message):
            if ev.get("type") == "done" and not saved:
                saved = True
                try:
                    _persist(conv, session, settings)
                except Exception as e:
                    yield {"type": "error", "message": f"chat not saved: {e}"}
            yield ev
    finally:
        if not saved:
            try:
                _persist(conv, session, settings)
            except Exception:
                pass
```

Replace the `/api/chat` handler:

```python
    @app.post("/api/chat")
    async def chat(request: Request):
        body = await request.json()
        conv = _get_conversation()
        if app.state.session is None:
            app.state.session = chatstore.new_session()
        return StreamingResponse(
            _sse(_chat_events(conv, app.state.session, app.state.settings,
                              body.get("message", ""))),
            media_type="text/event-stream")
```

Replace the `/api/chat/new` handler:

```python
    @app.post("/api/chat/new")
    def chat_new():
        app.state.conversation = None
        app.state.session = None
        return {"ok": True}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_chat_persistence.py tests/test_web_chat.py -q`
Expected: PASS

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: 378 passing

- [ ] **Step 7: Commit**

```bash
git add vantage/web/app.py tests/test_web_chat.py tests/test_web_chat_persistence.py
git commit -m "feat(web): persist each chat turn, surviving an abandoned stream"
```

---

### Task 4: Read and resume endpoints

**Files:**
- Modify: `vantage/web/app.py`
- Test: `tests/test_web_chat_sessions.py`

**Interfaces:**
- Consumes: `chatstore.list_sessions`, `chatstore.load`, `chatstore.chats_dir`, `chatstore.ID_RE` (Task 1); `app.state.session` (Task 3).
- Produces: `GET /api/chats`, `GET /api/chats/{cid}`, `POST /api/chats/{cid}/resume`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_chat_sessions.py
from fastapi.testclient import TestClient
from vantage import chatstore
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
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append({"role": "user", "content": message})
        yield {"type": "text", "text": f"echo: {message}"}
        self.messages.append({"role": "assistant",
                              "content": [{"type": "text", "text": f"echo: {message}"}]})
        yield {"type": "done"}


def _seed(tmp_path, session_id, title, messages):
    s = chatstore.ChatSession(id=session_id, started_at="2026-08-15T10:00:00Z",
                              updated_at="2026-08-15T10:00:00Z", title=title,
                              title_turns=1, messages=messages)
    chatstore.save(tmp_path / "reports" / "chats", s, now="2026-08-15T10:00:00Z")
    return s


def _client(tmp_path, convs=None):
    def factory(s):
        c = _FakeConversation()
        if convs is not None:
            convs.append(c)
        return c
    return TestClient(create_app(settings=_settings(tmp_path),
                                 conversation_factory=factory))


def test_list_chats_returns_titles_newest_first(tmp_path):
    client = _client(tmp_path)
    _seed(tmp_path, "20260813T100000Z", "older chat",
          [{"role": "user", "content": "a"}])
    _seed(tmp_path, "20260815T100000Z", "newer chat",
          [{"role": "user", "content": "b"}])
    rows = client.get("/api/chats").json()
    assert [r["title"] for r in rows] == ["newer chat", "older chat"]
    assert rows[0]["turns"] == 1


def test_get_one_chat_returns_its_messages(tmp_path):
    client = _client(tmp_path)
    _seed(tmp_path, "20260815T100000Z", "optical names",
          [{"role": "user", "content": "are the optical names overextended?"}])
    body = client.get("/api/chats/20260815T100000Z").json()
    assert body["title"] == "optical names"
    assert body["turns"] == 1
    assert body["messages"][0]["content"] == "are the optical names overextended?"


def test_get_unknown_chat_is_404(tmp_path):
    assert _client(tmp_path).get("/api/chats/20260101T000000Z").status_code == 404


def test_get_chat_rejects_path_traversal(tmp_path):
    r = _client(tmp_path).get("/api/chats/..%2F..%2Fbrief-2026-08-15")
    assert r.status_code == 404


def test_resume_loads_history_into_the_active_conversation(tmp_path):
    convs = []
    client = _client(tmp_path, convs=convs)
    _seed(tmp_path, "20260815T100000Z", "optical names",
          [{"role": "user", "content": "earlier question"},
           {"role": "assistant", "content": [{"type": "text", "text": "earlier answer"}]}])

    assert client.post("/api/chats/20260815T100000Z/resume").status_code == 200
    client.post("/api/chat", json={"message": "follow-up"})

    # the live conversation carries the old history plus the new turn
    assert convs[-1].messages[0] == {"role": "user", "content": "earlier question"}
    assert convs[-1].messages[-2] == {"role": "user", "content": "follow-up"}

    # and the follow-up landed in the SAME stored session, not a new one
    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert len(rows) == 1
    assert rows[0]["id"] == "20260815T100000Z"
    assert rows[0]["turns"] == 2


def test_resume_unknown_id_is_404(tmp_path):
    assert _client(tmp_path).post(
        "/api/chats/20260101T000000Z/resume").status_code == 404


def test_resume_rebuilds_context_rather_than_reusing_a_stale_conversation(tmp_path):
    """A resumed chat must be built fresh, so its system prompt reflects
    today's brief, portfolio and evidence register."""
    convs = []
    client = _client(tmp_path, convs=convs)
    _seed(tmp_path, "20260815T100000Z", "x", [{"role": "user", "content": "a"}])
    client.post("/api/chat", json={"message": "live one"})
    before = len(convs)
    client.post("/api/chats/20260815T100000Z/resume")
    assert len(convs) == before + 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_chat_sessions.py -q`
Expected: FAIL — 404 on `/api/chats` (route does not exist)

- [ ] **Step 3: Write the implementation**

Add to `vantage/web/app.py`, after the `/api/chat/new` handler:

```python
    @app.get("/api/chats")
    def chats():
        return chatstore.list_sessions(chatstore.chats_dir(app.state.settings))

    @app.get("/api/chats/{cid}")
    def chat_one(cid: str):
        sess = chatstore.load(chatstore.chats_dir(app.state.settings), cid)
        if sess is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {"id": sess.id, "title": sess.title,
                "started_at": sess.started_at, "updated_at": sess.updated_at,
                "turns": chatstore.turn_count(sess.messages),
                "messages": sess.messages}

    @app.post("/api/chats/{cid}/resume")
    def chat_resume(cid: str):
        sess = chatstore.load(chatstore.chats_dir(app.state.settings), cid)
        if sess is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        # Built fresh on purpose: Conversation composes its system prompt from
        # today's brief, portfolio and evidence register (conversation.py:20-21).
        # A resumed chat therefore carries last week's discussion against this
        # week's data — the grounding stays current even when the history is not.
        conv = app.state.conversation_factory(app.state.settings)
        conv.messages = list(sess.messages)
        app.state.conversation = conv
        app.state.session = sess
        return {"ok": True, "id": sess.id,
                "turns": chatstore.turn_count(sess.messages)}
```

`chatstore.load` already refuses any id that fails `ID_RE`, so a traversal
attempt returns `None` and becomes a 404 without touching the filesystem.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_chat_sessions.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: 385 passing

- [ ] **Step 6: Commit**

```bash
git add vantage/web/app.py tests/test_web_chat_sessions.py
git commit -m "feat(web): list, read and resume past conversations"
```

---

### Task 5: History UI in the dashboard

**Files:**
- Modify: `vantage/web/static/index.html`
- Modify: `vantage/web/static/app.js`
- Modify: `vantage/web/static/styles.css`

**Interfaces:**
- Consumes: `GET /api/chats`, `GET /api/chats/{cid}`, `POST /api/chats/{cid}/resume`, `POST /api/chat/new` (Tasks 3-4).
- Produces: no Python interface.

**Note for the implementer:** this project has no JS test harness and no build step — plain files served from `vantage/web/static`. Verify by loading the dashboard.

**The existing helpers you must reuse, not reinvent** (read them before writing anything):

| Helper | Location | What it does |
|---|---|---|
| `$(id)` | `app.js` | element by id |
| `getJSON(url)` | `app.js:13` | fetch + parse |
| `addMsg(kind, text)` | `app.js:280` | appends a `.msg` bubble to `$("chat-log")`; already sets `textContent` |
| `annotate(text, facts)` | `app.js:75` | expands tickers to name + sector |
| `$("chat-new")` handler | `app.js:322` | the existing New-chat control |

Clearing the log is `$("chat-log").replaceChildren()`. There is no
`DOMContentLoaded` hook — the file ends with a bare `loadData();` call, and
that is the init point.

**The XSS rule is not optional here.** Conversation text is model output containing arbitrary characters. `addMsg` is already safe because it assigns `textContent`; keep it that way and never assign chat content through `innerHTML`. This repo has fixed this bug twice already (`5107bda`, `dd94d10`).

- [ ] **Step 1: Add the history panel markup**

In `index.html`, inside the chat panel and above the message list, add:

```html
<div id="chat-history">
  <div class="chat-history-head">
    <span>Past conversations</span>
    <button id="chat-history-toggle" type="button">Show</button>
  </div>
  <ul id="chat-history-list" hidden></ul>
</div>
```

- [ ] **Step 2: Render the list from the API**

In `app.js`:

```js
async function loadChatHistory() {
  const list = document.getElementById('chat-history-list');
  list.replaceChildren();
  let rows = [];
  try {
    const r = await fetch('/api/chats');
    if (!r.ok) throw new Error(r.status);
    rows = await r.json();
  } catch (e) {
    const li = document.createElement('li');
    li.textContent = 'Could not load past conversations.';
    list.append(li);
    return;
  }
  if (!rows.length) {
    const li = document.createElement('li');
    li.textContent = 'No saved conversations yet.';
    list.append(li);
    return;
  }
  for (const row of rows) {
    const li = document.createElement('li');

    const open = document.createElement('button');
    open.type = 'button';
    open.className = 'chat-history-open';
    open.textContent = row.title;               // text node, never innerHTML
    open.addEventListener('click', () => openChat(row.id));

    const meta = document.createElement('span');
    meta.className = 'chat-history-meta';
    meta.textContent = `${(row.updated_at || '').slice(0, 10)} · ${row.turns} turns`;

    const cont = document.createElement('button');
    cont.type = 'button';
    cont.className = 'chat-history-continue';
    cont.textContent = 'Continue';
    cont.addEventListener('click', () => resumeChat(row.id));

    li.append(open, meta, cont);
    list.append(li);
  }
}
```

- [ ] **Step 3: Open a past conversation read-only**

```js
async function openChat(id) {
  const r = await fetch(`/api/chats/${encodeURIComponent(id)}`);
  if (!r.ok) return;
  const chat = await r.json();
  $("chat-log").replaceChildren();
  const bubbles = [];
  for (const m of chat.messages) {
    if (typeof m.content === "string") {
      bubbles.push(addMsg(m.role === "user" ? "user" : "bot", m.content));
      continue;
    }
    for (const b of m.content) {
      if (b.type === "text") bubbles.push(addMsg("bot", b.text));
      else if (b.type === "tool_use") addMsg("tool", `called ${b.name}`);
      // tool_result blocks are not rendered: the JSON payload is provenance
      // for the transcript file, not something to read in the panel.
    }
  }
  // Same treatment a live reply gets once its stream ends (app.js:316), so a
  // reopened conversation shows names and sectors like a fresh one.
  for (const b of bubbles) b.replaceChildren(annotate(b.textContent));
}
```

`addMsg`'s `kind` becomes the bubble's CSS class. Use whatever class the live
chat already uses for analyst replies — check the `$("chat-form")` submit
handler around `app.js:289` and match it rather than inventing `"bot"` if it
differs.

- [ ] **Step 4: Resume, and start fresh on load**

```js
async function resumeChat(id) {
  const r = await fetch(`/api/chats/${encodeURIComponent(id)}/resume`,
                        { method: "POST" });
  if (!r.ok) return;
  await openChat(id);
}
```

`app.js` ends with a bare `loadData();`. Replace that final line with:

```js
// Sessions live server-side, so a page load would otherwise inherit whatever
// conversation the server still held from the last sitting. Opening the
// dashboard always starts a fresh chat.
(async () => {
  await fetch("/api/chat/new", { method: "POST" });
  await loadChatHistory();
})();
loadData();
```

Wire `chat-history-toggle` to toggle the `hidden` attribute on
`chat-history-list`. In the existing `$("chat-new")` handler at `app.js:322`,
add a `loadChatHistory()` call after its POST so the conversation you just
finished appears in the list immediately.

- [ ] **Step 5: Style it**

In `styles.css`, follow the existing panel styling. Minimum: `#chat-history-list`
scrolls (`max-height: 14rem; overflow-y: auto`), each `li` is a row with the
title as a text button, and `.chat-history-meta` is smaller and muted.

- [ ] **Step 6: Verify in the browser**

```bash
.venv/bin/python -m vantage
```

Check: the panel opens fresh; sending a message then reloading shows the
conversation in the list with a generated title; clicking it renders it;
Continue then sending a follow-up appends to the same conversation rather than
creating a second one (confirm with `ls reports/chats/`).

- [ ] **Step 7: Run the full suite and commit**

```bash
.venv/bin/python -m pytest -q
git add vantage/web/static/index.html vantage/web/static/app.js vantage/web/static/styles.css
git commit -m "feat(web): past-conversation list with open and continue"
```

---

### Task 6: `chat.py` writes through the store

**Files:**
- Modify: `chat.py`
- Modify: `tests/test_chat.py`

**Interfaces:**
- Consumes: `chatstore.new_session`, `chatstore.normalize`, `chatstore.save`, `chatstore.chats_dir` (Task 1); `chattitle.maybe_retitle` (Task 2).
- Produces: nothing later tasks depend on. This is the last task.

**What changes:** the REPL currently accumulates a `transcript` list of strings
and writes `reports/chat-<stamp>.md` only after the loop exits — so a Ctrl-C
loses the session, and its format is unrelated to everything else. It now saves
through `chatstore` after every turn, and its conversations appear in the
dashboard's list.

**Two existing things in `tests/test_chat.py` this task must update — they will
fail otherwise, and that is expected, not a regression:**

1. `test_main_loops_streams_and_writes_transcript` asserts a `chat-*.md` in
   `reports_dir` and reads its body. That file no longer exists there. Rewrite
   it to assert through `chatstore.list_sessions(s.reports_dir / "chats")` —
   keep its existing `conv.sent` and stdout assertions, which still hold.
2. That module's `_FakeConversation` records `sent` but has no `messages`
   attribute, and persistence reads `conv.messages`. Add `self.messages = []`
   and append the user and assistant entries in `send`, mirroring
   `_RecordingConversation` below.

`tests/test_chat.py` already defines `_settings(tmp_path)` at line 6 — use it.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_chat.py
from vantage import chatstore
import chat as chat_module


class _RecordingConversation:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append({"role": "user", "content": message})
        yield {"type": "text", "text": f"reply to {message}"}
        self.messages.append({"role": "assistant",
                              "content": [{"type": "text",
                                           "text": f"reply to {message}"}]})
        yield {"type": "done"}


def test_repl_saves_each_turn_through_chatstore(tmp_path, monkeypatch, capsys):
    settings = _settings(tmp_path)   # reuse this module's existing helper
    monkeypatch.setattr("vantage.chattitle.maybe_retitle", lambda *a, **k: False)
    lines = iter(["what about MU?", "and WDC?", "exit"])
    chat_module.main(settings=settings, _conversation=_RecordingConversation(),
                     _input=lambda prompt: next(lines))

    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert len(rows) == 1
    assert rows[0]["turns"] == 2


def test_repl_turn_survives_an_interrupted_session(tmp_path, monkeypatch):
    """A turn is on disk before the next prompt, so Ctrl-C keeps what was said."""
    settings = _settings(tmp_path)
    monkeypatch.setattr("vantage.chattitle.maybe_retitle", lambda *a, **k: False)

    def _input(prompt):
        if not getattr(_input, "called", False):
            _input.called = True
            return "what about MU?"
        raise KeyboardInterrupt

    try:
        chat_module.main(settings=settings,
                         _conversation=_RecordingConversation(), _input=_input)
    except KeyboardInterrupt:
        pass

    rows = chatstore.list_sessions(tmp_path / "reports" / "chats")
    assert len(rows) == 1
    assert rows[0]["turns"] == 1


def test_repl_no_longer_writes_the_old_flat_transcript(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr("vantage.chattitle.maybe_retitle", lambda *a, **k: False)
    lines = iter(["hello", "exit"])
    chat_module.main(settings=settings, _conversation=_RecordingConversation(),
                     _input=lambda prompt: next(lines))
    assert list((tmp_path / "reports").glob("chat-*.md")) == []
```

These three tests are additions. The two existing items listed above must be
updated in the same commit.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_chat.py -q`
Expected: FAIL — no `reports/chats/` is written

- [ ] **Step 3: Write the implementation**

Rewrite `chat.py`'s `main` — remove the `transcript` list, the `datetime`
import and the trailing write block:

```python
from vantage.settings import load_settings
from vantage.conversation import Conversation
from vantage import chatstore, chattitle


def _persist(conv, session, settings):
    session.messages = chatstore.normalize(conv.messages)
    d = chatstore.chats_dir(settings)
    chatstore.save(d, session)
    if chattitle.maybe_retitle(session, settings):
        chatstore.save(d, session)


def main(argv=None, settings=None, _conversation=None, _input=None) -> None:
    s = settings or load_settings()
    conv = _conversation or Conversation(s)
    read = _input or (lambda prompt: input(prompt))
    session = chatstore.new_session()
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
        print("analyst> ", end="", flush=True)
        for event in conv.send(line):
            if event["type"] == "text":
                print(event["text"], end="", flush=True)
            elif event["type"] == "tool_use":
                print(f"\n[looking up via {event['name']}({event.get('input', {})})]\n",
                      end="", flush=True)
            elif event["type"] == "error":
                print(f"\n[error: {event['message']}]\n", end="", flush=True)
            # "done" ends the turn
        print("\n")
        # Saved before the next prompt, so a Ctrl-C keeps what was already said.
        try:
            _persist(conv, session, s)
        except Exception as e:
            print(f"[warning: conversation not saved: {e}]")
    print(f"[conversation {session.id}]")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_chat.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: 388 passing

- [ ] **Step 6: Update the README**

In the section covering `chat.py` and the dashboard, state that conversations
are saved to `reports/chats/chat-<id>.{json,md}` after every turn, that the
dashboard lists them by auto-generated title and can resume one, and that
opening the dashboard starts a fresh chat. Verify any claim you write against
the code before committing.

- [ ] **Step 7: Commit**

```bash
git add chat.py tests/test_chat.py README.md
git commit -m "feat(chat): REPL persists through chatstore, surviving Ctrl-C"
```

---

## Notes for the executor

- Task counts in the "Expected" lines assume a 346-test baseline and that each
  prior task landed. If your baseline differs, assert the delta, not the total.
- No task modifies `vantage/conversation.py`. If one seems to need to, stop:
  the design deliberately keeps persistence outside it.
- The single-global-session limitation (two browser tabs fight over the active
  conversation) is accepted and recorded in the spec's §7. Do not build around it.
