from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.base import BaseClient, TestResult
from app.clients.jellyfin import JellyfinClient
from app.clients.jellyseerr import JellyseerrClient
from app.clients.radarr import RadarrClient
from app.clients.sonarr import SonarrClient
from app.db.models import ServiceConfig, ServiceName, TestStatus
from app.db.session import get_session
from app.schemas import ConnectionTestResult, ServiceConfigRead, ServiceConfigUpdate

router = APIRouter(prefix="/settings", tags=["settings"])

CLIENT_CLASSES: dict[ServiceName, type[BaseClient]] = {
    ServiceName.jellyfin: JellyfinClient,
    ServiceName.radarr: RadarrClient,
    ServiceName.sonarr: SonarrClient,
    ServiceName.jellyseerr: JellyseerrClient,
}


async def _get_or_create(db: AsyncSession, service: ServiceName) -> ServiceConfig:
    result = await db.execute(select(ServiceConfig).where(ServiceConfig.service == service.value))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = ServiceConfig(service=service.value)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


@router.get("", response_model=list[ServiceConfigRead])
async def list_settings(db: AsyncSession = Depends(get_session)):
    """Return one entry per known service (auto-create missing rows with defaults)."""
    out: list[ServiceConfigRead] = []
    for service in ServiceName:
        cfg = await _get_or_create(db, service)
        out.append(ServiceConfigRead.from_model(cfg))
    return out


@router.get("/{service}", response_model=ServiceConfigRead)
async def get_setting(service: ServiceName, db: AsyncSession = Depends(get_session)):
    cfg = await _get_or_create(db, service)
    return ServiceConfigRead.from_model(cfg)


@router.put("/{service}", response_model=ServiceConfigRead)
async def update_setting(
    service: ServiceName,
    payload: ServiceConfigUpdate,
    db: AsyncSession = Depends(get_session),
):
    cfg = await _get_or_create(db, service)

    if payload.base_url is not None:
        cfg.base_url = payload.base_url.strip()
    if payload.enabled is not None:
        cfg.enabled = payload.enabled
    # api_key: only update if a non-empty value is provided. Empty/None keeps the existing key.
    if payload.api_key:
        cfg.api_key = payload.api_key.strip()

    await db.commit()
    await db.refresh(cfg)
    return ServiceConfigRead.from_model(cfg)


@router.post("/{service}/test", response_model=ConnectionTestResult)
async def test_setting(service: ServiceName, db: AsyncSession = Depends(get_session)):
    cfg = await _get_or_create(db, service)

    if not cfg.base_url or not cfg.api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL et clé API doivent être renseignées avant de tester.",
        )

    client_cls = CLIENT_CLASSES[service]
    client = client_cls(cfg.base_url, cfg.api_key)
    result: TestResult = await client.test_connection()

    cfg.last_tested_at = datetime.now(timezone.utc)
    cfg.last_test_status = (TestStatus.success if result.success else TestStatus.failure).value
    cfg.last_test_message = result.message
    await db.commit()

    return ConnectionTestResult(
        success=result.success, message=result.message, details=result.details
    )
