from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MediaItem, SyncRun
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
