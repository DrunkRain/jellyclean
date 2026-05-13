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
from app.db.models import (
    ActionLog,
    PendingItem,
    ServiceConfig,
    ServiceName,
)
from app.schemas import MarkPassResult, ScanCandidate
from app.services.scan import get_or_create_rule, preview_scan

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
            tmdb_id=None,  # not in ScanCandidate yet, would be a nice add
            tvdb_id=None,
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
