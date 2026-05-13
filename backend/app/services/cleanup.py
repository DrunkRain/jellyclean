"""Cleanup orchestrator — Sprint 4A scope: marking only, no actual deletion.

Pipeline:
  1. Run scan_preview (already-cached library + active rule)
  2. Compute diff:
       - to_mark: candidates not yet in pending_item
       - to_unmark: pending_items that are no longer candidates
                   (user watched it, restored it, protected it, rule changed, etc.)
  3. Sync the Jellyfin "Bientôt supprimé" Collection accordingly
  4. Persist pending_item table changes
  5. Append everything to ActionLog
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.jellyfin import JellyfinClient
from app.clients.jellyseerr import JellyseerrClient
from app.clients.radarr import RadarrClient
from app.clients.sonarr import SonarrClient
from app.db.models import (
    ActionLog,
    MediaItem,
    MediaType,
    PendingItem,
    ServiceConfig,
    ServiceName,
)
from app.schemas import (
    DeletePassResult,
    FullCycleResult,
    MarkPassResult,
    ScanCandidate,
)
from app.services.scan import get_or_create_rule, preview_scan
from app.services.sync import run_sync

log = logging.getLogger("jellyclean.cleanup")

COLLECTION_NAME = "Bientôt supprimé"


@dataclass
class _DiffResult:
    to_mark: list[ScanCandidate]
    to_unmark: list[str]  # jellyfin_ids
    to_keep: list[str]


async def _load_pending(db: AsyncSession) -> dict[str, PendingItem]:
    result = await db.execute(select(PendingItem))
    return {p.jellyfin_id: p for p in result.scalars().all()}


async def _log(
    db: AsyncSession,
    *,
    action: str,
    jellyfin_id: str,
    name: str,
    details: str = "",
    success: bool = True,
    error: str = "",
) -> None:
    db.add(
        ActionLog(
            action=action,
            jellyfin_id=jellyfin_id,
            name=name,
            details=details,
            success=success,
            error_message=error,
        )
    )


def _diff(
    candidates: list[ScanCandidate], current_pending: dict[str, PendingItem]
) -> _DiffResult:
    candidate_ids = {c.jellyfin_id for c in candidates}
    pending_ids = set(current_pending.keys())

    to_mark_ids = candidate_ids - pending_ids
    to_unmark_ids = pending_ids - candidate_ids
    to_keep_ids = candidate_ids & pending_ids

    return _DiffResult(
        to_mark=[c for c in candidates if c.jellyfin_id in to_mark_ids],
        to_unmark=list(to_unmark_ids),
        to_keep=list(to_keep_ids),
    )


async def _ensure_collection(
    jf: JellyfinClient, seed_item_ids: list[str], db: AsyncSession
) -> str | None:
    """Find or create the 'Bientôt supprimé' Collection. Returns its id, or None
    if creation isn't possible yet (no items to seed)."""
    existing = await jf.find_collection_by_name(COLLECTION_NAME)
    if existing:
        return existing["Id"]
    if not seed_item_ids:
        # Nothing to add and no existing collection — nothing to do.
        return None
    log.info("Creating Jellyfin Collection '%s' with %d seed items", COLLECTION_NAME, len(seed_item_ids))
    created = await jf.create_collection(COLLECTION_NAME, seed_item_ids)
    coll_id = created.get("Id")
    if coll_id:
        await _log(
            db,
            action="collection-created",
            jellyfin_id=coll_id,
            name=COLLECTION_NAME,
            details=f"Seeded with {len(seed_item_ids)} items",
        )
    return coll_id


async def run_mark_pass(db: AsyncSession) -> MarkPassResult:
    started = time.monotonic()

    # 1. Scan against current cache + rule
    rule = await get_or_create_rule(db)
    preview = await preview_scan(db)

    if not rule.enabled:
        log.info("Rule disabled — mark pass aborted (no changes)")
        return MarkPassResult(
            success=True,
            duration_seconds=round(time.monotonic() - started, 2),
            rule_enabled=False,
            candidates_total=len(preview.candidates),
            newly_marked=0,
            unmarked_no_longer_matching=0,
            items_in_collection_after=0,
            collection_id=None,
            error_message="La règle est désactivée — aucun marquage n'est appliqué.",
        )

    # 2. Diff
    pending_map = await _load_pending(db)
    diff = _diff(preview.candidates, pending_map)

    # 3. Resolve / create Jellyfin Collection
    configs_result = await db.execute(select(ServiceConfig).where(ServiceConfig.service == ServiceName.jellyfin.value))
    jf_cfg = configs_result.scalar_one_or_none()
    if not (jf_cfg and jf_cfg.enabled and jf_cfg.base_url and jf_cfg.api_key):
        msg = "Jellyfin n'est pas configuré ou activé."
        log.warning(msg)
        return MarkPassResult(
            success=False,
            duration_seconds=round(time.monotonic() - started, 2),
            rule_enabled=True,
            candidates_total=len(preview.candidates),
            newly_marked=0,
            unmarked_no_longer_matching=0,
            items_in_collection_after=0,
            collection_id=None,
            error_message=msg,
        )

    jf = JellyfinClient(jf_cfg.base_url, jf_cfg.api_key)

    # Seed ids = all candidates we still want in the collection (existing + new)
    desired_ids = [c.jellyfin_id for c in preview.candidates]

    try:
        collection_id = await _ensure_collection(jf, desired_ids, db)
    except Exception as exc:
        msg = f"Création de la Collection échouée : {exc.__class__.__name__}: {exc}"
        log.exception("Collection ensure failed")
        return MarkPassResult(
            success=False,
            duration_seconds=round(time.monotonic() - started, 2),
            rule_enabled=True,
            candidates_total=len(preview.candidates),
            newly_marked=0,
            unmarked_no_longer_matching=0,
            items_in_collection_after=0,
            collection_id=None,
            error_message=msg,
        )

    items_in_collection_after = 0
    if collection_id:
        # Sync collection contents to match `desired_ids` exactly
        try:
            existing_in_coll = await jf.list_collection_items(collection_id)
            existing_ids = {it["Id"] for it in existing_in_coll}
            desired_set = set(desired_ids)

            to_add_to_coll = list(desired_set - existing_ids)
            to_remove_from_coll = list(existing_ids - desired_set)

            if to_add_to_coll:
                await jf.add_to_collection(collection_id, to_add_to_coll)
                for jid in to_add_to_coll:
                    name = next((c.name for c in preview.candidates if c.jellyfin_id == jid), jid)
                    await _log(db, action="collection-add", jellyfin_id=jid, name=name)
            if to_remove_from_coll:
                await jf.remove_from_collection(collection_id, to_remove_from_coll)
                for jid in to_remove_from_coll:
                    name = pending_map.get(jid).name if jid in pending_map else jid
                    await _log(db, action="collection-remove", jellyfin_id=jid, name=name)

            items_in_collection_after = len(desired_set)
        except Exception as exc:
            log.exception("Collection sync failed")
            return MarkPassResult(
                success=False,
                duration_seconds=round(time.monotonic() - started, 2),
                rule_enabled=True,
                candidates_total=len(preview.candidates),
                newly_marked=0,
                unmarked_no_longer_matching=0,
                items_in_collection_after=0,
                collection_id=collection_id,
                error_message=f"Sync de la Collection échouée : {exc}",
            )

    # 4. Persist pending_item changes
    now = datetime.now(timezone.utc)
    grace = timedelta(days=rule.grace_period_days)

    newly_marked = 0
    for cand in diff.to_mark:
        item = PendingItem(
            jellyfin_id=cand.jellyfin_id,
            media_type=cand.media_type,
            name=cand.name,
            file_size_bytes=cand.file_size_bytes,
            radarr_id=cand.radarr_id,
            sonarr_id=cand.sonarr_id,
            tmdb_id=cand.tmdb_id,
            tvdb_id=cand.tvdb_id,
            library_name=cand.library_name,
            marked_at=now,
            scheduled_delete_at=now + grace,
            reasons=json.dumps(cand.reasons, ensure_ascii=False),
        )
        db.add(item)
        await _log(
            db,
            action="marked-pending",
            jellyfin_id=cand.jellyfin_id,
            name=cand.name,
            details=" / ".join(cand.reasons),
        )
        newly_marked += 1

    unmarked = 0
    for jid in diff.to_unmark:
        existing = pending_map.get(jid)
        if existing is None:
            continue
        await db.delete(existing)
        await _log(
            db,
            action="unmarked-pending",
            jellyfin_id=jid,
            name=existing.name,
            details="L'item ne matche plus la règle (vu, protégé, ou seuil changé)",
        )
        unmarked += 1

    await db.commit()

    duration = time.monotonic() - started
    log.info(
        "Mark pass OK in %.2fs: +%d marked, -%d unmarked, %d in collection now",
        duration, newly_marked, unmarked, items_in_collection_after,
    )

    return MarkPassResult(
        success=True,
        duration_seconds=round(duration, 2),
        rule_enabled=True,
        candidates_total=len(preview.candidates),
        newly_marked=newly_marked,
        unmarked_no_longer_matching=unmarked,
        items_in_collection_after=items_in_collection_after,
        collection_id=collection_id,
    )


async def _remove_from_jellyfin_collection(
    db: AsyncSession, jellyfin_ids: list[str]
) -> None:
    """Best-effort removal from the 'Bientôt supprimé' Collection. Non-fatal on failure."""
    if not jellyfin_ids:
        return
    configs_result = await db.execute(
        select(ServiceConfig).where(ServiceConfig.service == ServiceName.jellyfin.value)
    )
    jf_cfg = configs_result.scalar_one_or_none()
    if not (jf_cfg and jf_cfg.enabled and jf_cfg.base_url and jf_cfg.api_key):
        return
    jf = JellyfinClient(jf_cfg.base_url, jf_cfg.api_key)
    try:
        coll = await jf.find_collection_by_name(COLLECTION_NAME)
        if coll:
            await jf.remove_from_collection(coll["Id"], jellyfin_ids)
    except Exception as exc:
        log.warning("Could not remove ids from Jellyfin Collection: %s", exc)


async def _delete_one(
    db: AsyncSession,
    pending: PendingItem,
    radarr: RadarrClient | None,
    sonarr: SonarrClient | None,
    jellyseerr: JellyseerrClient | None,
    dry_run: bool,
) -> tuple[bool, str | None]:
    """Delete one item via the appropriate *arr + clean its Jellyseerr request.
    Returns (success, error_message). In dry_run, logs 'would-delete' and returns success
    without touching anything external."""
    is_movie = pending.media_type == MediaType.movie.value

    if dry_run:
        await _log(
            db,
            action="would-delete",
            jellyfin_id=pending.jellyfin_id,
            name=pending.name,
            details=(
                f"DRY-RUN — supprimerait via "
                f"{'Radarr' if is_movie else 'Sonarr'} (id={pending.radarr_id or pending.sonarr_id})"
                + (f", req Jellyseerr pour {'TMDB' if is_movie else 'TVDB'}={pending.tmdb_id or pending.tvdb_id}" if jellyseerr else "")
            ),
        )
        return True, None

    # Real deletion path
    target_id = pending.radarr_id if is_movie else pending.sonarr_id
    if target_id is None:
        msg = f"Pas d'id {'Radarr' if is_movie else 'Sonarr'} — impossible de supprimer."
        await _log(
            db,
            action="delete-failed",
            jellyfin_id=pending.jellyfin_id,
            name=pending.name,
            success=False,
            error=msg,
        )
        return False, msg

    try:
        if is_movie:
            assert radarr is not None
            await radarr.delete_movie(target_id, delete_files=True, add_import_exclusion=False)
        else:
            assert sonarr is not None
            await sonarr.delete_series(target_id, delete_files=True, add_import_exclusion=False)
    except Exception as exc:
        msg = f"{exc.__class__.__name__}: {exc}"
        log.exception("DELETE on *arr failed for %s", pending.name)
        await _log(
            db,
            action="delete-failed",
            jellyfin_id=pending.jellyfin_id,
            name=pending.name,
            success=False,
            error=msg,
        )
        return False, msg

    await _log(
        db,
        action="deleted",
        jellyfin_id=pending.jellyfin_id,
        name=pending.name,
        details=f"{'Radarr' if is_movie else 'Sonarr'} id={target_id}, files supprimés",
    )

    # ===== Jellyseerr cleanup =====
    # Best-effort: never fail the deletion just because Jellyseerr was unhappy.
    if jellyseerr is None:
        await _log(
            db,
            action="jellyseerr-skipped",
            jellyfin_id=pending.jellyfin_id,
            name=pending.name,
            details="Jellyseerr non configuré ou désactivé — cleanup ignoré.",
        )
        return True, None

    # Backfill provider IDs from the MediaItem cache if the pending row predates
    # Sprint 4B (it would have tmdb_id=None / tvdb_id=None).
    tmdb = pending.tmdb_id
    if not tmdb:
        media = await db.get(MediaItem, pending.jellyfin_id)
        if media and media.tmdb_id:
            tmdb = media.tmdb_id
            log.info("Backfilled tmdb_id=%s for %s from MediaItem cache", tmdb, pending.name)

    # Jellyseerr keys both movies and series by TMDB internally; we only need that.
    if not tmdb:
        await _log(
            db,
            action="jellyseerr-skipped",
            jellyfin_id=pending.jellyfin_id,
            name=pending.name,
            details=(
                "Pas d'ID TMDB pour cet item — Jellyseerr utilise TMDB comme clé primaire. "
                "Vérifie l'identification dans Jellyfin (⋮ → Identifier)."
            ),
        )
        return True, None

    # Direct lookup: GET /movie/{tmdbId} or /tv/{tmdbId} → mediaInfo block
    try:
        media_info = await jellyseerr.find_media_info(
            "movie" if is_movie else "tv", tmdb_id=tmdb,
        )
    except Exception as exc:
        log.warning("Jellyseerr media lookup failed for %s: %s", pending.name, exc)
        await _log(
            db,
            action="jellyseerr-cleanup-failed",
            jellyfin_id=pending.jellyfin_id,
            name=pending.name,
            success=False,
            error=f"Lookup TMDB={tmdb}: {exc.__class__.__name__}: {exc}",
        )
        return True, None

    if media_info is None:
        await _log(
            db,
            action="jellyseerr-skipped",
            jellyfin_id=pending.jellyfin_id,
            name=pending.name,
            details=(
                f"Jellyseerr ne connaît pas TMDB={tmdb} — pas de cleanup nécessaire "
                "(probablement jamais ajouté via Jellyseerr)."
            ),
        )
        return True, None

    media_id = media_info.get("id")
    if not media_id:
        await _log(
            db,
            action="jellyseerr-cleanup-failed",
            jellyfin_id=pending.jellyfin_id,
            name=pending.name,
            success=False,
            error=f"mediaInfo retourné sans id pour TMDB={tmdb} (Jellyseerr API inattendue).",
        )
        return True, None

    try:
        await jellyseerr.delete_media(media_id)
        await _log(
            db,
            action="jellyseerr-media-deleted",
            jellyfin_id=pending.jellyfin_id,
            name=pending.name,
            details=f"media id {media_id} (TMDB={tmdb}) — requests supprimés en cascade",
        )
    except Exception as exc:
        log.warning(
            "Jellyseerr delete_media failed for %s (media_id=%s): %s",
            pending.name, media_id, exc,
        )
        await _log(
            db,
            action="jellyseerr-cleanup-failed",
            jellyfin_id=pending.jellyfin_id,
            name=pending.name,
            success=False,
            error=f"Delete media id={media_id}: {exc.__class__.__name__}: {exc}",
        )

    return True, None


async def run_delete_pass(
    db: AsyncSession, *, force_jellyfin_ids: list[str] | None = None
) -> DeletePassResult:
    """Execute pending deletions whose grace period has elapsed.

    If force_jellyfin_ids is provided, only those are processed (used by the
    'Delete now' button). They still respect the dry_run flag.
    """
    started = time.monotonic()
    rule = await get_or_create_rule(db)
    now = datetime.now(timezone.utc)

    if force_jellyfin_ids:
        result = await db.execute(
            select(PendingItem).where(PendingItem.jellyfin_id.in_(force_jellyfin_ids))
        )
        candidates = list(result.scalars().all())
    else:
        result = await db.execute(
            select(PendingItem).where(PendingItem.scheduled_delete_at <= now)
        )
        candidates = list(result.scalars().all())

    if not candidates:
        return DeletePassResult(
            success=True,
            duration_seconds=round(time.monotonic() - started, 2),
            dry_run=rule.dry_run,
            candidates_for_deletion=0,
            deleted_count=0,
            failed_count=0,
        )

    # Load *arr clients (only what we need)
    configs_result = await db.execute(select(ServiceConfig))
    configs = {c.service: c for c in configs_result.scalars().all()}

    def _client_or_none(svc: ServiceName, cls):
        cfg = configs.get(svc.value)
        if cfg and cfg.enabled and cfg.base_url and cfg.api_key:
            return cls(cfg.base_url, cfg.api_key)
        return None

    radarr = _client_or_none(ServiceName.radarr, RadarrClient)
    sonarr = _client_or_none(ServiceName.sonarr, SonarrClient)
    jellyseerr = _client_or_none(ServiceName.jellyseerr, JellyseerrClient)

    deleted = 0
    failed = 0
    errors: list[str] = []
    successfully_processed_ids: list[str] = []

    for pending in candidates:
        ok, err = await _delete_one(
            db, pending, radarr, sonarr, jellyseerr, dry_run=rule.dry_run
        )
        if ok:
            deleted += 1
            successfully_processed_ids.append(pending.jellyfin_id)
            # In dry-run we keep the pending row so the user can see and re-test;
            # in LIVE we remove it (it's gone).
            if not rule.dry_run:
                await db.delete(pending)
        else:
            failed += 1
            if err:
                errors.append(f"{pending.name}: {err}")

    # Remove successfully-deleted items from the Jellyfin Collection (LIVE only)
    if not rule.dry_run and successfully_processed_ids:
        await _remove_from_jellyfin_collection(db, successfully_processed_ids)

    await db.commit()

    duration = time.monotonic() - started
    log.info(
        "Delete pass OK in %.2fs: %d %s, %d failed (dry_run=%s)",
        duration, deleted, "would-delete" if rule.dry_run else "deleted", failed, rule.dry_run,
    )

    return DeletePassResult(
        success=failed == 0,
        duration_seconds=round(duration, 2),
        dry_run=rule.dry_run,
        candidates_for_deletion=len(candidates),
        deleted_count=deleted,
        failed_count=failed,
        errors=errors[:10],  # cap for response size
    )


async def run_full_cycle(db: AsyncSession) -> FullCycleResult:
    """Sync → mark → delete. Used by the scheduler and by the manual button."""
    started = time.monotonic()
    log.info("Full cycle starting")

    # 1. Sync
    sync_result = await run_sync(db)
    if not sync_result.success:
        return FullCycleResult(
            success=False,
            duration_seconds=round(time.monotonic() - started, 2),
            sync=None,  # SyncResult dataclass doesn't match SyncSummary fields one-for-one
            error_message=f"Sync échouée : {sync_result.error_message}",
        )

    from app.schemas import SyncSummary  # local import to avoid cycle at module load

    sync_summary = SyncSummary(
        success=sync_result.success,
        duration_seconds=round(sync_result.duration_seconds, 2),
        items_total=sync_result.items_total,
        movies=sync_result.movies,
        series=sync_result.series,
        items_matched_radarr=sync_result.items_matched_radarr,
        items_matched_sonarr=sync_result.items_matched_sonarr,
        error_message=sync_result.error_message,
    )

    # 2. Mark pass
    mark_result = await run_mark_pass(db)

    # 3. Delete pass — only if mark didn't blow up
    delete_result = await run_delete_pass(db)

    return FullCycleResult(
        success=mark_result.success and delete_result.success,
        duration_seconds=round(time.monotonic() - started, 2),
        sync=sync_summary,
        mark_pass=mark_result,
        delete_pass=delete_result,
    )


async def restore_pending(db: AsyncSession, jellyfin_id: str) -> bool:
    """Remove an item from pending + Jellyfin Collection. Returns True if found."""
    pending = await db.get(PendingItem, jellyfin_id)
    if pending is None:
        return False

    # Remove from Jellyfin Collection if possible
    configs_result = await db.execute(select(ServiceConfig).where(ServiceConfig.service == ServiceName.jellyfin.value))
    jf_cfg = configs_result.scalar_one_or_none()
    if jf_cfg and jf_cfg.enabled and jf_cfg.base_url and jf_cfg.api_key:
        jf = JellyfinClient(jf_cfg.base_url, jf_cfg.api_key)
        try:
            coll = await jf.find_collection_by_name(COLLECTION_NAME)
            if coll:
                await jf.remove_from_collection(coll["Id"], [jellyfin_id])
        except Exception as exc:
            log.warning("Could not remove %s from Jellyfin Collection: %s", jellyfin_id, exc)

    name = pending.name
    await db.delete(pending)
    await _log(
        db,
        action="restored",
        jellyfin_id=jellyfin_id,
        name=name,
        details="Restauré manuellement par l'utilisateur",
    )
    await db.commit()
    return True
