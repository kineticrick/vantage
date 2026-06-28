import json
from vantage.persona import ANALYST_PERSONA
from vantage.analyst import DISCLAIMER
from vantage.chat_context import load_chat_context
from vantage.chat_tools import TOOL_DEFINITIONS, CUSTOM_TOOL_NAMES, dispatch

_WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}
_TOOL_NOTE = ("\n\nYou have two tools for exact figures: get_ticker_metrics(ticker) "
              "and run_screen(...). Prefer calling them over guessing numbers; use "
              "web_search for news. Keep the conversation grounded and challenge the "
              "user's reasoning where the evidence warrants.\n\n")

_MAX_CONTINUATIONS = 10

class Conversation:
    def __init__(self, settings, _client=None, _context=None):
        self.settings = settings
        self._client = _client
        self.context = _context if _context is not None else load_chat_context(settings)
        self.system = (ANALYST_PERSONA + "\n\n=== Current context ===\n"
                       + self.context.render() + _TOOL_NOTE + DISCLAIMER)
        self.messages = []

    def _client_or_default(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
        return self._client

    def send(self, user_message):
        self.messages.append({"role": "user", "content": user_message})
        client = self._client_or_default()
        tools = [_WEB_SEARCH_TOOL] + TOOL_DEFINITIONS
        steps = 0
        while True:
            steps += 1
            if steps > _MAX_CONTINUATIONS:
                yield {"type": "error",
                       "message": f"tool loop exceeded {_MAX_CONTINUATIONS} steps"}
                break
            try:
                with client.messages.stream(
                    model=self.settings.model, max_tokens=64000,
                    thinking={"type": "adaptive"}, system=self.system,
                    tools=tools, messages=self.messages,
                ) as stream:
                    for event in stream:
                        if (getattr(event, "type", None) == "content_block_delta"
                                and getattr(event.delta, "type", None) == "text_delta"):
                            yield {"type": "text", "text": event.delta.text}
                    final = stream.get_final_message()
            except Exception as e:  # API/stream failure — surface, balance history, end
                # answer the dangling user turn so history stays valid for the next send()
                self.messages.append({"role": "assistant", "content": f"[error: {e}]"})
                yield {"type": "error", "message": str(e)}
                break

            self.messages.append({"role": "assistant", "content": final.content})
            custom_calls = [b for b in final.content
                            if getattr(b, "type", None) == "tool_use"
                            and getattr(b, "name", None) in CUSTOM_TOOL_NAMES]

            if final.stop_reason == "tool_use" and custom_calls:
                results = []
                for call in custom_calls:
                    yield {"type": "tool_use", "name": call.name, "input": dict(call.input)}
                    out = dispatch(call.name, call.input, self.settings)
                    is_err = out.get("error") is not None
                    if is_err:
                        yield {"type": "error", "message": out["error"]}
                    results.append({"type": "tool_result", "tool_use_id": call.id,
                                    "content": json.dumps(out), "is_error": is_err})
                self.messages.append({"role": "user", "content": results})
                continue
            if final.stop_reason == "pause_turn":
                continue  # server tool (web_search) paused — resume the turn
            break
        yield {"type": "done"}
