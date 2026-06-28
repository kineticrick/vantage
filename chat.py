from datetime import datetime, timezone
from vantage.settings import load_settings
from vantage.conversation import Conversation

def main(argv=None, settings=None, _conversation=None, _input=None) -> None:
    s = settings or load_settings()
    conv = _conversation or Conversation(s)
    read = _input or (lambda prompt: input(prompt))
    transcript = []
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
        transcript.append(f"**you>** {line}")
        parts = []
        print("analyst> ", end="", flush=True)
        for event in conv.send(line):
            if event["type"] == "text":
                print(event["text"], end="", flush=True)
                parts.append(event["text"])
            elif event["type"] == "tool_use":
                note = f"\n[looking up via {event['name']}({event.get('input', {})})]\n"
                print(note, end="", flush=True)
                parts.append(note)
            elif event["type"] == "error":
                note = f"\n[error: {event['message']}]\n"
                print(note, end="", flush=True)
                parts.append(note)
            # "done" ends the turn
        print("\n")
        transcript.append("**analyst>** " + "".join(parts))
    if transcript:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = s.reports_dir / f"chat-{ts}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Chat transcript {ts}\n\n" + "\n\n".join(transcript) + "\n",
                        encoding="utf-8")
        print(f"[transcript saved to {path}]")

if __name__ == "__main__":
    main()
