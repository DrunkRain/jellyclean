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


class CleanupRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    movie_age_days: int
    movie_unwatched_days: int
    series_age_days: int
    series_unwatched_days: int
    protect_continuing_series: bool
    grace_period_days: int
    dry_run: bool
    updated_at: datetime


class CleanupRuleUpdate(BaseModel):
    enabled: bool | None = None
    movie_age_days: int | None = Field(default=None, ge=0, le=3650)
    movie_unwatched_days: int | None = Field(default=None, ge=0, le=3650)
    series_age_days: int | None = Field(default=None, ge=0, le=3650)
    series_unwatched_days: int | None = Field(default=None, ge=0, le=3650)
    protect_continuing_series: bool | None = None
    grace_period_days: int | None = Field(default=None, ge=0, le=365)
    dry_run: bool | None = None


class ScanCandidate(BaseModel):
    jellyfin_id: str
    media_type: str
    name: str
    file_size_bytes: int | None
    date_added: datetime | None
    last_played_at: datetime | None
    last_played_by: str | None
    radarr_id: int | None
    sonarr_id: int | None
    series_status: str | None
    reasons: list[str]
    deletable: bool  # false if not matched in Radarr/Sonarr — diagnostic
    deletable_blocker: str | None = None  # why not deletable


class ScanPreview(BaseModel):
    rule_enabled: bool
    total_items_evaluated: int
    candidates: list[ScanCandidate]
    skipped_protected: int
    skipped_continuing_series: int
    candidates_total_size_bytes: int
    deletable_total_size_bytes: int


class ProtectedItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    jellyfin_id: str
    reason: str
    created_at: datetime


class ProtectedItemCreate(BaseModel):
    reason: str = ""


class PendingItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    jellyfin_id: str
    media_type: str
    name: str
    file_size_bytes: int | None
    radarr_id: int | None
    sonarr_id: int | None
    tmdb_id: str | None
    tvdb_id: str | None
    marked_at: datetime
    scheduled_delete_at: datetime
    reasons: list[str] = []  # populated server-side by parsing the stored JSON


class ActionLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    action: str
    jellyfin_id: str
    name: str
    details: str
    success: bool
    error_message: str


class MarkPassResult(BaseModel):
    success: bool
    duration_seconds: float
    rule_enabled: bool
    candidates_total: int
    newly_marked: int
    unmarked_no_longer_matching: int
    items_in_collection_after: int
    collection_id: str | None
    error_message: str = ""
