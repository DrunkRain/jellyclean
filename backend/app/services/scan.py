"""Scan / preview service.

Given the current MediaItem cache and the active CleanupRule, returns the list of
items that *would* be marked for deletion. Pure read-only — no Jellyfin / *arr
calls, no DB writes outside loading the rule.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CleanupRule,
    MediaItem,
    MediaType,
    ProtectedItem,
    SeriesStatus,
)
from app.schemas import ScanCandidate, ScanPreview


async def get_or_create_rule(db: AsyncSession) -> CleanupRule:
    result = await db.execute(select(CleanupRule).where(CleanupRule.id == 1))
    rule = result.scalar_one_or_none()
    if rule is None:
        rule = CleanupRule(id=1)
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
    return rule


def _days_between(then: datetime | None, now: datetime) -> int | None:
    if then is None:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (now - then).days


def _evaluate(item: MediaItem, rule: CleanupRule, now: datetime) -> tuple[bool, list[str]]:
    """Returns (is_candidate, reasons). Reasons explain WHY it matches."""
    if item.media_type == MediaType.movie.value:
        age_threshold = rule.movie_age_days
        unwatched_threshold = rule.movie_unwatched_days
    else:
        age_threshold = rule.series_age_days
        unwatched_threshold = rule.series_unwatched_days

    age_days = _days_between(item.date_added, now)
    if age_days is None:
        return False, ["Date d'ajout inconnue"]
    if age_days < age_threshold:
        return False, []

    if item.last_played_at is None:
        return True, [
            f"Ajouté il y a {age_days} j (seuil {age_threshold})",
            "Jamais vu",
        ]

    unwatched_days = _days_between(item.last_played_at, now)
    if unwatched_days is None or unwatched_days < unwatched_threshold:
        return False, []

    return True, [
        f"Ajouté il y a {age_days} j (seuil {age_threshold})",
        f"Non vu depuis {unwatched_days} j (seuil {unwatched_threshold})",
    ]


def _deletable_status(item: MediaItem) -> tuple[bool, str | None]:
    """Can this item actually be deleted via Radarr/Sonarr API in Sprint 4?

    Two distinct causes when not deletable, with different fixes:
    (A) Jellyfin has no usable provider ID → user must Identify the item in Jellyfin.
    (B) IDs are present in Jellyfin but the corresponding *arr instance has no entry
        for this item → user must add it via 'Add Movie' / 'Add Series → Import existing'.
    """
    if item.media_type == MediaType.movie.value:
        if item.radarr_id is not None:
            return True, None
        if not item.tmdb_id and not item.imdb_id:
            return False, (
                "Aucun ID TMDB/IMDB côté Jellyfin. "
                "Fix : dans Jellyfin → l'item → ⋮ → Identifier → choisir le bon match."
            )
        ids = ", ".join(filter(None, [
            f"TMDB:{item.tmdb_id}" if item.tmdb_id else None,
            f"IMDB:{item.imdb_id}" if item.imdb_id else None,
        ]))
        return False, (
            f"Jellyfin a les IDs ({ids}) mais Radarr ne connaît pas ce film. "
            "Fix : dans Radarr → Add Movie → recherche par titre. Il appairera le fichier existant."
        )

    # series
    if item.sonarr_id is not None:
        return True, None
    if not item.tvdb_id and not item.imdb_id:
        return False, (
            "Aucun ID TVDB/IMDB côté Jellyfin. "
            "Fix : dans Jellyfin → la série → ⋮ → Identifier → choisir le bon match."
        )
    ids = ", ".join(filter(None, [
        f"TVDB:{item.tvdb_id}" if item.tvdb_id else None,
        f"IMDB:{item.imdb_id}" if item.imdb_id else None,
    ]))
    return False, (
        f"Jellyfin a les IDs ({ids}) mais Sonarr ne connaît pas cette série. "
        "Fix : dans Sonarr → Add Series → Import existing (sélectionne le dossier)."
    )


async def preview_scan(db: AsyncSession) -> ScanPreview:
    rule = await get_or_create_rule(db)
    now = datetime.now(timezone.utc)

    items_result = await db.execute(select(MediaItem))
    items = list(items_result.scalars().all())

    protected_result = await db.execute(select(ProtectedItem.jellyfin_id))
    protected_ids = {row for (row,) in protected_result.all()}

    candidates: list[ScanCandidate] = []
    skipped_protected = 0
    skipped_continuing = 0

    for item in items:
        if item.jellyfin_id in protected_ids:
            skipped_protected += 1
            continue
        if (
            item.media_type == MediaType.series.value
            and rule.protect_continuing_series
            and item.series_status == SeriesStatus.continuing.value
        ):
            skipped_continuing += 1
            continue

        is_candidate, reasons = _evaluate(item, rule, now)
        if not is_candidate:
            continue

        deletable, blocker = _deletable_status(item)
        candidates.append(
            ScanCandidate(
                jellyfin_id=item.jellyfin_id,
                media_type=item.media_type,
                name=item.name,
                file_size_bytes=item.file_size_bytes,
                date_added=item.date_added,
                last_played_at=item.last_played_at,
                last_played_by=item.last_played_by,
                radarr_id=item.radarr_id,
                sonarr_id=item.sonarr_id,
                tmdb_id=item.tmdb_id,
                tvdb_id=item.tvdb_id,
                library_name=item.library_name,
                series_status=item.series_status,
                reasons=reasons,
                deletable=deletable,
                deletable_blocker=blocker,
            )
        )

    candidates_total = sum(c.file_size_bytes or 0 for c in candidates)
    deletable_total = sum(c.file_size_bytes or 0 for c in candidates if c.deletable)

    return ScanPreview(
        rule_enabled=rule.enabled,
        total_items_evaluated=len(items),
        candidates=candidates,
        skipped_protected=skipped_protected,
        skipped_continuing_series=skipped_continuing,
        candidates_total_size_bytes=candidates_total,
        deletable_total_size_bytes=deletable_total,
    )
