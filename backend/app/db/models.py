from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, String, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ServiceName(str, Enum):
    jellyfin = "jellyfin"
    radarr = "radarr"
    sonarr = "sonarr"
    jellyseerr = "jellyseerr"


class TestStatus(str, Enum):
    unknown = "unknown"
    success = "success"
    failure = "failure"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ServiceConfig(Base):
    __tablename__ = "service_config"

    service: Mapped[str] = mapped_column(String(32), primary_key=True)
    base_url: Mapped[str] = mapped_column(String(512), default="")
    api_key: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    last_test_status: Mapped[str] = mapped_column(String(16), default=TestStatus.unknown.value)
    last_test_message: Mapped[str] = mapped_column(Text, default="")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
