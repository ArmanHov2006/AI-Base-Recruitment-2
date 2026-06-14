"""Celery task wrappers.

Each task is a sync function that calls ``asyncio.run`` on the underlying
async implementation. The worker is long-running, so loop creation cost
is negligible relative to LLM latency.
"""

import asyncio
import sys
import uuid

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import structlog
from celery.exceptions import MaxRetriesExceededError

from app.worker.celery_app import celery_app

log = structlog.get_logger()


async def _mark_application_failed(application_id: uuid.UUID, reason: str) -> None:
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.applications.models import JobApplication
    from app.database import async_session_factory

    async with async_session_factory() as db:
        result = await db.execute(select(JobApplication).where(JobApplication.id == application_id))
        app = result.scalar_one_or_none()
        if app and app.status == "parsing":
            app.status = "parse_failed"
            app.error_message = reason[:1000]
            app.updated_at = datetime.now(timezone.utc)
            await db.commit()


async def _embed_candidate_from_application(application_id: uuid.UUID) -> None:
    from sqlalchemy import select

    from app.applications.models import JobApplication
    from app.candidates.models import Candidate
    from app.database import async_session_factory
    from app.llm.factory import get_llm_client

    async with async_session_factory() as db:
        result = await db.execute(select(JobApplication).where(JobApplication.id == application_id))
        app = result.scalar_one_or_none()
        if not app or not app.candidate_id:
            return
        result = await db.execute(select(Candidate).where(Candidate.id == app.candidate_id))
        candidate = result.scalar_one_or_none()
        if not candidate or candidate.embedding is not None:
            return
        text = ((candidate.summary or "") + " " + " ".join(candidate.skills or [])).strip()
        if not text:
            return
        embedding = await get_llm_client().embed(text)
        candidate.embedding = embedding
        await db.commit()


@celery_app.task(
    name="apply_pipeline",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def apply_pipeline_task(self, application_id: str) -> None:
    from app.applications.service import run_apply_pipeline

    try:
        asyncio.run(run_apply_pipeline(uuid.UUID(application_id)))
        try:
            asyncio.run(_embed_candidate_from_application(uuid.UUID(application_id)))
        except Exception as exc:
            log.warning("embed_candidate.failed", application_id=application_id, exc=str(exc))
    except Exception as exc:
        log.warning("apply_pipeline.retry", application_id=application_id, error=str(exc))
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            log.error("apply_pipeline.exhausted", application_id=application_id, error=str(exc))
            try:
                asyncio.run(_mark_application_failed(uuid.UUID(application_id), f"Max retries exceeded: {exc}"))
            except Exception as mark_exc:
                log.error("apply_pipeline.mark_failed_error", application_id=application_id, exc=str(mark_exc))


@celery_app.task(
    name="score_candidate_for_job",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def score_candidate_for_job_task(self, candidate_id: str, job_id: str) -> None:
    from app.worker.scoring import score_candidate_for_job_async

    try:
        asyncio.run(score_candidate_for_job_async(uuid.UUID(candidate_id), uuid.UUID(job_id)))
    except Exception as exc:
        log.warning(
            "score_candidate_for_job.retry",
            candidate_id=candidate_id,
            job_id=job_id,
            error=str(exc),
        )
        raise self.retry(exc=exc)


@celery_app.task(
    name="send_notification_email",
    bind=False,
    max_retries=0,
)
def send_notification_email_task(to: str, subject: str, body: str) -> None:
    async def _do() -> None:
        import html as _html

        from app.users.email import _send

        await _send(to=to, subject=subject, html=f"<pre>{_html.escape(body)}</pre>")

    try:
        asyncio.run(_do())
    except Exception as exc:
        log.warning("send_notification_email.failed", to=to, exc=str(exc))
        raise


async def _generate_ai_suggested_rating(evaluation_id: uuid.UUID) -> None:

    from app.candidates.models import Candidate
    from app.comparisons.scoring import candidate_to_data
    from app.database import async_session_factory
    from app.evaluations.models import CandidateEvaluation
    from app.jobs.models import Job
    from app.llm.factory import get_llm_client

    async with async_session_factory() as db:
        evaluation = await db.get(CandidateEvaluation, evaluation_id)
        if not evaluation:
            return
        candidate = await db.get(Candidate, evaluation.candidate_id)
        job = await db.get(Job, evaluation.job_id)
        if not candidate or not job:
            return

        llm = get_llm_client()
        result = await llm.score_candidate(
            candidate=candidate_to_data(candidate),
            job_title=job.title,
            job_description=job.description,
            required_skills=job.required_skills,
            required_technical_skills=list(job.required_technical_skills or []),
            required_soft_skills=list(job.required_soft_skills or []),
            required_seniority=job.required_seniority,
        )
        # Map 0-100 → 1-5 (half-up rounding)
        bucket = int(result.overall_score / 20 + 0.5)
        evaluation.ai_suggested_rating = max(1, min(5, bucket))
        await db.commit()


@celery_app.task(
    name="generate_ai_suggested_rating",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def generate_ai_suggested_rating_task(self, evaluation_id: str) -> None:
    try:
        asyncio.run(_generate_ai_suggested_rating(uuid.UUID(evaluation_id)))
    except Exception as exc:
        log.warning("generate_ai_suggested_rating.failed", evaluation_id=evaluation_id, exc=str(exc))
        raise self.retry(exc=exc)


async def _send_interview_reminders() -> dict:
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import and_, select

    from app.applications.models import JobApplication
    from app.audit.actions import BusinessEventAction
    from app.audit.events import BusinessEvent, record
    from app.database import async_session_factory
    from app.jobs.models import Job

    now = datetime.now(timezone.utc)
    reminded_24h = 0
    reminded_1h = 0

    # Statuses that should NOT receive reminders
    _SKIP_STATUSES = ("rejected", "withdrawn", "parse_failed", "parsing")

    # Non-overlapping windows: 1h → (now, now+1h]; 24h → (now+1h, now+24h]
    for reminder_action, window_start, window_end in (
        (BusinessEventAction.INTERVIEW_REMINDER_1H, now, now + timedelta(hours=1)),
        (BusinessEventAction.INTERVIEW_REMINDER_24H, now + timedelta(hours=1), now + timedelta(hours=24)),
    ):
        async with async_session_factory() as db:
            result = await db.execute(
                select(JobApplication).where(
                    and_(
                        JobApplication.deleted_at.is_(None),
                        ~JobApplication.status.in_(_SKIP_STATUSES),
                        JobApplication.interview_scheduled_at > window_start,
                        JobApplication.interview_scheduled_at <= window_end,
                    )
                )
            )
            applications = result.scalars().all()

            for app in applications:
                scheduled_iso = app.interview_scheduled_at.isoformat()

                existing = await db.execute(
                    select(BusinessEvent.id)
                    .where(
                        and_(
                            BusinessEvent.resource_type == "application",
                            BusinessEvent.resource_id == app.id,
                            BusinessEvent.action == reminder_action.value,
                            BusinessEvent.meta["interview_scheduled_at"].astext == scheduled_iso,
                        )
                    )
                    .limit(1)
                )
                if existing.scalar_one_or_none() is not None:
                    continue

                # Record dedup marker before sending to prevent double-fire on retry
                await record(
                    db,
                    actor_id=None,
                    action=reminder_action,
                    resource_type="application",
                    resource_id=app.id,
                    meta={
                        "interview_scheduled_at": scheduled_iso,
                        "job_id": str(app.job_id),
                    },
                )
                await db.commit()

                try:
                    job_result = await db.execute(select(Job).where(Job.id == app.job_id))
                    job = job_result.scalar_one_or_none()
                    if job:
                        label = "24h" if reminder_action == BusinessEventAction.INTERVIEW_REMINDER_24H else "1h"
                        from app.watchers.service import fan_out

                        await fan_out(
                            db,
                            "interview_reminder",
                            {
                                "application_id": str(app.id),
                                "job_title": job.title,
                                "scheduled_at": scheduled_iso,
                                "reminder_type": label,
                            },
                            job_id=app.job_id,
                            creator_id=job.creator_id,
                        )
                except Exception as exc:
                    log.warning(
                        "interview_reminder.notify_failed",
                        application_id=str(app.id),
                        reminder=reminder_action.value,
                        exc=str(exc),
                    )

                if reminder_action == BusinessEventAction.INTERVIEW_REMINDER_24H:
                    reminded_24h += 1
                else:
                    reminded_1h += 1

    log.info(
        "interview_reminders.sent",
        reminded_24h=reminded_24h,
        reminded_1h=reminded_1h,
    )
    return {"reminded_24h": reminded_24h, "reminded_1h": reminded_1h}


@celery_app.task(name="interview.send_reminders")
def send_interview_reminders_task() -> dict:
    return asyncio.run(_send_interview_reminders())


# ---------------------------------------------------------------------------
# Elasticsearch outbox tasks (F4)
# ---------------------------------------------------------------------------


@celery_app.task(
    name="es.index_candidate",
    bind=True,
    max_retries=5,
    default_retry_delay=30,
)
def es_index_candidate_task(self, candidate_id: str) -> dict:
    """(Re)index a single candidate in Elasticsearch.

    Idempotent: calling multiple times with the same id is safe.
    Retried up to 5× with exponential back-off so ES downtime never drifts
    the index permanently.
    """

    async def _do() -> dict:
        from sqlalchemy import select

        from app.candidates.models import Candidate
        from app.database import async_session_factory
        from app.search.service import index_candidate

        async with async_session_factory() as db:
            result = await db.execute(select(Candidate).where(Candidate.id == uuid.UUID(candidate_id)))
            candidate = result.scalar_one_or_none()
            if candidate is None:
                log.warning("es_index_candidate.not_found", candidate_id=candidate_id)
                return {"ok": False, "reason": "not_found"}
            ok = await index_candidate(candidate)
            return {"ok": ok, "candidate_id": candidate_id}

    try:
        return asyncio.run(_do())
    except Exception as exc:
        log.warning("es_index_candidate.retry", candidate_id=candidate_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="es.remove_candidate",
    bind=True,
    max_retries=5,
    default_retry_delay=30,
)
def es_remove_candidate_task(self, candidate_id: str) -> dict:
    """Mark a candidate as deleted in Elasticsearch (soft-delete)."""

    async def _do() -> dict:
        from app.search.service import remove_candidate

        ok = await remove_candidate(uuid.UUID(candidate_id))
        return {"ok": ok, "candidate_id": candidate_id}

    try:
        return asyncio.run(_do())
    except Exception as exc:
        log.warning("es_remove_candidate.retry", candidate_id=candidate_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="es.backfill_candidates",
    bind=False,
    max_retries=0,
)
def es_backfill_candidates_task() -> dict:
    """Index all existing candidates from Postgres into Elasticsearch.

    Run once after initial deployment or whenever the ES index is wiped.
    """

    async def _do() -> dict:
        from app.database import async_session_factory
        from app.search.service import backfill_all_candidates

        async with async_session_factory() as db:
            count = await backfill_all_candidates(db)
        return {"indexed": count}

    result = asyncio.run(_do())
    log.info("es.backfill_candidates_task_done", **result)
    return result


# ---------------------------------------------------------------------------
# SLA alert task (#7)
# ---------------------------------------------------------------------------


async def _send_sla_alerts() -> dict:
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import and_, select

    from app.applications.models import JobApplication
    from app.audit.actions import BusinessEventAction
    from app.audit.events import BusinessEvent, record
    from app.candidates.models import Candidate
    from app.database import async_session_factory
    from app.jobs.models import Job
    from app.watchers.service import fan_out

    alerted = 0
    _STALE_STATUSES = ("applied", "screening", "interview")

    async with async_session_factory() as db:
        now = datetime.now(timezone.utc)

        jobs_result = await db.execute(select(Job).where(Job.sla_days.isnot(None), Job.deleted_at.is_(None)))
        jobs = {j.id: j for j in jobs_result.scalars().all()}

        if not jobs:
            return {"alerted": 0}

        apps_result = await db.execute(
            select(JobApplication).where(
                and_(
                    JobApplication.deleted_at.is_(None),
                    JobApplication.job_id.in_(jobs.keys()),
                    JobApplication.status.in_(_STALE_STATUSES),
                )
            )
        )
        applications = apps_result.scalars().all()

        for app in applications:
            job = jobs[app.job_id]
            threshold = now - timedelta(days=job.sla_days or 0)
            updated = app.updated_at or app.applied_at
            if updated is None or updated > threshold:
                continue

            # Dedup: skip if already alerted in last 24h
            dedup_result = await db.execute(
                select(BusinessEvent.id)
                .where(
                    and_(
                        BusinessEvent.resource_type == "application",
                        BusinessEvent.resource_id == app.id,
                        BusinessEvent.action == BusinessEventAction.SLA_ALERT.value,
                        BusinessEvent.created_at > now - timedelta(hours=24),
                    )
                )
                .limit(1)
            )
            if dedup_result.scalar_one_or_none() is not None:
                continue

            days_stale = int((now - updated).total_seconds() / 86400)

            cand_result = await db.execute(select(Candidate).where(Candidate.id == app.candidate_id))
            candidate = cand_result.scalar_one_or_none()

            await record(
                db,
                actor_id=None,
                action=BusinessEventAction.SLA_ALERT,
                resource_type="application",
                resource_id=app.id,
                meta={"job_id": str(app.job_id), "days_stale": days_stale},
            )
            await db.commit()

            try:
                await fan_out(
                    db,
                    "sla_alert",
                    {
                        "job_title": job.title,
                        "candidate_name": candidate.name if candidate else None,
                        "candidate_id": str(app.candidate_id) if app.candidate_id else None,
                        "job_id": str(app.job_id),
                        "application_id": str(app.id),
                        "status": app.status,
                        "days_stale": days_stale,
                        "sla_days": job.sla_days,
                    },
                    job_id=app.job_id,
                    creator_id=job.creator_id,
                )
                alerted += 1
                try:
                    from app.notifications.webhook import notify_sla_alert

                    await notify_sla_alert(
                        candidate_name=candidate.name if candidate else None,
                        job_title=job.title,
                        status=app.status,
                        days_stale=days_stale,
                        sla_days=job.sla_days or 0,
                        candidate_id=str(app.candidate_id) if app.candidate_id else None,
                    )
                except Exception as exc:
                    log.warning("sla_alert.slack_failed", application_id=str(app.id), exc=str(exc))
            except Exception as exc:
                log.warning("sla_alert.fan_out_failed", application_id=str(app.id), exc=str(exc))

    log.info("sla_alerts.sent", alerted=alerted)
    return {"alerted": alerted}


@celery_app.task(name="sla.send_alerts")
def send_sla_alerts_task() -> dict:
    return asyncio.run(_send_sla_alerts())


# ---------------------------------------------------------------------------
# Digest email task (#1)
# ---------------------------------------------------------------------------


async def _send_digests(preference: str) -> dict:
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import and_, select

    from app.database import async_session_factory
    from app.notifications.models import Notification
    from app.users.models import User
    from app.watchers.service import render_email

    window = timedelta(hours=24) if preference == "daily" else timedelta(days=7)
    sent = 0

    async with async_session_factory() as db:
        now = datetime.now(timezone.utc)

        users_result = await db.execute(
            select(User).where(
                User.digest_preference == preference,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        users = users_result.scalars().all()

        for user in users:
            notifs_result = await db.execute(
                select(Notification)
                .where(
                    and_(
                        Notification.user_id == user.id,
                        Notification.emailed_at.is_(None),
                        Notification.created_at > now - window,
                    )
                )
                .order_by(Notification.created_at.asc())
            )
            notifs = notifs_result.scalars().all()
            if not notifs:
                continue

            lines = []
            for n in notifs:
                _, body = render_email(n.type, n.payload)
                lines.append(f"• [{n.type}] {body.split(chr(10))[0]}")

            subject = f"Recruitment digest ({len(notifs)} update{'s' if len(notifs) != 1 else ''})"
            full_body = "\n".join(lines)
            try:
                send_notification_email_task.delay(user.email, subject, full_body)
                for n in notifs:
                    n.emailed_at = now
                await db.commit()
                sent += 1
            except Exception as exc:
                await db.rollback()
                log.warning("digest.send_failed", user_id=str(user.id), exc=str(exc))

    log.info("digest.sent", preference=preference, users_notified=sent)
    return {"preference": preference, "users_notified": sent}


@celery_app.task(name="digest.send_daily")
def send_daily_digest_task() -> dict:
    return asyncio.run(_send_digests("daily"))


@celery_app.task(name="digest.send_weekly")
def send_weekly_digest_task() -> dict:
    return asyncio.run(_send_digests("weekly"))


# ---------------------------------------------------------------------------
# Slack daily pipeline summary
# ---------------------------------------------------------------------------


async def _slack_daily_summary() -> dict:
    from datetime import datetime, timezone

    from sqlalchemy import and_, func, select

    from app.applications.models import JobApplication
    from app.audit.actions import BusinessEventAction
    from app.audit.events import BusinessEvent
    from app.comparisons.models import CandidateJobScore
    from app.database import async_session_factory
    from app.notifications.webhook import notify_slack_daily_summary

    _OPEN_STATUSES = ("applied", "screening", "interview", "offer")
    _HIGH_SCORE = 75

    async with async_session_factory() as db:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        new_today_result = await db.execute(
            select(func.count(JobApplication.id)).where(
                JobApplication.deleted_at.is_(None),
                JobApplication.applied_at >= today_start,
            )
        )
        new_today = new_today_result.scalar() or 0

        breakdown_result = await db.execute(
            select(JobApplication.status, func.count(JobApplication.id))
            .where(
                JobApplication.deleted_at.is_(None),
                JobApplication.status.in_(_OPEN_STATUSES),
            )
            .group_by(JobApplication.status)
        )
        status_breakdown: dict[str, int] = {row[0]: row[1] for row in breakdown_result.all()}
        open_total = sum(status_breakdown.values())

        sla_result = await db.execute(
            select(func.count(BusinessEvent.id)).where(
                and_(
                    BusinessEvent.action == BusinessEventAction.SLA_ALERT.value,
                    BusinessEvent.created_at >= today_start,
                )
            )
        )
        sla_breaches = sla_result.scalar() or 0

        high_score_result = await db.execute(
            select(func.count(CandidateJobScore.id)).where(
                CandidateJobScore.overall_score >= _HIGH_SCORE,
                CandidateJobScore.scored_at >= today_start,
            )
        )
        high_score_today = high_score_result.scalar() or 0

    await notify_slack_daily_summary(
        new_today=new_today,
        open_total=open_total,
        sla_breaches=sla_breaches,
        high_score_today=high_score_today,
        status_breakdown=status_breakdown,
    )
    log.info("slack_daily_summary.sent", new_today=new_today, open_total=open_total)
    return {"new_today": new_today, "open_total": open_total}


@celery_app.task(name="slack.daily_summary")
def slack_daily_summary_task() -> dict:
    return asyncio.run(_slack_daily_summary())


# ---------------------------------------------------------------------------
# Interview transcription + scoring (Lane B)
# ---------------------------------------------------------------------------


@celery_app.task(
    name="interview.transcribe_and_score",
    bind=True,
    # Transient errors (S3Error, subprocess.TimeoutExpired, OSError) are retried.
    # Permanent errors (LLMParseError, FileValidationError, ValueError) are NOT
    # retried — the pipeline marks session.status="failed" and re-raises; the
    # except block below skips self.retry so those propagate immediately.
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def transcribe_and_score_task(self, session_id: str) -> None:
    """Sync Celery wrapper: download → STT → LLM score → upsert CandidateEvaluation."""
    from app.llm.base import LLMParseError as _LLMParseError
    from app.storage.validator import FileValidationError as _FileValidationError

    _PERMANENT = (_LLMParseError, _FileValidationError, ValueError)

    try:
        import uuid as _uuid

        from app.worker.interview import transcribe_and_score

        asyncio.run(transcribe_and_score(_uuid.UUID(session_id)))
    except _PERMANENT as exc:
        # Permanent failure — do NOT retry; let Celery mark the task as failed.
        log.error(
            "interview.transcribe_and_score.permanent_failure",
            session_id=session_id,
            error=str(exc),
        )
        raise
    except Exception as exc:
        log.warning(
            "interview.transcribe_and_score.transient_retry",
            session_id=session_id,
            error=str(exc),
        )
        raise
