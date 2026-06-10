"""Background worker for the apply-to-job pipeline.

Triggered from `POST /jobs/{job_id}/applications` after the row has been
inserted with `status="parsing"`. Extracts candidate data via the LLM,
upserts the candidate, attaches the candidate to the application, and flips
status to `applied`. On failure, sets `parse_failed` with `error_message` and
keeps the source file in MinIO so the user can retry.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.applications.models import JobApplication
from app.candidates.models import Candidate
from app.database import async_session_factory
from app.parser.schemas import CandidateData
from app.parser.service import parse_and_validate

_DUPLICATE_ERROR_PREFIX = "duplicate:"

logger = logging.getLogger(__name__)


async def run_apply_pipeline(application_id: uuid.UUID) -> None:
    async with async_session_factory() as db:
        row = await db.execute(
            select(JobApplication).where(JobApplication.id == application_id)
        )
        application = row.scalar_one_or_none()
        if application is None:
            logger.warning("apply pipeline: application %s not found", application_id)
            return

        try:
            parsed = await parse_and_validate(
                application.resume_file_id, db, job_id=application.job_id
            )
        except HTTPException as exc:
            await _mark_failed(db, application, f"{exc.status_code}: {exc.detail}")
            return
        except Exception as exc:
            logger.exception("apply pipeline: unexpected error for %s", application_id)
            await _mark_failed(db, application, str(exc))
            return

        if not application.allow_duplicate:
            similar = await _check_duplicate(db, parsed)
            if similar is not None:
                await _mark_failed(db, application, f"duplicate:{similar.id}")
                return

        try:
            candidate = await _upsert_candidate(db, application.resume_file_id, parsed)
        except Exception as exc:
            logger.exception("apply pipeline: candidate upsert failed for %s", application_id)
            await _mark_failed(db, application, f"candidate upsert failed: {exc}")
            return

        existing = await db.execute(
            select(JobApplication).where(
                JobApplication.job_id == application.job_id,
                JobApplication.candidate_id == candidate.id,
                JobApplication.id != application.id,
                JobApplication.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none() is not None:
            await _mark_failed(
                db, application, "Candidate already has an application for this job"
            )
            return

        application.candidate_id = candidate.id
        application.status = "applied"
        application.error_message = None
        application.updated_at = datetime.now(timezone.utc)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            await _mark_failed(db, application, "Candidate already has an application for this job")
            return

        # Proactive scoring: pre-populate the leaderboard for this job.
        # Local import keeps Celery out of the import graph when worker isn't loaded.
        from app.worker.tasks import score_candidate_for_job_task

        score_candidate_for_job_task.delay(str(candidate.id), str(application.job_id))


async def _check_duplicate(db, data: CandidateData) -> Candidate | None:
    # Email-based dedup is already handled in _upsert_candidate.
    # Embedding dedup catches "same person, different email" — but same-role batches
    # (e.g. 42 Senior ML engineers) share skill embeddings and produce false positives.
    # Require both high embedding similarity AND matching name before flagging.
    embed_text = ((data.summary or "") + " " + " ".join(data.skills or [])).strip()
    if not embed_text:
        return None
    try:
        from app.candidates.router import find_similar_candidate
        from app.llm import get_llm_client

        vec = await get_llm_client().embed(embed_text)
        match = await find_similar_candidate(db, vec)
        if match is None:
            return None
        # Name must match AND phone must match — two people can share a name,
        # but not both name and phone. This prevents false positives in same-role batches
        # where generated/real data reuses common names.
        if data.name and match.name:
            if data.name.strip().lower() != match.name.strip().lower():
                return None
        if data.phone and match.phone:
            if data.phone.strip() != match.phone.strip():
                return None
        return match
    except Exception:
        logger.warning("duplicate check failed — skipping", exc_info=True)
        return None


async def _upsert_candidate(db, file_id: str, data: CandidateData) -> Candidate:
    from datetime import datetime, timezone

    from app.resumes.models import CandidateResume

    if data.email:
        row = await db.execute(
            select(Candidate).where(
                Candidate.email == data.email,
                Candidate.deleted_at.is_(None),
            )
        )
        existing = row.scalar_one_or_none()
        if existing is not None:
            # Add a new resume version for the existing candidate
            next_version = (existing.current_resume_version or 1) + 1
            resume_row = CandidateResume(
                candidate_id=existing.id,
                file_id=file_id,
                version=next_version,
                parsed_at=datetime.now(timezone.utc),
            )
            db.add(resume_row)
            existing.file_id = file_id
            existing.current_resume_version = next_version
            await db.flush()
            return existing

    candidate = Candidate(
        file_id=file_id,
        name=data.name,
        email=data.email,
        phone=data.phone,
        skills=data.skills,
        years_experience=data.years_experience,
        education=[e.model_dump() for e in data.education],
        work_experiences=[e.model_dump() for e in data.work_experiences],
        location=data.location,
        seniority=data.seniority,
        summary=data.summary,
        desired_position=data.desired_position,
        certifications=data.certifications,
        languages=data.languages,
        linkedin_url=data.linkedin_url,
        github_url=data.github_url,
        current_resume_version=1,
        resume_language=data.resume_language,
    )
    db.add(candidate)
    await db.flush()

    # Record version 1
    resume_row = CandidateResume(
        candidate_id=candidate.id,
        file_id=file_id,
        version=1,
        parsed_at=datetime.now(timezone.utc),
    )
    db.add(resume_row)
    await db.flush()

    return candidate


async def _mark_failed(db, application: JobApplication, message: str) -> None:
    application.status = "parse_failed"
    application.error_message = message[:1000]
    application.updated_at = datetime.now(timezone.utc)
    await db.commit()
