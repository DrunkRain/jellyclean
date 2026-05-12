from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ServiceName, TestStatus


def mask_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 4:
        return "•" * len(api_key)
    return "•" * 8 + api_key[-4:]


class ServiceConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service: ServiceName
    base_url: str
    api_key_masked: str = ""
    has_api_key: bool = False
    enabled: bool
    last_test_status: TestStatus
    last_test_message: str
    last_tested_at: datetime | None

    @classmethod
    def from_model(cls, m) -> "ServiceConfigRead":
        return cls(
            service=ServiceName(m.service),
            base_url=m.base_url,
            api_key_masked=mask_key(m.api_key),
            has_api_key=bool(m.api_key),
            enabled=m.enabled,
            last_test_status=TestStatus(m.last_test_status),
            last_test_message=m.last_test_message,
            last_tested_at=m.last_tested_at,
        )


class ServiceConfigUpdate(BaseModel):
    base_url: str | None = Field(default=None, max_length=512)
    api_key: str | None = Field(default=None)
    enabled: bool | None = None


class ConnectionTestResult(BaseModel):
    success: bool
    message: str
    details: dict = {}


class MediaItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    jellyfin_id: str
    media_type: str
    name: str

    tmdb_id: str | None = None
    tvdb_id: str | None = None
    imdb_id: str | None = None

    radarr_id: int | None = None
    sonarr_id: int | None = None

    date_added: datetime | None = None
    file_path: str | None = None
    file_size_bytes: int | None = None

    series_status: str | None = None

    last_played_at: datetime | None = None
    last_played_by: str | None = None
    total_play_count: int = 0

    last_synced_at: datetime


class SyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: datetime | None = None
    success: bool
    items_total: int
    items_matched_radarr: int
    items_matched_sonarr: int
    error_message: str


class SyncSummary(BaseModel):
    success: bool
    duration_seconds: float
    items_total: int
    movies: int
    series: int
    items_matched_radarr: int
    items_matched_sonarr: int
    error_message: str = ""
