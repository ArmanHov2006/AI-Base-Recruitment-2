import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.applications.models import JobApplication
from app.applications.schemas import (
    ApplicationResponse,
    BulkCreateApplicationsRequest,
    BulkCreateApplicationsResponse,
    CreateApplicationRequest,
    SetInterviewRequest,
    UpdateApplicationStatusRequest,
)
from app.audit.actions import BusinessEventAction
from app.audit.events import record
from app.audit.snapshots import snapshot_application
from app.auth import get_current_user, require_write
from app.candidates.models import Candidate
from app.comparisons.models import CandidateJobScore
from app.comparisons.utils import to_ten_scale
from app.database import get_db
from app.jobs.models import Job
from app.parser.service import validate_file_id
from app.users.models import User, UserRole
from app.worker.tasks import apply_pipeline_task

router = APIRouter(prefix="/jobs/{job_id}/applications", tags=["applications"])
logger = logging.getLogger(__name__)

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _load_job(db: AsyncSession, job_id: uuid.UUID) -> Job:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


async def _load_application(
    db: AsyncSession, job_id: uuid.UUID, application_id: uuid.UUID
) -> JobApplication:
    result = await db.execute(
        select(JobApplication).where(
            JobApplication.id == application_id,
            JobApplication.job_id == job_id,
            JobApplication.deleted_at.is_(None),
        )
    )
    application = result.scalar_one_or_none()
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return application


async def _load_candidate(db: AsyncSession, candidate_id: uuid.UUID | None) -> Candidate | None:
    if candidate_id is None:
        return None
    row = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    return row.scalar_one_or_none()


def _to_response(
    application: JobApplication,
    candidate: Candidate | None,
    *,
    score: CandidateJobScore | None = None,
    user: User | None = None,
) -> ApplicationResponse:
    can_view_score = score is not None and (user is None or user.role != UserRole.VIEWER)
    return ApplicationResponse(
        id=application.id,
        job_id=application.job_id,
        candidate_id=application.candidate_id,
        status=application.status,  # type: ignore[arg-type]
        resume_file_id=application.resume_file_id,
        error_message=application.error_message,
        source=application.source,
        applied_at=application.applied_at,
        updated_at=application.updated_at,
        overall_score_10=to_ten_scale(score.overall_score) if can_view_score else None,
        scored_at=score.scored_at if can_view_score else None,
        interview_scheduled_at=application.interview_scheduled_at,
        interview_location=application.interview_location,
        candidate=candidate,  # type: ignore[arg-type]
    )


@router.post(
    "",
    response_model=ApplicationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_application(
    request: Request,
    job_id: uuid.UUID,
    body: CreateApplicationRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
    allow_duplicate: bool = Query(False, description="Bypass duplicate resume detection"),
) -> ApplicationResponse:
    job = await _load_job(db, job_id)
    validate_file_id(body.file_id)

    application = JobApplication(
        job_id=job_id,
        candidate_id=None,
        resume_file_id=body.file_id,
        status="parsing",
        allow_duplicate=allow_duplicate,
        source=body.source,
    )
    db.add(application)
    await db.flush()
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.APPLICATION_SUBMITTED,
        resource_type="application",
        resource_id=application.id,
        request_id=getattr(request.state, "request_id", None),
        after=snapshot_application(application),
        meta={"job_id": str(job_id)},
    )
    await db.commit()
    await db.refresh(application)

    apply_pipeline_task.delay(str(application.id))

    try:
        from app.watchers.service import ensure_job_watcher, fan_out
        await ensure_job_watcher(db, job_id, current_user.id)
        await fan_out(
            db,
            "new_application",
            {"job_title": job.title, "application_id": str(application.id)},
            job_id=job_id,
            creator_id=job.creator_id,
        )
    except Exception:
        logger.exception(
            "Notification dispatch failed",
            extra={"job_id": str(job_id), "application_id": str(application.id)},
        )

    return _to_response(application, candidate=None)


@router.post(
    "/bulk",
    response_model=BulkCreateApplicationsResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def bulk_create_applications(
    request: Request,
    job_id: uuid.UUID,
    body: BulkCreateApplicationsRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
    allow_duplicate: bool = Query(False, description="Bypass duplicate resume detection"),
) -> BulkCreateApplicationsResponse:
    await _load_job(db, job_id)
    for file_id in body.file_ids:
        validate_file_id(file_id)

    applications: list[JobApplication] = []
    for file_id in body.file_ids:
        app = JobApplication(
            job_id=job_id,
            candidate_id=None,
            resume_file_id=file_id,
            status="parsing",
            allow_duplicate=allow_duplicate,
            source=body.source,
        )
        db.add(app)
        applications.append(app)

    await db.flush()

    for app in applications:
        await record(
            db,
            actor_id=current_user.id,
            action=BusinessEventAction.APPLICATION_SUBMITTED,
            resource_type="application",
            resource_id=app.id,
            request_id=getattr(request.state, "request_id", None),
            after=snapshot_application(app),
            meta={"job_id": str(job_id), "bulk": True},
        )

    try:
        from app.watchers.service import ensure_job_watcher
        await ensure_job_watcher(db, job_id, current_user.id)
    except Exception:
        logger.warning("bulk_create.auto_assign_failed", extra={"job_id": str(job_id)})

    await db.commit()
    for app in applications:
        apply_pipeline_task.delay(str(app.id))
    return BulkCreateApplicationsResponse(application_ids=[str(app.id) for app in applications])


@router.get(
    "",
    response_model=list[ApplicationResponse],
    status_code=status.HTTP_200_OK,
)
async def list_applications(
    job_id: uuid.UUID,
    db: DbDep,
    user: Annotated[User, Depends(get_current_user)],
) -> list[ApplicationResponse]:
    await _load_job(db, job_id)

    CandidateAlias = aliased(Candidate)
    result = await db.execute(
        select(JobApplication, CandidateAlias, CandidateJobScore)
        .outerjoin(
            CandidateAlias,
            (CandidateAlias.id == JobApplication.candidate_id)
            & (CandidateAlias.deleted_at.is_(None)),
        )
        .outerjoin(
            CandidateJobScore,
            (CandidateJobScore.job_id == JobApplication.job_id)
            & (CandidateJobScore.candidate_id == JobApplication.candidate_id),
        )
        .where(
            JobApplication.job_id == job_id,
            JobApplication.deleted_at.is_(None),
        )
        .order_by(JobApplication.applied_at.desc())
    )

    return [
        _to_response(app, cand, score=score, user=user)
        for app, cand, score in result.all()
    ]


@router.get(
    "/{application_id}",
    response_model=ApplicationResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
async def get_application(
    job_id: uuid.UUID,
    application_id: uuid.UUID,
    db: DbDep,
) -> ApplicationResponse:
    application = await _load_application(db, job_id, application_id)
    candidate = await _load_candidate(db, application.candidate_id)
    return _to_response(application, candidate)


@router.patch(
    "/{application_id}",
    response_model=ApplicationResponse,
    status_code=status.HTTP_200_OK,
)
async def update_application_status(
    request: Request,
    job_id: uuid.UUID,
    application_id: uuid.UUID,
    body: UpdateApplicationStatusRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> ApplicationResponse:
    application = await _load_application(db, job_id, application_id)
    if application.status in ("parsing", "parse_failed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot change status while application is {application.status}",
        )
    _before = snapshot_application(application)
    application.status = body.status
    application.updated_at = datetime.now(timezone.utc)
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.APPLICATION_STATUS_CHANGED,
        resource_type="application",
        resource_id=application_id,
        request_id=getattr(request.state, "request_id", None),
        before=_before,
        after=snapshot_application(application),
        meta={
            "job_id": str(job_id),
            "candidate_id": str(application.candidate_id) if application.candidate_id else None,
        },
    )
    await db.commit()
    await db.refresh(application)

    candidate = await _load_candidate(db, application.candidate_id)

    try:
        _job_result = await db.execute(select(Job).where(Job.id == job_id))
        _job = _job_result.scalar_one_or_none()
        from app.notifications.webhook import notify_stage_change
        await notify_stage_change(
            candidate_name=candidate.name if candidate else None,
            job_title=_job.title if _job else None,
            new_status=body.status,
            candidate_id=str(application.candidate_id) if application.candidate_id else None,
        )
    except Exception:
        logger.exception("Webhook dispatch failed", extra={"application_id": str(application_id)})

    try:
        _j = await db.get(Job, job_id)
        from app.watchers.service import fan_out
        await fan_out(
            db,
            "stage_change",
            {
                "job_title": _j.title if _j else None,
                "candidate_name": candidate.name if candidate else None,
                "candidate_id": str(application.candidate_id) if application.candidate_id else None,
                "job_id": str(job_id),
                "new_stage": body.status,
                "application_id": str(application_id),
            },
            job_id=job_id,
            candidate_id=application.candidate_id,
            creator_id=_j.creator_id if _j else None,
        )
    except Exception:
        logger.exception("fan_out failed", extra={"application_id": str(application_id)})

    return _to_response(application, candidate)


@router.patch(
    "/{application_id}/interview",
    response_model=ApplicationResponse,
    status_code=status.HTTP_200_OK,
)
async def set_interview(
    request: Request,
    job_id: uuid.UUID,
    application_id: uuid.UUID,
    body: SetInterviewRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> ApplicationResponse:
    application = await _load_application(db, job_id, application_id)

    old_scheduled_at = application.interview_scheduled_at
    new_scheduled_at = body.scheduled_at

    # No-op: nothing would change
    if old_scheduled_at == new_scheduled_at and application.interview_location == body.location:
        candidate = await _load_candidate(db, application.candidate_id)
        return _to_response(application, candidate)

    _before = snapshot_application(application)

    if new_scheduled_at is None:
        action = BusinessEventAction.INTERVIEW_CLEARED
    elif old_scheduled_at is None:
        action = BusinessEventAction.INTERVIEW_SCHEDULED
    else:
        action = BusinessEventAction.INTERVIEW_RESCHEDULED

    application.interview_scheduled_at = new_scheduled_at
    application.interview_location = body.location
    application.updated_at = datetime.now(timezone.utc)

    await record(
        db,
        actor_id=current_user.id,
        action=action,
        resource_type="application",
        resource_id=application_id,
        request_id=getattr(request.state, "request_id", None),
        before=_before,
        after=snapshot_application(application),
        meta={"job_id": str(job_id)},
    )
    await db.commit()
    await db.refresh(application)

    if new_scheduled_at is not None:
        try:
            job = await _load_job(db, job_id)
            from app.watchers.service import fan_out
            await fan_out(
                db,
                "interview_scheduled",
                {
                    "job_title": job.title,
                    "application_id": str(application_id),
                    "scheduled_at": new_scheduled_at.isoformat(),
                    "location": body.location,
                    "candidate_name": None,
                },
                job_id=job_id,
                candidate_id=application.candidate_id,
                creator_id=job.creator_id,
            )
        except Exception:
            logger.exception(
                "Interview notification failed",
                extra={"application_id": str(application_id)},
            )

    candidate = await _load_candidate(db, application.candidate_id)
    return _to_response(application, candidate)


@router.delete(
    "/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_application(
    request: Request,
    job_id: uuid.UUID,
    application_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> None:
    application = await _load_application(db, job_id, application_id)
    _before = snapshot_application(application)
    application.deleted_at = datetime.now(timezone.utc)
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.APPLICATION_DELETED,
        resource_type="application",
        resource_id=application_id,
        request_id=getattr(request.state, "request_id", None),
        before=_before,
        meta={"job_id": str(job_id)},
    )
    await db.commit()
