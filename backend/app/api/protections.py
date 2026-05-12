from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProtectedItem
from app.db.session import get_session
from app.schemas import ProtectedItemCreate, ProtectedItemRead

router = APIRouter(prefix="/protections", tags=["protections"])


@router.get("", response_model=list[ProtectedItemRead])
async def list_protections(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(ProtectedItem).order_by(ProtectedItem.created_at.desc()))
    return list(result.scalars().all())


@router.post("/{jellyfin_id}", response_model=ProtectedItemRead)
async def add_protection(
    jellyfin_id: str,
    payload: ProtectedItemCreate = ProtectedItemCreate(),
    db: AsyncSession = Depends(get_session),
):
    existing = await db.get(ProtectedItem, jellyfin_id)
    if existing:
        existing.reason = payload.reason or existing.reason
        await db.commit()
        await db.refresh(existing)
        return existing

    item = ProtectedItem(jellyfin_id=jellyfin_id, reason=payload.reason)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{jellyfin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_protection(jellyfin_id: str, db: AsyncSession = Depends(get_session)):
    item = await db.get(ProtectedItem, jellyfin_id)
    if not item:
        raise HTTPException(status_code=404, detail="Protection introuvable")
    await db.delete(item)
    await db.commit()
    return None
