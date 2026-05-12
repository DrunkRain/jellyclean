from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas import CleanupRuleRead, CleanupRuleUpdate, ScanPreview
from app.services.scan import get_or_create_rule, preview_scan

router = APIRouter(tags=["rule"])


@router.get("/rule", response_model=CleanupRuleRead)
async def get_rule(db: AsyncSession = Depends(get_session)):
    return await get_or_create_rule(db)


@router.put("/rule", response_model=CleanupRuleRead)
async def update_rule(payload: CleanupRuleUpdate, db: AsyncSession = Depends(get_session)):
    rule = await get_or_create_rule(db)
    data = payload.model_dump(exclude_none=True)
    for key, value in data.items():
        setattr(rule, key, value)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.post("/scan/preview", response_model=ScanPreview)
async def scan_preview(db: AsyncSession = Depends(get_session)):
    return await preview_scan(db)
