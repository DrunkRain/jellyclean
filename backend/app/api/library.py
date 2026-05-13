from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.jellyfin import JellyfinClient
from app.db.models import MediaItem, ServiceConfig, ServiceName, SyncRun
from app.db.session import get_session
from app.schemas import MediaItemRead, SyncRunRead, SyncSummary
from app.services.sync import run_sync

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/items", response_model=list[MediaItemRead])
async def list_items(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(MediaItem).order_by(MediaItem.name))
    return list(result.scalars().all())


@router.post("/sync", response_model=SyncSummary)
async def sync_library(db: AsyncSession = Depends(get_session)) -> SyncSummary:
    result = await run_sync(db)
    return SyncSummary(
        success=result.success,
        duration_seconds=round(result.duration_seconds, 2),
        items_total=result.items_total,
        movies=result.movies,
        series=result.series,
        items_matched_radarr=result.items_matched_radarr,
        items_matched_sonarr=result.items_matched_sonarr,
        error_message=result.error_message,
    )


@router.get("/sync/last", response_model=SyncRunRead | None)
async def last_sync(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(SyncRun).order_by(desc(SyncRun.id)).limit(1))
    return result.scalar_one_or_none()


@router.get("/diagnose")
async def diagnose(db: AsyncSession = Depends(get_session)) -> dict:
    """Diagnostic dump for the library-name resolution. Returns the raw
    Jellyfin libraries response and a few sample paths from the cache so we
    can see why item paths aren't matching library locations."""
    cfg_result = await db.execute(
        select(ServiceConfig).where(ServiceConfig.service == ServiceName.jellyfin.value)
    )
    cfg = cfg_result.scalar_one_or_none()
    if not (cfg and cfg.enabled and cfg.base_url and cfg.api_key):
        raise HTTPException(status_code=400, detail="Jellyfin n'est pas configuré ou activé.")

    jf = JellyfinClient(cfg.base_url, cfg.api_key)
    raw_libraries = await jf.list_libraries()

    # Build the same matcher as sync uses, so the diagnostic mirrors prod behaviour
    library_paths: list[tuple[str, str]] = []
    for lib in raw_libraries:
        name = lib.get("Name") or ""
        for loc in lib.get("Locations") or []:
            if loc:
                library_paths.append((loc.rstrip("/").rstrip("\\"), name))
    library_paths.sort(key=lambda p: len(p[0]), reverse=True)

    def _match(path: str | None) -> str | None:
        if not path:
            return None
        n = path.rstrip("/").rstrip("\\")
        for prefix, name in library_paths:
            if n == prefix or n.startswith(prefix + "/") or n.startswith(prefix + "\\"):
                return name
        return None

    sample_result = await db.execute(select(MediaItem).limit(10))
    sample_items = [
        {
            "name": it.name,
            "media_type": it.media_type,
            "stored_library_name": it.library_name,
            "file_path": it.file_path,
            "would_match_now": _match(it.file_path),
        }
        for it in sample_result.scalars().all()
    ]

    return {
        "jellyfin_base_url": cfg.base_url,
        "raw_virtual_folders": raw_libraries,
        "parsed_path_prefixes": [
            {"prefix": p, "library_name": n} for p, n in library_paths
        ],
        "sample_items": sample_items,
    }
