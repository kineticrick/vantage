from vantage.settings import load_settings
from vantage.conversation import Conversation
from vantage import chatstore


def main(argv=None, settings=None, _conversation=None, _input=None) -> None:
    s = settings or load_settings()
    conv = _conversation or Conversation(s)
    read = _input or (lambda prompt: input(prompt))
    session = chatstore.new_session()
    persisted = False
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
            chatstore.persist(conv.messages, session, s)
            persisted = True
        except Exception as e:
            print(f"[warning: conversation not saved: {e}]")
    if persisted:
        print(f"[conversation {session.id}]")


if __name__ == "__main__":
    main()
