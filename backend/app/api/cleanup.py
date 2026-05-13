import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActionLog, PendingItem
from app.db.session import get_session
from app.schemas import ActionLogRead, MarkPassResult, PendingItemRead
from app.services.cleanup import restore_pending, run_mark_pass

router = APIRouter(prefix="/cleanup", tags=["cleanup"])


@router.post("/mark-pass", response_model=MarkPassResult)
async def mark_pass(db: AsyncSession = Depends(get_session)):
    return await run_mark_pass(db)


@router.get("/pending", response_model=list[PendingItemRead])
async def list_pending(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(PendingItem).order_by(PendingItem.scheduled_delete_at))
    items = list(result.scalars().all())

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
