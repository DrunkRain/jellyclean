"""Library sync service.

Fetches movies & series from Jellyfin, aggregates last-played across all users,
matches each item against Radarr/Sonarr via TMDB/TVDB IDs, and upserts the
result into the local SQLite cache. Radarr/Sonarr failures don't abort the sync —
items just stay unmatched.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.jellyfin import JellyfinClient
from app.clients.radarr import RadarrClient
from app.clients.sonarr import SonarrClient
from app.db.models import (
    MediaItem,
    MediaType,
    ServiceConfig,
    ServiceName,
    SeriesStatus,
    SyncRun,
)

log = logging.getLogger("jellyclean.sync")


@dataclass
class SyncResult:
    success: bool
    duration_seconds: float
    items_total: int
    movies: int
    series: int
    items_matched_radarr: int
    items_matched_sonarr: int
    error_message: str = ""


def _parse_jellyfin_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Jellyfin returns ISO 8601, sometimes with trailing 'Z' and microseconds with >6 digits
        s = s.rstrip("Z").split(".")[0]  # strip subsecond + Z to keep parsing simple
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _get_provider_id(item: dict[str, Any], key: str) -> str | None:
    providers = item.get("ProviderIds") or {}
    v = providers.get(key)
    return str(v) if v else None


def _movie_file_info(item: dict[str, Any]) -> tuple[str | None, int | None]:
    sources = item.get("MediaSources") or []
    if not sources:
        return item.get("Path"), None
    src = sources[0]
    return src.get("Path") or item.get("Path"), src.get("Size")


def _series_status_norm(raw: str | None) -> str:
    if not raw:
        return SeriesStatus.unknown.value
    r = raw.strip().lower()
    if r == "continuing":
        return SeriesStatus.continuing.value
    if r == "ended":
        return SeriesStatus.ended.value
    return SeriesStatus.unknown.value


async def _load_service_configs(db: AsyncSession) -> dict[str, ServiceConfig]:
    result = await db.execute(select(ServiceConfig))
    return {cfg.service: cfg for cfg in result.scalars().all()}


def _is_usable(cfg: ServiceConfig | None) -> bool:
    return bool(cfg and cfg.enabled and cfg.base_url and cfg.api_key)


async def run_sync(db: AsyncSession) -> SyncResult:
    started = time.monotonic()
    run = SyncRun()
    db.add(run)
    await db.commit()
    await db.refresh(run)

    configs = await _load_service_configs(db)
    jf_cfg = configs.get(ServiceName.jellyfin.value)
    if not _is_usable(jf_cfg):
        msg = "Jellyfin n'est pas configuré ou activé."
        log.warning(msg)
        run.finished_at = datetime.now(timezone.utc)
        run.success = False
        run.error_message = msg
        await db.commit()
        return SyncResult(False, 0.0, 0, 0, 0, 0, 0, msg)

    jf = JellyfinClient(jf_cfg.base_url, jf_cfg.api_key)

    try:
        users, movies, series_list = await asyncio.gather(
            jf.list_users(), jf.list_movies(), jf.list_series()
        )
    except Exception as exc:
        msg = f"Échec du fetch Jellyfin : {exc.__class__.__name__}: {exc}"
        log.exception("Jellyfin fetch failed")
        run.finished_at = datetime.now(timezone.utc)
        run.success = False
        run.error_message = msg
        await db.commit()
        return SyncResult(False, time.monotonic() - started, 0, 0, 0, 0, 0, msg)

    log.info("Fetched %d users, %d movies, %d series from Jellyfin", len(users), len(movies), len(series_list))

    # Aggregate last-played per item across all users
    # Map: item_id -> {last_played_at, last_played_by, total_play_count}
    play_agg: dict[str, dict[str, Any]] = {}

    async def _fetch_user_plays(user: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        uid = user["Id"]
        try:
            played = await jf.list_user_played(uid)
        except Exception as exc:
            log.warning("Could not fetch played items for user %s: %s", user.get("Name"), exc)
            return user.get("Name", uid), []
        return user.get("Name", uid), played

    user_results = await asyncio.gather(*(_fetch_user_plays(u) for u in users))
    for user_name, played_items in user_results:
        for it in played_items:
            iid = it.get("Id")
            ud = it.get("UserData") or {}
            last = _parse_jellyfin_date(ud.get("LastPlayedDate"))
            count = int(ud.get("PlayCount") or 0)

            entry = play_agg.setdefault(
                iid, {"last_played_at": None, "last_played_by": None, "total_play_count": 0}
            )
            entry["total_play_count"] += count
            if last and (entry["last_played_at"] is None or last > entry["last_played_at"]):
                entry["last_played_at"] = last
                entry["last_played_by"] = user_name

    # Pull Radarr / Sonarr catalogs for matching (best-effort)
    radarr_by_tmdb: dict[str, int] = {}
    sonarr_by_tvdb: dict[str, int] = {}

    radarr_cfg = configs.get(ServiceName.radarr.value)
    if _is_usable(radarr_cfg):
        try:
            radarr_movies = await RadarrClient(radarr_cfg.base_url, radarr_cfg.api_key).list_movies()
            for m in radarr_movies:
                tmdb = m.get("tmdbId")
                if tmdb:
                    radarr_by_tmdb[str(tmdb)] = m["id"]
            log.info("Loaded %d Radarr movies for matching", len(radarr_movies))
        except Exception as exc:
            log.warning("Radarr fetch failed (matching skipped): %s", exc)

    sonarr_cfg = configs.get(ServiceName.sonarr.value)
    sonarr_series_index: dict[int, dict[str, Any]] = {}  # id -> raw sonarr series
    if _is_usable(sonarr_cfg):
        try:
            sonarr_all = await SonarrClient(sonarr_cfg.base_url, sonarr_cfg.api_key).list_series()
            for s in sonarr_all:
                tvdb = s.get("tvdbId")
                if tvdb:
                    sonarr_by_tvdb[str(tvdb)] = s["id"]
                    sonarr_series_index[s["id"]] = s
            log.info("Loaded %d Sonarr series for matching", len(sonarr_all))
        except Exception as exc:
            log.warning("Sonarr fetch failed (matching skipped): %s", exc)

    now = datetime.now(timezone.utc)
    matched_radarr = 0
    matched_sonarr = 0

    # Wipe and rebuild — simpler than diffing for our scale
    await db.execute(MediaItem.__table__.delete())

    for m in movies:
        jid = m["Id"]
        tmdb = _get_provider_id(m, "Tmdb")
        tvdb = _get_provider_id(m, "Tvdb")
        imdb = _get_provider_id(m, "Imdb")
        path, size = _movie_file_info(m)
        agg = play_agg.get(jid) or {}

        radarr_id = radarr_by_tmdb.get(tmdb) if tmdb else None
        if radarr_id:
            matched_radarr += 1

        item = MediaItem(
            jellyfin_id=jid,
            media_type=MediaType.movie.value,
            name=m.get("Name", "?"),
            tmdb_id=tmdb,
            tvdb_id=tvdb,
            imdb_id=imdb,
            radarr_id=radarr_id,
            sonarr_id=None,
            date_added=_parse_jellyfin_date(m.get("DateCreated")),
            file_path=path,
            file_size_bytes=size,
            series_status=None,
            last_played_at=agg.get("last_played_at"),
            last_played_by=agg.get("last_played_by"),
            total_play_count=agg.get("total_play_count", 0),
            last_synced_at=now,
        )
        db.add(item)

    for s in series_list:
        jid = s["Id"]
        tmdb = _get_provider_id(s, "Tmdb")
        tvdb = _get_provider_id(s, "Tvdb")
        imdb = _get_provider_id(s, "Imdb")
        agg = play_agg.get(jid) or {}

        sonarr_id = sonarr_by_tvdb.get(tvdb) if tvdb else None
        if sonarr_id:
            matched_sonarr += 1

        # Prefer Sonarr's status (more reliable) — fall back to Jellyfin's
        if sonarr_id and sonarr_id in sonarr_series_index:
            series_status = _series_status_norm(sonarr_series_index[sonarr_id].get("status"))
        else:
            series_status = _series_status_norm(s.get("Status"))

        item = MediaItem(
            jellyfin_id=jid,
            media_type=MediaType.series.value,
            name=s.get("Name", "?"),
            tmdb_id=tmdb,
            tvdb_id=tvdb,
            imdb_id=imdb,
            radarr_id=None,
            sonarr_id=sonarr_id,
            date_added=_parse_jellyfin_date(s.get("DateCreated")),
            file_path=s.get("Path"),
            file_size_bytes=None,  # series-level file size requires episode aggregation — out of Sprint 2 scope
            series_status=series_status,
            last_played_at=agg.get("last_played_at"),
            last_played_by=agg.get("last_played_by"),
            total_play_count=agg.get("total_play_count", 0),
            last_synced_at=now,
        )
        db.add(item)

    duration = time.monotonic() - started
    run.finished_at = datetime.now(timezone.utc)
    run.success = True
    run.items_total = len(movies) + len(series_list)
    run.items_matched_radarr = matched_radarr
    run.items_matched_sonarr = matched_sonarr
    await db.commit()

    log.info(
        "Sync OK in %.1fs: %d movies, %d series (matched: %d radarr, %d sonarr)",
        duration, len(movies), len(series_list), matched_radarr, matched_sonarr,
    )

    return SyncResult(
        success=True,
        duration_seconds=duration,
        items_total=len(movies) + len(series_list),
        movies=len(movies),
        series=len(series_list),
        items_matched_radarr=matched_radarr,
        items_matched_sonarr=matched_sonarr,
    )
