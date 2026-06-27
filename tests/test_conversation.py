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
