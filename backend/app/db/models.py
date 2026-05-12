from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MediaType(str, Enum):
    movie = "movie"
    series = "series"


class SeriesStatus(str, Enum):
    continuing = "continuing"
    ended = "ended"
    unknown = "unknown"


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


class MediaItem(Base):
    """Cached snapshot of a Jellyfin movie or series, enriched with *arr matches and watch stats."""

    __tablename__ = "media_item"

    jellyfin_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    media_type: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(512))

    tmdb_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    tvdb_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    imdb_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    radarr_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sonarr_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    date_added: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    series_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    last_played_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_played_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_play_count: Mapped[int] = mapped_column(Integer, default=0)

    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SyncRun(Base):
    """Log of each library sync — useful for the UI ('last synced 5 min ago')."""

    __tablename__ = "sync_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    items_total: Mapped[int] = mapped_column(Integer, default=0)
    items_matched_radarr: Mapped[int] = mapped_column(Integer, default=0)
    items_matched_sonarr: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
