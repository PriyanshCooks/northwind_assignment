"""FastAPI server: creates the app, binds the routes, serves the UI. It listens on 127.0.0.1 only and writes under
.northwind/ (run folders). The model is never called from here: advice is replayed from the ledger."""
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import routes, routes_results
from app.services.pipeline_service import NotReady
from app.services.registry_service import Registry, UnknownRun
from app.utils.paths import ROOT, RUNTIME_DIR

HOST, PORT = "127.0.0.1", 8000


def create_app(runs_root: Path = RUNTIME_DIR / "runs", frontend: Path = ROOT / "frontend") -> FastAPI:
    runs_root.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Northwind consolidation review")
    app.state.registry = Registry(runs_root)

    @app.exception_handler(UnknownRun)
    def unknown_run(_: Request, error: UnknownRun) -> JSONResponse:
        return JSONResponse({"detail": f"no such run: {error}"}, status_code=404)

    @app.exception_handler(NotReady)
    def not_ready(_: Request, error: NotReady) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(ValueError)
    def bad_value(_: Request, error: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=422)

    app.include_router(routes.router)
    app.include_router(routes_results.router)
    app.mount("/ui", StaticFiles(directory=frontend, html=True), name="ui")

    @app.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        return RedirectResponse("/ui/")

    return app


def serve() -> int:
    print(f"Northwind review UI at http://{HOST}:{PORT}/")
    uvicorn.run(create_app(), host=HOST, port=PORT, log_level="warning")
    return 0
