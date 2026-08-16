# tests/test_chattitle.py
from vantage import chatstore, chattitle


class _FakeMessages:
    def __init__(self, text=None, error=None, block_type="text"):
        self._text = text
        self._error = error
        self._block_type = block_type
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error

        block_type = self._block_type
        block_text = self._text

        class _Block:
            type = block_type
            text = block_text

        class _Resp:
            content = [_Block()]

        return _Resp()


class _FakeClient:
    def __init__(self, text=None, error=None, block_type="text"):
        self.messages = _FakeMessages(text=text, error=error,
                                       block_type=block_type)


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


def test_generate_title_takes_first_non_empty_line():
    client = _FakeClient(text="Good title\n\nlong rambling justification")
    out = chattitle.generate_title([{"role": "user", "content": "x"}],
                                   _settings(), _client=client)
    assert out == "Good title"


def test_generate_title_caps_length_at_80_chars():
    client = _FakeClient(text="A" * 5000)
    out = chattitle.generate_title([{"role": "user", "content": "x"}],
                                   _settings(), _client=client)
    assert len(out) == 80
    assert out == "A" * 80


def test_generate_title_returns_empty_for_whitespace_only_response():
    client = _FakeClient(text="   \n\t  \n")
    out = chattitle.generate_title([{"role": "user", "content": "x"}],
                                   _settings(), _client=client)
    assert out == ""


def test_generate_title_returns_empty_when_no_text_block():
    client = _FakeClient(text="ignored", block_type="tool_use")
    out = chattitle.generate_title([{"role": "user", "content": "x"}],
                                   _settings(), _client=client)
    assert out == ""


def test_maybe_retitle_rejects_blank_title_without_advancing():
    s = chatstore.new_session(now="2026-08-15T10:00:00Z")
    s.title = "existing"
    s.title_turns = 0
    s.messages = [{"role": "user", "content": "a"}]
    changed = chattitle.maybe_retitle(
        s, _settings(), _client=_FakeClient(text="   \n  "))
    assert changed is False
    assert s.title == "existing"
    assert s.title_turns == 0


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
