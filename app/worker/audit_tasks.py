"""Celery tasks for audit log maintenance."""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import structlog
from sqlalchemy import delete, select, text

from app.worker.celery_app import celery_app

log = structlog.get_logger()

_BATCH = 1000


async def _purge_old_audit_logs() -> dict:
    from app.audit.events import BusinessEvent
    from app.audit.models import AuditLog
    from app.config import settings
    from app.database import async_session_factory

    months = settings.audit_retention_months
    cutoff = text(f"NOW() - INTERVAL '{months} months'")

    audit_deleted = 0
    events_deleted = 0

    async with async_session_factory() as db:
        # audit_log — delete in batches ordered by created_at
        while True:
            ids = (
                await db.execute(
                    select(AuditLog.id)
                    .where(AuditLog.created_at < cutoff)
                    .limit(_BATCH)
                )
            ).scalars().all()
            if not ids:
                break
            result = await db.execute(delete(AuditLog).where(AuditLog.id.in_(ids)))
            audit_deleted += result.rowcount
            await db.commit()
            if len(ids) < _BATCH:
                break

        # business_events — delete in batches
        while True:
            ids = (
                await db.execute(
                    select(BusinessEvent.id)
                    .where(BusinessEvent.created_at < cutoff)
                    .limit(_BATCH)
                )
            ).scalars().all()
            if not ids:
                break
            result = await db.execute(delete(BusinessEvent).where(BusinessEvent.id.in_(ids)))
            events_deleted += result.rowcount
            await db.commit()
            if len(ids) < _BATCH:
                break

    log.info(
        "audit.purge_completed",
        audit_log_deleted=audit_deleted,
        business_events_deleted=events_deleted,
        retention_months=months,
    )
    return {"audit_log_deleted": audit_deleted, "business_events_deleted": events_deleted}


@celery_app.task(name="audit.purge_old_logs")
def purge_old_audit_logs() -> dict:
    """Delete audit_log and business_events rows older than audit_retention_months."""
    return asyncio.run(_purge_old_audit_logs())
