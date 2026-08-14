import json
import re
from dataclasses import asdict
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from vantage.settings import load_settings
from vantage.conversation import Conversation
from vantage.web import artifacts as art

STATIC_DIR = Path(__file__).parent / "static"

# Brief ids are dates ("2026-08-11"); this mirrors the shape openBrief()
# already enforces client-side. An as_of that doesn't match is treated as
# absent rather than erroring — the ticker map just falls back to being
# unscoped by any brief (signals + portfolio only).
_AS_OF_RE = re.compile(r"^[0-9-]+$")

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
    from vantage.web.pipeline import run_refresh
    app.state.refresh_runner = refresh_runner or run_refresh
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
        return art.signals_payload(art.latest_signals(app.state.settings.data_dir))

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

    @app.get("/api/tickers")
    def tickers(as_of: str | None = None):
        from vantage.tickers import load_facts
        s = app.state.settings
        pf = app.state.portfolio_loader(s.portfolio_analysis_path)
        ss = art.latest_signals(s.data_dir)
        if as_of is not None:
            # Scope brief-text keys to the requested brief instead of the
            # latest one. An unrecognized shape or an as_of with no matching
            # brief file both degrade to "no brief" rather than erroring.
            brief = art.load_brief(s.reports_dir, as_of) if _AS_OF_RE.match(as_of) else None
        else:
            briefs = art.list_briefs(s.reports_dir)
            brief = art.load_brief(s.reports_dir, briefs[0]["as_of"]) if briefs else None
        return art.relevant_ticker_facts(load_facts(s.cache_dir, pf), ss, pf, brief)

    def _get_conversation():
        if app.state.conversation is None:
            app.state.conversation = app.state.conversation_factory(app.state.settings)
        return app.state.conversation

    @app.post("/api/chat")
    async def chat(request: Request):
        body = await request.json()
        conv = _get_conversation()
        return StreamingResponse(_sse(conv.send(body.get("message", ""))),
                                 media_type="text/event-stream")

    @app.post("/api/chat/new")
    def chat_new():
        app.state.conversation = None
        return {"ok": True}

    @app.post("/api/refresh")
    def refresh():
        return StreamingResponse(_sse(app.state.refresh_runner(app.state.settings)),
                                 media_type="text/event-stream")

    return app
