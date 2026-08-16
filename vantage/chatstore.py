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
# does not match is refused rather than joined onto a path. The microsecond
# group is optional: ids minted by _stamp_id() always carry it (so two
# sessions created in the same second still get distinct filenames), but
# hand-written 14-digit ids (e.g. in tests, or resume links seeded before
# this change) must keep resolving.
ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}(?:[0-9]{6})?Z\Z")

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
    # Microseconds keep two sessions minted in the same second from
    # colliding on one filename and silently overwriting each other.
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


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
