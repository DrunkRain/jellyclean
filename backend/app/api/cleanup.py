import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActionLog, MediaItem, PendingItem
from app.db.session import get_session
from app.schemas import (
    ActionLogRead,
    DeletePassResult,
    FullCycleResult,
    MarkPassResult,
    PendingItemRead,
)
from app.services.cleanup import (
    restore_pending,
    run_delete_pass,
    run_full_cycle,
    run_mark_pass,
)

router = APIRouter(prefix="/cleanup", tags=["cleanup"])


@router.post("/mark-pass", response_model=MarkPassResult)
async def mark_pass(db: AsyncSession = Depends(get_session)):
    return await run_mark_pass(db)


@router.post("/delete-pass", response_model=DeletePassResult)
async def delete_pass(db: AsyncSession = Depends(get_session)):
    """Delete all pending items whose grace period has elapsed. Respects dry_run."""
    return await run_delete_pass(db)


@router.post("/full-cycle", response_model=FullCycleResult)
async def full_cycle(db: AsyncSession = Depends(get_session)):
    """Sync library + mark pass + delete pass — what the scheduler does, on demand."""
    return await run_full_cycle(db)


@router.post("/pending/{jellyfin_id}/delete-now", response_model=DeletePassResult)
async def delete_now(jellyfin_id: str, db: AsyncSession = Depends(get_session)):
    """Force-delete one item, bypassing the grace period. Still respects dry_run."""
    pending = await db.get(PendingItem, jellyfin_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="Item non trouvé dans la liste pending")
    return await run_delete_pass(db, force_jellyfin_ids=[jellyfin_id])


@router.get("/pending", response_model=list[PendingItemRead])
async def list_pending(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(PendingItem).order_by(PendingItem.scheduled_delete_at))
    items = list(result.scalars().all())

    # Backfill library_name from MediaItem cache for pending rows created before
    # library_name was snapshot on PendingItem (one-time legacy migration).
    missing_lib_ids = [it.jellyfin_id for it in items if it.library_name is None]
    lib_map: dict[str, str | None] = {}
    if missing_lib_ids:
        media_result = await db.execute(
            select(MediaItem.jellyfin_id, MediaItem.library_name).where(
                MediaItem.jellyfin_id.in_(missing_lib_ids)
            )
        )
        lib_map = {row[0]: row[1] for row in media_result.all()}

    out: list[PendingItemRead] = []
    for it in items:
        try:
            reasons = json.loads(it.reasons) if it.reasons else []
        except json.JSONDecodeError:
            reasons = [it.reasons]
        out.append(
            PendingItemRead(
                jellyfin_id=it.jellyfin_id,
                media_type=it.media_type,
                name=it.name,
                file_size_bytes=it.file_size_bytes,
                radarr_id=it.radarr_id,
                sonarr_id=it.sonarr_id,
                tmdb_id=it.tmdb_id,
                tvdb_id=it.tvdb_id,
                library_name=it.library_name or lib_map.get(it.jellyfin_id),
                marked_at=it.marked_at,
                scheduled_delete_at=it.scheduled_delete_at,
                reasons=reasons,
            )
        )
    return out


@router.post("/pending/{jellyfin_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
async def restore(jellyfin_id: str, db: AsyncSession = Depends(get_session)):
    found = await restore_pending(db, jellyfin_id)
    if not found:
        raise HTTPException(status_code=404, detail="Item non trouvé dans la liste pending")
    return None


@router.get("/log", response_model=list[ActionLogRead])
async def action_log(
    limit: int = 200,
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(ActionLog).order_by(desc(ActionLog.timestamp)).limit(min(limit, 1000))
    )
    return list(result.scalars().all())
