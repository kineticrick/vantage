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


_TITLE_CAP = 80


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
    # max_tokens=32 is a property of the request, not an invariant of this
    # function — a model change, a client swap, or a response shaped
    # "Title\n\nhere's why I chose it" could otherwise hand back something
    # that wrecks the scannable list this feature exists to build. Take the
    # first non-empty line only, then cap defensively.
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return line.strip('"').strip()[:_TITLE_CAP]


def maybe_retitle(session, settings, _client=None) -> bool:
    """Best-effort. Never raises, never blocks a chat.

    On failure the stored title is left exactly as it was and title_turns is
    not advanced, so the next turn retries. Nothing writes a placeholder: an
    empty title means never successfully titled, and list_sessions supplies
    the display fallback.
    """
    try:
        turns = chatstore.turn_count(session.messages)
        if not should_title(turns, session.title_turns):
            return False
        title = generate_title(session.messages, settings, _client=_client)
    except Exception:
        return False
    if not title:
        return False
    session.title = title
    session.title_turns = turns
    return True
