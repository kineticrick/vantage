import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from vantage.settings import load_settings
from vantage.conversation import Conversation

STATIC_DIR = Path(__file__).parent / "static"

def _sse(events):
    for ev in events:
        yield f"data: {json.dumps(ev)}\n\n"

def create_app(settings=None, conversation_factory=None,
               refresh_runner=None, portfolio_loader=None) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings or load_settings()
    app.state.conversation_factory = conversation_factory or (lambda s: Conversation(s))
    app.state.portfolio_loader = portfolio_loader
    app.state.refresh_runner = refresh_runner
    app.state.conversation = None

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
