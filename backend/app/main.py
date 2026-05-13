import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.cleanup import router as cleanup_router
from app.api.health import router as health_router
from app.api.library import router as library_router
from app.api.protections import router as protections_router
from app.api.rule import router as rule_router
from app.api.settings import router as settings_router
from app.services.scheduler import start_scheduler, stop_scheduler
from app.config import settings
from app.db.session import init_db

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("jellyclean")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("Starting JellyClean — data dir: %s", settings.data_dir)
    await init_db()
    await start_scheduler()
    yield
    stop_scheduler()
    log.info("Stopping JellyClean")


app = FastAPI(title="JellyClean", version="0.1.0", lifespan=lifespan)

app.include_router(health_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(library_router, prefix="/api")
app.include_router(rule_router, prefix="/api")
app.include_router(protections_router, prefix="/api")
app.include_router(cleanup_router, prefix="/api")


FRONTEND_DIR = Path(__file__).parent.parent / "static"

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = FRONTEND_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIR / "index.html")
else:
    @app.get("/")
    async def root() -> dict:
        return {
            "message": "JellyClean backend running — frontend not built yet",
            "docs": "/docs",
        }
