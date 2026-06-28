import json
from dataclasses import asdict
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from vantage.settings import load_settings
from vantage.conversation import Conversation
from vantage.web import artifacts as art

STATIC_DIR = Path(__file__).parent / "static"

def _sse(events):
    for ev in events:
        yield f"data: {json.dumps(ev)}\n\n"

def create_app(settings=None, conversation_factory=None,
               refresh_runner=None, portfolio_loader=None) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings or load_settings()
    app.state.conversation_factory = conversation_factory or (lambda s: Conversation(s))
    from vantage.portfolio_context import load_portfolio_context
    app.state.portfolio_loader = portfolio_loader or load_portfolio_context
    app.state.refresh_runner = refresh_runner
    app.state.conversation = None

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/overview")
    def overview():
        s = app.state.settings
        ss = art.latest_signals(s.data_dir)
        pf = app.state.portfolio_loader(s.portfolio_analysis_path)
        briefs = art.list_briefs(s.reports_dir)
        latest = art.load_brief(s.reports_dir, briefs[0]["as_of"]) if briefs else None
        return art.build_overview(ss, pf, latest)

    @app.get("/api/signals")
    def signals():
        ss = art.latest_signals(app.state.settings.data_dir)
        return ss.to_dict() if ss else {"as_of": None, "signals": [],
                                        "sector_momentum": {}}

    @app.get("/api/portfolio")
    def portfolio():
        pf = app.state.portfolio_loader(app.state.settings.portfolio_analysis_path)
        return asdict(pf)

    @app.get("/api/briefs")
    def briefs():
        return art.list_briefs(app.state.settings.reports_dir)

    @app.get("/api/briefs/{as_of}")
    def brief(as_of: str):
        s = app.state.settings
        b = art.load_brief(s.reports_dir, as_of)
        if b is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {"brief": b.to_dict(), "html": art.read_brief_html(s.reports_dir, as_of)}

    return app
