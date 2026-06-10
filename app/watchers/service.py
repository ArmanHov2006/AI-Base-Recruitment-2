"""Watcher fan-out — single entry-point for all notification dispatch.

fan_out() collects recipients from job_watchers + candidate_watchers (deduped),
respects per-watcher type filters, checks digest_preference before sending
email, and marks emailed_at so the digest task skips already-sent items.
"""
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import Notification
from app.watchers.models import CandidateWatcher, JobWatcher

log = structlog.get_logger()

_DIGEST_PREFS = frozenset({"daily", "weekly"})


def _add_notification(
    db: AsyncSession, user_id: uuid.UUID, type_: str, payload: dict
) -> Notification:
    notif = Notification(user_id=user_id, type=type_, payload=payload)
    db.add(notif)
    return notif


def render_email(type_: str, payload: dict) -> tuple[str, str]:
    job_title = payload.get("job_title") or ""
    candidate_name = payload.get("candidate_name") or "Unknown"

    if type_ == "new_application":
        return (
            f"New application: {job_title}",
            f"A new resume was submitted for {job_title}.\n\nLog in to review.",
        )
    if type_ == "stage_change":
        return (
            f"Stage change: {candidate_name} — {job_title}",
            (
                f"Candidate {candidate_name} moved to '{payload.get('new_stage', '')}'"
                f" for {job_title}.\n\nLog in to view."
            ),
        )
    if type_ == "interview_scheduled":
        return (
            f"Interview scheduled: {job_title}",
            (
                f"Interview scheduled for {job_title}.\n"
                f"Time: {payload.get('scheduled_at', 'TBD')}\n"
                f"Location: {payload.get('location') or 'TBD'}"
            ),
        )
    if type_ == "interview_reminder":
        label = payload.get("reminder_type", "")
        return (
            f"Interview reminder ({label}): {job_title}",
            (
                f"Reminder: interview in ~{label} for {job_title}.\n"
                f"Time: {payload.get('scheduled_at', 'TBD')}"
            ),
        )
    if type_ == "rating_update":
        return (
            f"New evaluation: {candidate_name} — {job_title}",
            (
                f"New evaluation for {candidate_name} on {job_title}.\n"
                f"Rating: {payload.get('overall_rating', '—')}/5"
            ),
        )
    if type_ == "sla_alert":
        days = payload.get("days_stale", "?")
        return (
            f"SLA alert: {candidate_name} stale {days}d — {job_title}",
            (
                f"Candidate {candidate_name} has been in '{payload.get('status', '')}'"
                f" for {days} days (SLA: {payload.get('sla_days', '?')} days).\n"
                f"Job: {job_title}\n\nAction required."
            ),
        )
    return ("Recruitment update", f"New update: {type_}")


async def fan_out(
    db: AsyncSession,
    type_: str,
    payload: dict,
    *,
    job_id: uuid.UUID | None = None,
    candidate_id: uuid.UUID | None = None,
    creator_id: uuid.UUID | None = None,
) -> None:
    from app.users.models import User

    recipient_ids: set[uuid.UUID] = set()

    if job_id is not None:
        if creator_id is not None:
            recipient_ids.add(creator_id)
        rows = await db.execute(select(JobWatcher).where(JobWatcher.job_id == job_id))
        for w in rows.scalars().all():
            if w.filters.get(type_, True):
                recipient_ids.add(w.user_id)

    if candidate_id is not None:
        cw_rows = await db.execute(
            select(CandidateWatcher.user_id).where(
                CandidateWatcher.candidate_id == candidate_id
            )
        )
        for cw_uid in cw_rows.scalars().all():
            recipient_ids.add(cw_uid)

    if not recipient_ids:
        return

    user_rows = await db.execute(
        select(User).where(
            User.id.in_(recipient_ids),
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    users = {u.id: u for u in user_rows.scalars().all()}

    for uid in recipient_ids:
        user = users.get(uid)
        if user is None:
            continue
        try:
            notif = _add_notification(db, uid, type_, payload)
            if user.digest_preference not in _DIGEST_PREFS:
                subject, body = render_email(type_, payload)
                try:
                    from app.worker.tasks import send_notification_email_task
                    send_notification_email_task.delay(user.email, subject, body)
                    notif.emailed_at = datetime.now(timezone.utc)
                except Exception:
                    log.warning("fan_out.email_dispatch_failed", user_id=str(uid), type=type_)
            await db.commit()
        except Exception:
            await db.rollback()
            log.warning("fan_out.notify_failed", user_id=str(uid), type=type_)


async def ensure_job_watcher(
    db: AsyncSession,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    stmt = (
        pg_insert(JobWatcher)
        .values(id=uuid.uuid4(), job_id=job_id, user_id=user_id, filters={})
        .on_conflict_do_nothing(constraint="uq_job_watcher")
    )
    await db.execute(stmt)
