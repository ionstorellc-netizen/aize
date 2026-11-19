import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .config import STORAGE, FRONTEND_DIST
from .db import init_db
from .engine import sfx
from .agents.master import start_workers
from .routes.api import r as api_router

app = FastAPI(title="Premium AI E-commerce Video Studio", version="1.0.0")

PASSWORD = os.environ.get("STUDIO_PASSWORD", "")


class BasicAuth(BaseHTTPMiddleware):
    """Optional single-user protection for deployments: set STUDIO_PASSWORD."""
    async def dispatch(self, request: Request, call_next):
        if PASSWORD:
            import base64
            h = request.headers.get("authorization", "")
            ok = False
            if h.startswith("Basic "):
                try:
                    _, pw = base64.b64decode(h[6:]).decode().split(":", 1)
                    ok = secrets.compare_digest(pw, PASSWORD)
                except Exception:
                    ok = False
            if not ok:
                return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Studio"'})
        return await call_next(request)


app.add_middleware(BasicAuth)
if os.environ.get("CORS_ORIGINS"):
    app.add_middleware(CORSMiddleware, allow_origins=os.environ["CORS_ORIGINS"].split(","), allow_methods=["*"],
                       allow_headers=["*"])
app.include_router(api_router)


@app.on_event("startup")
def _startup():
    init_db()
    sfx.ensure_assets()
    app.state.stop = start_workers()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/media/{path:path}")
def media(path: str):
    p = (STORAGE / path).resolve()
    if not p.is_relative_to(STORAGE.resolve()) or not p.is_file() or p.name.startswith(".") or p.suffix in (".enc", ".db"):
        raise HTTPException(404)
    return FileResponse(p)


@app.get("/{full_path:path}")
def spa(full_path: str):
    f = (FRONTEND_DIST / full_path).resolve()
    if full_path and f.is_file() and f.is_relative_to(FRONTEND_DIST.resolve()):
        return FileResponse(f)
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return Response("Frontend not built. Run: cd frontend && npm install && npm run build", media_type="text/plain")
