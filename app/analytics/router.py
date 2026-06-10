import asyncio
import uuid
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import (
    CandidateSourceItem,
    CandidateSourcesResponse,
    FunnelResponse,
    FunnelStage,
    JobTimeToHire,
    OverviewResponse,
    RecruiterActivityItem,
    RecruiterActivityResponse,
    SkillCount,
    TimeToHireResponse,
)
from app.applications.models import JobApplication
from app.audit.actions import BusinessEventAction
from app.audit.events import BusinessEvent, record
from app.auth import get_current_user, require_admin, require_write
from app.candidates.models import Candidate
from app.database import get_db
from app.evaluations.models import CandidateEvaluation
from app.jobs.models import Job
from app.users.models import User

router = APIRouter(prefix="/analytics", tags=["analytics"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

_FUNNEL_ORDER = ["applied", "reviewing", "shortlisted", "interview", "offer", "hired"]

# Application statuses that count a candidate as "active" (in-flight, not yet
# hired or rejected). Mirrors the frontend Analytics active set.
_ACTIVE_APP_STATUSES = [
    "applied",
    "reviewing",
    "screening",
    "shortlisted",
    "interview",
    "offer",
]


@router.get("/overview", response_model=OverviewResponse, dependencies=[Depends(require_write)])
async def get_overview(db: DbDep) -> OverviewResponse:
    total_candidates: int = (
        await db.execute(select(func.count()).select_from(Candidate).where(Candidate.deleted_at.is_(None)))
    ).scalar_one()

    total_jobs: int = (
        await db.execute(select(func.count()).select_from(Job).where(Job.deleted_at.is_(None)))
    ).scalar_one()

    total_applications: int = (
        await db.execute(
            select(func.count()).select_from(JobApplication).where(JobApplication.deleted_at.is_(None))
        )
    ).scalar_one()

    # Distinct candidates with at least one in-flight application. Counts people,
    # not applications, so it can never exceed total_candidates even when one
    # candidate applies to multiple roles.
    active_candidates: int = (
        await db.execute(
            select(func.count(func.distinct(JobApplication.candidate_id)))
            .select_from(JobApplication)
            .join(Candidate, Candidate.id == JobApplication.candidate_id)
            .where(
                JobApplication.deleted_at.is_(None),
                JobApplication.status.in_(_ACTIVE_APP_STATUSES),
                Candidate.deleted_at.is_(None),
            )
        )
    ).scalar_one()

    status_rows = (
        await db.execute(
            select(JobApplication.status, func.count().label("cnt"))
            .where(JobApplication.deleted_at.is_(None))
            .group_by(JobApplication.status)
        )
    ).all()
    applications_by_status = {row.status: row.cnt for row in status_rows}

    skill_rows = (
        await db.execute(
            text(
                "SELECT jsonb_array_elements_text(skills) AS skill, COUNT(*) AS cnt"
                " FROM candidates WHERE deleted_at IS NULL"
                " GROUP BY skill ORDER BY cnt DESC LIMIT 10"
            )
        )
    ).all()
    top_skills = [SkillCount(skill=row.skill, count=row.cnt) for row in skill_rows]

    return OverviewResponse(
        total_candidates=total_candidates,
        active_candidates=active_candidates,
        total_jobs=total_jobs,
        total_applications=total_applications,
        applications_by_status=applications_by_status,
        top_skills=top_skills,
    )


@router.get("/funnel", response_model=FunnelResponse, dependencies=[Depends(require_write)])
async def get_funnel(
    db: DbDep,
    job_id: uuid.UUID | None = Query(default=None),
) -> FunnelResponse:
    q = (
        select(JobApplication.status, func.count().label("cnt"))
        .where(JobApplication.deleted_at.is_(None))
        .group_by(JobApplication.status)
    )
    if job_id is not None:
        q = q.where(JobApplication.job_id == job_id)

    rows = (await db.execute(q)).all()
    counts: dict[str, int] = {row.status: row.cnt for row in rows}

    stages: list[FunnelStage] = []
    prev_count: int | None = None
    for stage in _FUNNEL_ORDER:
        count = counts.get(stage, 0)
        if prev_count is None or prev_count == 0:
            conversion_rate = None
        else:
            conversion_rate = round(count / prev_count * 100, 1)
        stages.append(FunnelStage(stage=stage, count=count, conversion_rate=conversion_rate))
        if count > 0:
            prev_count = count

    for stage, count in counts.items():
        if stage not in _FUNNEL_ORDER:
            stages.append(FunnelStage(stage=stage, count=count, conversion_rate=None))

    return FunnelResponse(stages=stages)


@router.get(
    "/recruiter-activity",
    response_model=RecruiterActivityResponse,
    dependencies=[Depends(require_admin)],
)
async def get_recruiter_activity(db: DbDep) -> RecruiterActivityResponse:
    rows = (
        await db.execute(
            select(
                CandidateEvaluation.evaluator_id,
                func.count().label("eval_count"),
                func.avg(CandidateEvaluation.overall_rating).label("avg_rating"),
                func.max(CandidateEvaluation.created_at).label("last_active"),
            )
            .where(CandidateEvaluation.deleted_at.is_(None))
            .group_by(CandidateEvaluation.evaluator_id)
        )
    ).all()

    evaluator_ids = [row.evaluator_id for row in rows]
    users_by_id: dict[uuid.UUID, str | None] = {}
    if evaluator_ids:
        user_rows = (
            await db.execute(select(User.id, User.full_name).where(User.id.in_(evaluator_ids)))
        ).all()
        users_by_id = {row.id: row.full_name for row in user_rows}

    recruiters = [
        RecruiterActivityItem(
            evaluator_id=row.evaluator_id,
            evaluator_name=users_by_id.get(row.evaluator_id),
            evaluation_count=row.eval_count,
            avg_rating=float(row.avg_rating) if row.avg_rating is not None else None,
            last_active=row.last_active,
        )
        for row in rows
    ]

    return RecruiterActivityResponse(recruiters=recruiters)


@router.get(
    "/time-to-hire",
    response_model=TimeToHireResponse,
    dependencies=[Depends(get_current_user)],
)
async def get_time_to_hire(
    db: DbDep,
    job_id: uuid.UUID | None = Query(default=None),
) -> TimeToHireResponse:
    # Authoritative hire timestamp = earliest business event that flipped the
    # application's status to "hired" (audit log is immutable; the application's
    # own updated_at mutates on later edits, so it can't be trusted here).
    hire_q = (
        select(
            JobApplication.job_id.label("job_id"),
            JobApplication.applied_at.label("applied_at"),
            func.min(BusinessEvent.created_at).label("hired_at"),
        )
        .join(
            BusinessEvent,
            and_(
                BusinessEvent.resource_type == "application",
                BusinessEvent.resource_id == JobApplication.id,
                BusinessEvent.action == BusinessEventAction.APPLICATION_STATUS_CHANGED.value,
                BusinessEvent.after["status"].astext == "hired",
            ),
        )
        .where(JobApplication.deleted_at.is_(None))
        .group_by(JobApplication.id, JobApplication.job_id, JobApplication.applied_at)
    )
    if job_id is not None:
        hire_q = hire_q.where(JobApplication.job_id == job_id)

    rows = (await db.execute(hire_q)).all()

    per_job_days: dict[uuid.UUID, list[float]] = defaultdict(list)
    all_days: list[float] = []
    for row in rows:
        days = (row.hired_at - row.applied_at).total_seconds() / 86400.0
        if days < 0:  # guard against clock skew / backdated imports
            days = 0.0
        per_job_days[row.job_id].append(days)
        all_days.append(days)

    titles: dict[uuid.UUID, str | None] = {}
    if per_job_days:
        title_rows = (
            await db.execute(select(Job.id, Job.title).where(Job.id.in_(list(per_job_days.keys()))))
        ).all()
        titles = {t.id: t.title for t in title_rows}

    per_job = [
        JobTimeToHire(
            job_id=jid,
            job_title=titles.get(jid),
            hired_count=len(days_list),
            avg_days_to_hire=round(sum(days_list) / len(days_list), 1) if days_list else None,
        )
        for jid, days_list in per_job_days.items()
    ]
    per_job.sort(key=lambda x: x.job_title or "")

    overall = round(sum(all_days) / len(all_days), 1) if all_days else None
    return TimeToHireResponse(
        overall_avg_days=overall,
        total_hired=len(all_days),
        per_job=per_job,
    )


@router.get("/sources", response_model=CandidateSourcesResponse)
async def get_candidate_sources(
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> CandidateSourcesResponse:
    rows = (
        await db.execute(
            select(
                func.coalesce(JobApplication.source, "unknown").label("source"),
                func.count().label("cnt"),
            )
            .where(JobApplication.deleted_at.is_(None))
            .group_by(JobApplication.source)
            .order_by(func.count().desc())
        )
    ).all()

    data = [CandidateSourceItem(source=row.source, count=row.cnt) for row in rows]

    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.ANALYTICS_SOURCES_VIEWED,
        resource_type="analytics",
        resource_id=uuid.UUID(int=0),
        meta={"source_count": len(data)},
    )

    return CandidateSourcesResponse(data=data)


@router.get("/export.pdf", dependencies=[Depends(require_write)])
async def export_analytics_pdf(db: DbDep) -> Response:
    from app.export.pdf import build_analytics_pdf

    overview = await get_overview(db)
    # Pass job_id explicitly: calling the route handler directly would otherwise
    # leave job_id as its FastAPI Query(default=None) sentinel, which then leaks
    # into the SQL bind and raises a DataError.
    time_to_hire = await get_time_to_hire(db, job_id=None)

    pdf_bytes = await asyncio.to_thread(build_analytics_pdf, overview, None, time_to_hire)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=analytics.pdf"},
    )
