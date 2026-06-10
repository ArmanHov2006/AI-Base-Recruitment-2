"""Async worker entrypoint for proactive candidate-job scoring.

Loads the Candidate + Job, delegates to ``score_with_cache`` (which is
idempotent via ``score_input_hash``), and commits. Safe to retry.
"""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.candidates.models import Candidate
from app.comparisons.scoring import score_with_cache
from app.config import settings
from app.jobs.models import Job

log = structlog.get_logger()


async def score_candidate_for_job_async(
    candidate_id: uuid.UUID, job_id: uuid.UUID
) -> None:
    # Create engine here so asyncpg pool is bound to the current event loop.
    # The module-level engine in database.py is bound to a different loop when
    # called from asyncio.run() inside a Celery worker process.
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            cand_row = await db.execute(
                select(Candidate).where(
                    Candidate.id == candidate_id,
                    Candidate.deleted_at.is_(None),
                )
            )
            candidate = cand_row.scalar_one_or_none()
            if candidate is None:
                log.warning("score.candidate_missing", candidate_id=str(candidate_id))
                return

            job_row = await db.execute(
                select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
            )
            job = job_row.scalar_one_or_none()
            if job is None:
                log.warning("score.job_missing", job_id=str(job_id))
                return

            _, overall_score, *_ = await score_with_cache(candidate, job, db)
            await db.commit()

            threshold = (job.threshold_score * 10) if job.threshold_score else 75
            if overall_score >= threshold:
                from app.notifications.webhook import notify_high_score
                await notify_high_score(candidate.name, job.title, overall_score, candidate_id=str(candidate.id))
    finally:
        await engine.dispose()
