"""APScheduler integration.

One job: daily full cycle (sync → mark → delete) at the configured hour.
The job is added/updated/removed based on the CleanupRule.schedule_enabled
+ schedule_hour fields. Reconfigure by calling reconfigure_schedule() after
mutating the rule.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db.session import AsyncSessionLocal
from app.services.cleanup import run_full_cycle
from app.services.scan import get_or_create_rule

log = logging.getLogger("jellyclean.scheduler")

JOB_ID = "jellyclean-daily-cycle"

_scheduler: AsyncIOScheduler | None = None


async def _full_cycle_job() -> None:
    log.info("Scheduled full cycle starting")
    async with AsyncSessionLocal() as db:
        try:
            result = await run_full_cycle(db)
            log.info(
                "Scheduled full cycle done in %.1fs: success=%s",
                result.duration_seconds, result.success,
            )
        except Exception:
            log.exception("Scheduled full cycle crashed")


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


async def start_scheduler() -> None:
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        log.info("APScheduler started")
    await reconfigure_schedule()


def stop_scheduler() -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("APScheduler stopped")


async def reconfigure_schedule() -> None:
    """Read the current rule from DB and (re)install the daily job accordingly."""
    scheduler = get_scheduler()
    async with AsyncSessionLocal() as db:
        rule = await get_or_create_rule(db)

    existing = scheduler.get_job(JOB_ID)

    if not rule.schedule_enabled:
        if existing:
            scheduler.remove_job(JOB_ID)
            log.info("Schedule disabled — removed daily job")
        return

    trigger = CronTrigger(hour=rule.schedule_hour, minute=0)
    if existing:
        scheduler.reschedule_job(JOB_ID, trigger=trigger)
        log.info("Rescheduled daily job to %02dh00 UTC", rule.schedule_hour)
    else:
        scheduler.add_job(
            _full_cycle_job,
            trigger=trigger,
            id=JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        log.info("Installed daily job at %02dh00 UTC", rule.schedule_hour)
