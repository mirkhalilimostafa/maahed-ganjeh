from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import ensure_admin_user
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.routers import auth_routes, bots, dashboards, health, manual_ingest, sources
from app.services.bale_inbound import start_bale_inbound, stop_bale_inbound

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    async with SessionLocal() as db:
        await ensure_admin_user(db)
    try:
        await start_bale_inbound(get_settings())
    except Exception:  # noqa: BLE001
        # Never block API boot if Bale webhook/poll setup fails.
        pass
    try:
        yield
    finally:
        await stop_bale_inbound()


app = FastAPI(
    title="Maahed Ganjeh API",
    description="سیستم داشبورد و مکاتبات هوشمند ماهد — Full API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth_routes.router)
app.include_router(sources.router)
app.include_router(manual_ingest.router)
app.include_router(bots.router)
app.include_router(dashboards.router)

if STATIC_DIR.is_dir():
    assets = STATIC_DIR / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Keep API/health for routers registered above; never SPA-fallback those prefixes.
        if full_path == "health" or full_path.startswith(("api/", "docs", "openapi.json", "redoc")):
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not Found")
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
