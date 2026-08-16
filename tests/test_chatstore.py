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
    assert not chatstore.ID_RE.match("20260815T195412Z\n")
    assert not chatstore.ID_RE.match("/etc/passwd")
    assert not chatstore.ID_RE.match("")
    assert not chatstore.ID_RE.match("20260815T195412Zsuffix")
