import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.applications.models import JobApplication
from app.applications.schemas import ApplicationResponse
from app.audit.actions import BusinessEventAction
from app.audit.events import record
from app.audit.snapshots import snapshot_application, snapshot_evaluation
from app.auth import get_current_user, require_write
from app.candidates.models import Candidate
from app.database import get_db
from app.evaluations.models import CandidateEvaluation
from app.evaluations.schemas import (
    CreateEvaluationRequest,
    EvaluationResponse,
    StageTransitionRequest,
    UpdateEvaluationRequest,
)
from app.jobs.models import Job
from app.llm.base import LLMParseError, LLMTimeoutError
from app.users.models import User

router = APIRouter(tags=["evaluations"])
logger = logging.getLogger(__name__)

DbDep = Annotated[AsyncSession, Depends(get_db)]

_VALID_NEXT: dict[str, set[str]] = {
    "applied":      {"reviewing", "rejected"},
    "reviewing":    {"shortlisted", "rejected"},
    "shortlisted":  {"interview", "rejected"},
    "interview":    {"offer", "rejected"},
    "offer":        {"hired", "rejected"},
    "hired":        set(),
    "rejected":     set(),
    "withdrawn":    set(),
    "parsing":      set(),
    "parse_failed": set(),
    "screening":    {"interview", "shortlisted", "rejected"},
}


async def _load_candidate(db: AsyncSession, candidate_id: uuid.UUID) -> Candidate:
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id, Candidate.deleted_at.is_(None))
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return candidate


async def _load_evaluation(
    db: AsyncSession, candidate_id: uuid.UUID, eval_id: uuid.UUID
) -> CandidateEvaluation:
    result = await db.execute(
        select(CandidateEvaluation).where(
            CandidateEvaluation.id == eval_id,
            CandidateEvaluation.candidate_id == candidate_id,
            CandidateEvaluation.deleted_at.is_(None),
        )
    )
    evaluation = result.scalar_one_or_none()
    if evaluation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found")
    return evaluation


async def _load_job(db: AsyncSession, job_id: uuid.UUID) -> Job:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


async def _load_application(
    db: AsyncSession, job_id: uuid.UUID, app_id: uuid.UUID
) -> JobApplication:
    result = await db.execute(
        select(JobApplication).where(
            JobApplication.id == app_id,
            JobApplication.job_id == job_id,
            JobApplication.deleted_at.is_(None),
        )
    )
    application = result.scalar_one_or_none()
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return application


async def _fetch_evaluations_with_names(
    db: AsyncSession,
    candidate_id: uuid.UUID,
    job_id: uuid.UUID | None,
) -> list[EvaluationResponse]:
    EvaluatorUser = aliased(User)
    q = (
        select(CandidateEvaluation, EvaluatorUser.full_name)
        .join(EvaluatorUser, CandidateEvaluation.evaluator_id == EvaluatorUser.id, isouter=True)
        .where(
            CandidateEvaluation.candidate_id == candidate_id,
            CandidateEvaluation.deleted_at.is_(None),
        )
    )
    if job_id is not None:
        q = q.where(CandidateEvaluation.job_id == job_id)
    rows = (await db.execute(q)).all()
    responses = []
    for ev, evaluator_name in rows:
        resp = EvaluationResponse.model_validate(ev)
        resp.evaluator_name = evaluator_name
        responses.append(resp)
    return responses


@router.post(
    "/candidates/{candidate_id}/evaluations",
    response_model=EvaluationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_evaluation(
    request: Request,
    candidate_id: uuid.UUID,
    body: CreateEvaluationRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> EvaluationResponse:
    candidate = await _load_candidate(db, candidate_id)
    job = await _load_job(db, body.job_id)

    evaluation = CandidateEvaluation(
        candidate_id=candidate_id,
        job_id=body.job_id,
        evaluator_id=current_user.id,
        stage=body.stage,
        overall_rating=body.overall_rating,
        technical_score=body.technical_score,
        communication_score=body.communication_score,
        leadership_score=body.leadership_score,
        cultural_fit_score=body.cultural_fit_score,
        english_score=body.english_score,
        domain_score=body.domain_score,
        feedback=body.feedback,
        ai_suggested_rating=body.ai_suggested_rating,
    )
    db.add(evaluation)
    await db.flush()
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.EVALUATION_CREATED,
        resource_type="evaluation",
        resource_id=evaluation.id,
        request_id=getattr(request.state, "request_id", None),
        after=snapshot_evaluation(evaluation),
        meta={"candidate_id": str(candidate_id), "job_id": str(body.job_id)},
    )
    await db.commit()
    await db.refresh(evaluation)

    evaluator_result = await db.execute(select(User).where(User.id == evaluation.evaluator_id))
    evaluator = evaluator_result.scalar_one_or_none()
    resp = EvaluationResponse.model_validate(evaluation)
    resp.evaluator_name = evaluator.full_name if evaluator else None

    try:
        from app.watchers.service import fan_out
        await fan_out(
            db,
            "rating_update",
            {
                "job_title": job.title,
                "candidate_name": candidate.name,
                "candidate_id": str(candidate_id),
                "job_id": str(body.job_id),
                "overall_rating": body.overall_rating,
                "evaluation_id": str(evaluation.id),
            },
            job_id=body.job_id,
            candidate_id=candidate_id,
            creator_id=job.creator_id,
        )
    except Exception:
        logger.exception(
            "Notification dispatch failed for evaluation.created",
            extra={"evaluation_id": str(evaluation.id), "job_id": str(body.job_id)},
        )

    try:
        from app.worker.tasks import generate_ai_suggested_rating_task
        generate_ai_suggested_rating_task.delay(str(evaluation.id))
    except Exception:
        logger.exception(
            "AI rating task dispatch failed",
            extra={"evaluation_id": str(evaluation.id)},
        )

    return resp


@router.get(
    "/candidates/{candidate_id}/evaluations",
    response_model=list[EvaluationResponse],
)
async def list_evaluations(
    candidate_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(get_current_user)],
    job_id: uuid.UUID | None = Query(None),
) -> list[EvaluationResponse]:
    await _load_candidate(db, candidate_id)
    return await _fetch_evaluations_with_names(db, candidate_id, job_id)


@router.patch(
    "/candidates/{candidate_id}/evaluations/{eval_id}",
    response_model=EvaluationResponse,
)
async def update_evaluation(
    request: Request,
    candidate_id: uuid.UUID,
    eval_id: uuid.UUID,
    body: UpdateEvaluationRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> EvaluationResponse:
    evaluation = await _load_evaluation(db, candidate_id, eval_id)

    _before = snapshot_evaluation(evaluation)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(evaluation, field, value)
    evaluation.updated_at = datetime.now(timezone.utc)

    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.EVALUATION_UPDATED,
        resource_type="evaluation",
        resource_id=eval_id,
        request_id=getattr(request.state, "request_id", None),
        before=_before,
        after=snapshot_evaluation(evaluation),
        meta={"candidate_id": str(candidate_id)},
    )
    await db.commit()
    await db.refresh(evaluation)

    evaluator_result = await db.execute(select(User).where(User.id == evaluation.evaluator_id))
    evaluator = evaluator_result.scalar_one_or_none()
    resp = EvaluationResponse.model_validate(evaluation)
    resp.evaluator_name = evaluator.full_name if evaluator else None
    return resp


@router.delete(
    "/candidates/{candidate_id}/evaluations/{eval_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_evaluation(
    request: Request,
    candidate_id: uuid.UUID,
    eval_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> None:
    evaluation = await _load_evaluation(db, candidate_id, eval_id)
    _before = snapshot_evaluation(evaluation)
    evaluation.deleted_at = datetime.now(timezone.utc)
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.EVALUATION_DELETED,
        resource_type="evaluation",
        resource_id=eval_id,
        request_id=getattr(request.state, "request_id", None),
        before=_before,
        meta={"candidate_id": str(candidate_id)},
    )
    await db.commit()


@router.patch(
    "/jobs/{job_id}/applications/{app_id}/stage",
    response_model=ApplicationResponse,
)
async def transition_application_stage(
    request: Request,
    job_id: uuid.UUID,
    app_id: uuid.UUID,
    body: StageTransitionRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> ApplicationResponse:
    job = await _load_job(db, job_id)
    application = await _load_application(db, job_id, app_id)

    current = application.status
    requested = body.stage
    allowed = _VALID_NEXT.get(current, set())
    if requested not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition from '{current}' to '{requested}'",
        )

    _before = snapshot_application(application)
    application.status = requested
    application.updated_at = datetime.now(timezone.utc)
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.APPLICATION_STAGE_TRANSITIONED,
        resource_type="application",
        resource_id=app_id,
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

    candidate = None
    if application.candidate_id is not None:
        cand_result = await db.execute(
            select(Candidate).where(
                Candidate.id == application.candidate_id,
                Candidate.deleted_at.is_(None),
            )
        )
        candidate = cand_result.scalar_one_or_none()

    try:
        from app.watchers.service import fan_out
        await fan_out(
            db,
            "stage_change",
            {
                "job_title": job.title,
                "candidate_name": candidate.name if candidate else None,
                "candidate_id": str(application.candidate_id) if application.candidate_id else None,
                "job_id": str(job_id),
                "new_stage": body.stage,
                "application_id": str(app_id),
            },
            job_id=job_id,
            candidate_id=application.candidate_id,
            creator_id=job.creator_id,
        )
    except Exception:
        logger.exception(
            "Notification dispatch failed for stage transition",
            extra={"job_id": str(job_id), "application_id": str(app_id)},
        )

    if requested == "rejected" and candidate is not None and candidate.email:
        try:
            from app.notifications.email import notify_candidate_rejected
            await notify_candidate_rejected(
                job_title=job.title,
                candidate_name=candidate.name,
                candidate_email=candidate.email,
            )
        except Exception:
            logger.exception(
                "Rejection email failed for candidate",
                extra={"candidate_id": str(candidate.id), "job_id": str(job_id)},
            )

    return ApplicationResponse(
        id=application.id,
        job_id=application.job_id,
        candidate_id=application.candidate_id,
        status=application.status,
        resume_file_id=application.resume_file_id,
        error_message=application.error_message,
        applied_at=application.applied_at,
        updated_at=application.updated_at,
        candidate=candidate,  # type: ignore[arg-type]
    )


class InterviewQuestionsResponse(BaseModel):
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    questions: list[str]


@router.get("/candidates/{candidate_id}/interview-questions", response_model=InterviewQuestionsResponse)
async def get_interview_questions(
    candidate_id: uuid.UUID,
    db: DbDep,
    _: Annotated[User, Depends(require_write)],
    job_id: uuid.UUID = Query(...),
) -> InterviewQuestionsResponse:
    from app.comparisons.scoring import candidate_to_data
    from app.llm import get_llm_client

    candidate = await _load_candidate(db, candidate_id)
    job = await _load_job(db, job_id)

    llm = get_llm_client()
    try:
        questions = await llm.suggest_interview_questions(
            candidate=candidate_to_data(candidate),
            job_title=job.title,
            job_description=job.description,
            required_skills=job.required_skills,
        )
    except (LLMTimeoutError, LLMParseError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return InterviewQuestionsResponse(candidate_id=candidate_id, job_id=job_id, questions=questions)
