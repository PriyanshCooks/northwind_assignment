"""FastAPI server: creates the app, binds the routes, serves the UI. It listens on 127.0.0.1 only and writes under
.northwind/ (run folders). The model is never called from here: advice is replayed from the ledger."""
import re
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import routes, routes_results
from app.services.pipeline_service import NotReady
from app.services.registry_service import Registry, UnknownRun
from app.utils.paths import ROOT, RUNTIME_DIR

HOST, PORT = "127.0.0.1", 8000
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]  # a page on another name (DNS rebinding) is refused
PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/)(?:[^\\/\s'\"<>|:]+[\\/])+([^\\/\s'\"<>|:]*)")


def scrub(text: str) -> str:
    """Keep the file name, drop the folders: an error must not tell a caller where the server keeps its files."""
    return PATH.sub(lambda m: m[1] or "", text)


def create_app(runs_root: Path = RUNTIME_DIR / "runs", frontend: Path = ROOT / "frontend") -> FastAPI:
    runs_root.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Northwind consolidation review")
    app.state.registry = Registry(runs_root)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

    @app.exception_handler(UnknownRun)
    def unknown_run(_: Request, error: UnknownRun) -> JSONResponse:
        return JSONResponse({"detail": scrub(f"no such run: {error}")}, status_code=404)

    @app.exception_handler(NotReady)
    def not_ready(_: Request, error: NotReady) -> JSONResponse:
        return JSONResponse({"detail": scrub(str(error))}, status_code=409)

    @app.exception_handler(ValueError)
    def bad_value(_: Request, error: ValueError) -> JSONResponse:
        return JSONResponse({"detail": scrub(str(error))}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    def http_error(_: Request, error: StarletteHTTPException) -> JSONResponse:
        detail = scrub(error.detail) if isinstance(error.detail, str) else error.detail
        return JSONResponse({"detail": detail}, status_code=error.status_code)

    @app.exception_handler(Exception)
    def unexpected(_: Request, error: Exception) -> JSONResponse:
        return JSONResponse({"detail": scrub(f"{type(error).__name__}: {error}")}, status_code=500)

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
