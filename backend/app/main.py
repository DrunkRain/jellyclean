import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
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
    yield
    log.info("Stopping JellyClean")


app = FastAPI(title="JellyClean", version="0.1.0", lifespan=lifespan)

app.include_router(health_router, prefix="/api")


FRONTEND_DIR = Path(__file__).parent.parent / "static"

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}
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
