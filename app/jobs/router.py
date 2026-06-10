import asyncio
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.models import JobApplication
from app.audit.actions import BusinessEventAction
from app.audit.events import record
from app.audit.snapshots import snapshot_job
from app.auth import get_current_user, require_job_owner_or_elevated, require_role, require_write
from app.candidates.models import Candidate
from app.comparisons.constants import DEFAULT_THRESHOLD_SCORE
from app.comparisons.models import CandidateJobScore, Comparison, ComparisonResult
from app.comparisons.schemas import (
    LeaderboardEntry,
    RunTiebreakerRequest,
    ShortlistEntry,
    ShortlistResponse,
    SkillBreakdown,
    TiebreakerCandidateResult,
    TiebreakerDimensionRating,
    TiebreakerResponse,
)
from app.comparisons.tiering import assign_tiers
from app.comparisons.utils import to_ten_scale
from app.database import get_db
from app.jobs.models import Job
from app.jobs.schemas import (
    CreateJobRequest,
    GenerateDescriptionRequest,
    GenerateDescriptionResponse,
    JobAnalyticsSummary,
    JobResponse,
    SkillSplitRequest,
    SkillSplitResponse,
    UpdateJobRequest,
)
from app.limiter import limiter
from app.llm import get_llm_client
from app.llm.base import LLMParseError, LLMTimeoutError
from app.users.models import User, UserRole

router = APIRouter(prefix="/jobs", tags=["jobs"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

_llm = get_llm_client()


def _merged_required_skills(tech: list[str], soft: list[str], legacy: list[str]) -> list[str]:
    """Keep legacy required_skills in sync with the union of tech + soft."""
    seen: list[str] = []
    for source in (tech, soft, legacy):
        for s in source:
            if s and s not in seen:
                seen.append(s)
    return seen


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    request: Request,
    body: CreateJobRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> Job:
    tech = body.required_technical_skills
    soft = body.required_soft_skills
    legacy = body.required_skills
    # Back-compat: if caller didn't split but did provide a flat list, treat them all as technical.
    if not tech and not soft and legacy:
        tech = list(legacy)
    required = _merged_required_skills(tech, soft, legacy)

    # If no skills were provided at all, ask the LLM to suggest a split from
    # title + description. Failure is non-fatal — we just persist empty lists.
    if not tech and not soft and not legacy and (body.title or body.description):
        try:
            split = await _llm.suggest_skill_split(
                title=body.title,
                description=body.description,
                existing_skills=[],
            )
            tech = split.get("technical", [])
            soft = split.get("soft", [])
            required = _merged_required_skills(tech, soft, [])
        except Exception:
            pass

    job = Job(
        title=body.title,
        description=body.description,
        required_skills=required,
        required_technical_skills=tech,
        required_soft_skills=soft,
        decision_tags=body.decision_tags,
        required_seniority=body.required_seniority,
        location=body.location,
        creator_id=current_user.id,
        threshold_score=body.threshold_score,
        candidates_for_next_stage=body.candidates_for_next_stage,
    )
    db.add(job)
    await db.flush()
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.JOB_CREATED,
        resource_type="job",
        resource_id=job.id,
        request_id=getattr(request.state, "request_id", None),
        after=snapshot_job(job),
    )
    await db.commit()
    return job


@router.get(
    "",
    response_model=list[JobResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
async def list_jobs(db: DbDep) -> list[Job]:
    result = await db.execute(
        select(Job).where(Job.deleted_at.is_(None)).order_by(Job.created_at.desc())
    )
    return list(result.scalars().all())


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
async def get_job(job_id: uuid.UUID, db: DbDep) -> Job:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.patch(
    "/{job_id}",
    response_model=JobResponse,
    status_code=status.HTTP_200_OK,
)
async def update_job(
    request: Request,
    job_id: uuid.UUID,
    body: UpdateJobRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_job_owner_or_elevated)],
) -> Job:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    _before = snapshot_job(job)

    if body.title is not None:
        job.title = body.title
    if body.description is not None:
        job.description = body.description
    if body.required_seniority is not None:
        job.required_seniority = body.required_seniority
    if body.location is not None:
        job.location = body.location
    if body.decision_tags is not None:
        job.decision_tags = body.decision_tags or None
    if "threshold_score" in body.model_fields_set:
        job.threshold_score = body.threshold_score
    if "candidates_for_next_stage" in body.model_fields_set:
        job.candidates_for_next_stage = body.candidates_for_next_stage

    skills_touched = (
        body.required_technical_skills is not None
        or body.required_soft_skills is not None
        or body.required_skills is not None
    )
    if skills_touched:
        tech = (
            body.required_technical_skills
            if body.required_technical_skills is not None
            else job.required_technical_skills
        )
        soft = body.required_soft_skills if body.required_soft_skills is not None else job.required_soft_skills
        legacy = body.required_skills if body.required_skills is not None else job.required_skills
        job.required_technical_skills = tech
        job.required_soft_skills = soft
        job.required_skills = _merged_required_skills(tech, soft, legacy)

    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.JOB_UPDATED,
        resource_type="job",
        resource_id=job_id,
        request_id=getattr(request.state, "request_id", None),
        before=_before,
        after=snapshot_job(job),
    )
    await db.commit()
    return job


@router.post(
    "/generate-description",
    response_model=GenerateDescriptionResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/minute")
async def generate_job_description(
    request: Request,
    body: GenerateDescriptionRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_role(UserRole.RECRUITER, UserRole.HR_MANAGER, UserRole.ADMIN))],
) -> GenerateDescriptionResponse:
    """Generate a draft job description from title, seniority, and skills.

    Returns a draft only — does NOT persist a job.
    """
    try:
        draft = await _llm.generate_job_description(
            title=body.title,
            seniority=body.seniority,
            skills=body.required_skills,
            notes=body.notes,
        )
    except (LLMTimeoutError, LLMParseError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    # Emit business event — no persistent resource yet, so use a synthetic UUID
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.JOB_DESCRIPTION_GENERATED,
        resource_type="job_description_draft",
        resource_id=uuid.uuid4(),
        request_id=getattr(request.state, "request_id", None),
        meta={"title": body.title, "actor_email": current_user.email},
    )
    await db.commit()

    return GenerateDescriptionResponse(
        summary=draft["summary"],
        responsibilities=draft["responsibilities"],
        requirements=draft["requirements"],
    )


@router.post(
    "/auto-split-preview",
    response_model=SkillSplitResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_write)],
)
async def auto_split_preview(body: SkillSplitRequest) -> SkillSplitResponse:
    try:
        split = await _llm.suggest_skill_split(
            title=body.title,
            description=body.description,
            existing_skills=body.existing_skills,
        )
    except (LLMTimeoutError, LLMParseError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return SkillSplitResponse(technical=split["technical"], soft=split["soft"])


@router.post(
    "/{job_id}/auto-split-skills",
    response_model=SkillSplitResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_job_owner_or_elevated)],
)
async def auto_split_skills(job_id: uuid.UUID, db: DbDep) -> SkillSplitResponse:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    try:
        split = await _llm.suggest_skill_split(
            title=job.title,
            description=job.description,
            existing_skills=list(job.required_skills or []),
        )
    except (LLMTimeoutError, LLMParseError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return SkillSplitResponse(technical=split["technical"], soft=split["soft"])


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_job(
    request: Request,
    job_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(require_job_owner_or_elevated)],
) -> None:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    _before = snapshot_job(job)
    job.deleted_at = datetime.now(timezone.utc)
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.JOB_DELETED,
        resource_type="job",
        resource_id=job_id,
        request_id=getattr(request.state, "request_id", None),
        before=_before,
    )
    await db.commit()


@router.get(
    "/{job_id}/leaderboard",
    response_model=list[LeaderboardEntry],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
async def get_job_leaderboard(
    job_id: uuid.UUID,
    db: DbDep,
    limit: int = Query(default=20, ge=1, le=500),
) -> list[LeaderboardEntry]:
    job_row = await db.execute(
        select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
    )
    if job_row.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    applicant_subq = (
        select(JobApplication.candidate_id)
        .where(
            JobApplication.job_id == job_id,
            JobApplication.candidate_id.is_not(None),
            JobApplication.deleted_at.is_(None),
        )
        .scalar_subquery()
    )

    rows = await db.execute(
        select(CandidateJobScore, Candidate)
        .join(Candidate, CandidateJobScore.candidate_id == Candidate.id)
        .where(
            CandidateJobScore.job_id == job_id,
            CandidateJobScore.candidate_id.in_(applicant_subq),
        )
        .order_by(CandidateJobScore.overall_score.desc())
        .limit(limit)
    )

    entries = []
    for rank, (score, candidate) in enumerate(rows.all(), start=1):
        entries.append(
            LeaderboardEntry(
                rank=rank,
                candidate_id=candidate.id,
                candidate_name=candidate.name,
                candidate_email=candidate.email,
                candidate_seniority=candidate.seniority,
                overall_score=score.overall_score,
                overall_score_10=to_ten_scale(score.overall_score),
                dimension_scores=score.dimension_scores,
                skill_breakdown=SkillBreakdown.model_validate(score.skill_breakdown) if score.skill_breakdown else None,
                reasoning=score.reasoning,
                model_tag=score.model_tag,
                scored_at=score.scored_at,
                updated_at=score.updated_at,
            )
        )
    return entries


@router.get(
    "/{job_id}/analytics-summary",
    response_model=JobAnalyticsSummary,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
async def get_job_analytics_summary(job_id: uuid.UUID, db: DbDep) -> JobAnalyticsSummary:
    job_row = await db.execute(
        select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
    )
    if job_row.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    total: int = (
        await db.execute(
            select(func.count()).select_from(JobApplication)
            .where(JobApplication.job_id == job_id, JobApplication.deleted_at.is_(None))
        )
    ).scalar_one()

    applicant_subq = (
        select(JobApplication.candidate_id)
        .where(
            JobApplication.job_id == job_id,
            JobApplication.candidate_id.is_not(None),
            JobApplication.deleted_at.is_(None),
        )
        .scalar_subquery()
    )
    scored: int = (
        await db.execute(
            select(func.count()).select_from(CandidateJobScore)
            .where(
                CandidateJobScore.job_id == job_id,
                CandidateJobScore.candidate_id.in_(applicant_subq),
            )
        )
    ).scalar_one()

    return JobAnalyticsSummary(total_applications=total, scored_count=scored)


@router.get(
    "/{job_id}/qualified-candidates.pdf",
    dependencies=[Depends(require_write)],
)
async def export_qualified_candidates_pdf(
    job_id: uuid.UUID,
    db: DbDep,
    threshold: float = Query(default=DEFAULT_THRESHOLD_SCORE, ge=0.0, le=10.0),
    max_candidates: int = Query(default=1000, ge=1, le=5000),
) -> Response:
    from app.export.pdf import build_qualified_candidates_pdf

    job_row = await db.execute(
        select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
    )
    job = job_row.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    applicant_subq = (
        select(JobApplication.candidate_id)
        .where(
            JobApplication.job_id == job_id,
            JobApplication.candidate_id.is_not(None),
            JobApplication.deleted_at.is_(None),
        )
        .scalar_subquery()
    )
    rows = await db.execute(
        select(CandidateJobScore, Candidate)
        .join(Candidate, CandidateJobScore.candidate_id == Candidate.id)
        .where(
            CandidateJobScore.job_id == job_id,
            CandidateJobScore.candidate_id.in_(applicant_subq),
        )
        .order_by(CandidateJobScore.overall_score.desc())
        .limit(max_candidates)
    )

    qualified = []
    for score, candidate in rows.all():
        # Compare on the precise 0-10 value so 0.5-step display rounding never
        # flips threshold inclusion; emit the quantized value for display.
        precise = score.overall_score / 10 if score.overall_score is not None else None
        if precise is not None and precise >= threshold:
            qualified.append({
                "name": candidate.name,
                "email": candidate.email,
                "score": to_ten_scale(score.overall_score),
            })

    pdf_bytes = await asyncio.to_thread(
        build_qualified_candidates_pdf,
        job.title,
        threshold,
        qualified,
    )

    safe_title = "".join(c for c in (job.title or "role") if c.isalnum() or c in "- ").strip()[:40] or "role"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="qualified-{safe_title}.pdf"'},
    )


@router.get(
    "/{job_id}/shortlist",
    response_model=ShortlistResponse,
    status_code=status.HTTP_200_OK,
)
async def get_job_shortlist(
    job_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(get_current_user)],
    target: int | None = Query(default=None, ge=1),
    threshold: float | None = Query(default=None, ge=0.0, le=10.0),
) -> ShortlistResponse:
    job_row = await db.execute(
        select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
    )
    job = job_row.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    effective_target = target if target is not None else job.candidates_for_next_stage
    effective_threshold = (
        threshold if threshold is not None
        else (job.threshold_score if job.threshold_score is not None else DEFAULT_THRESHOLD_SCORE)
    )

    applicant_subq = (
        select(JobApplication.candidate_id)
        .where(
            JobApplication.job_id == job_id,
            JobApplication.candidate_id.is_not(None),
            JobApplication.deleted_at.is_(None),
        )
        .scalar_subquery()
    )

    applicant_count: int = (
        await db.execute(
            select(func.count()).select_from(JobApplication)
            .where(JobApplication.job_id == job_id, JobApplication.deleted_at.is_(None))
        )
    ).scalar_one()

    # Phase 1: minimal columns — no JSONB — for cut computation
    p1_result = await db.execute(
        select(
            CandidateJobScore.id,
            CandidateJobScore.overall_score,
            CandidateJobScore.updated_at,
            CandidateJobScore.candidate_id,
        )
        .where(
            CandidateJobScore.job_id == job_id,
            CandidateJobScore.candidate_id.in_(applicant_subq),
        )
    )
    p1_rows = p1_result.all()  # list of Row(id, overall_score, updated_at, candidate_id)

    if not p1_rows:
        return ShortlistResponse(
            mode="tiered" if effective_target is not None else "qualified_only",
            target=effective_target,
            threshold=effective_threshold,
            cut_rating=None,
            scored_count=0,
            applicant_count=applicant_count,
            latest_scored_at=None,
            entries=[],
        )

    assignment = assign_tiers(list(p1_rows), effective_target, effective_threshold)

    # Phase 2: full display data for all scored rows
    all_cjs_ids = [r.id for r in p1_rows]
    p2_result = await db.execute(
        select(CandidateJobScore, Candidate)
        .join(Candidate, CandidateJobScore.candidate_id == Candidate.id)
        .where(CandidateJobScore.id.in_(all_cjs_ids))
    )
    display_map: dict[str, tuple] = {
        str(score.id): (score, candidate) for score, candidate in p2_result.all()
    }

    latest_scored_at = max((r.updated_at for r in p1_rows), default=None)
    can_view_ai_scores = current_user.role != UserRole.VIEWER

    entries: list[ShortlistEntry] = []
    for rank, (p1_row, tier) in enumerate(assignment.entries, start=1):
        pair = display_map.get(str(p1_row.id))
        if pair is None:
            continue
        score, candidate = pair
        entries.append(
            ShortlistEntry(
                rank=rank,
                candidate_id=candidate.id,
                candidate_name=candidate.name,
                candidate_email=candidate.email,
                candidate_seniority=candidate.seniority,
                overall_score=score.overall_score if can_view_ai_scores else None,
                overall_score_10=to_ten_scale(score.overall_score) if can_view_ai_scores else None,
                dimension_scores=score.dimension_scores if can_view_ai_scores else {},
                skill_breakdown=(
                    SkillBreakdown.model_validate(score.skill_breakdown)
                    if can_view_ai_scores and score.skill_breakdown
                    else None
                ),
                reasoning=score.reasoning if can_view_ai_scores else None,
                model_tag=score.model_tag if can_view_ai_scores else None,
                scored_at=score.scored_at if can_view_ai_scores else None,
                updated_at=score.updated_at if can_view_ai_scores else None,
                tier=tier if can_view_ai_scores else None,
            )
        )

    return ShortlistResponse(
        mode=assignment.mode,
        target=effective_target,
        threshold=effective_threshold,
        cut_rating=assignment.cut_rating if can_view_ai_scores else None,
        scored_count=len(p1_rows),
        applicant_count=applicant_count,
        latest_scored_at=latest_scored_at if can_view_ai_scores else None,
        entries=entries,
    )


def _derive_tiebreaker_dimensions(job: Job) -> list[str]:
    dims = ["Technical Skill Depth", "Domain Experience", "Role Chemistry"]
    if job.required_soft_skills:
        dims.insert(2, "Communication & Leadership")
    return dims


@router.post(
    "/{job_id}/tiebreaker",
    response_model=TiebreakerResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("5/minute")
async def run_tiebreaker(
    request: Request,
    job_id: uuid.UUID,
    body: RunTiebreakerRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_job_owner_or_elevated)],
) -> TiebreakerResponse:
    from app.comparisons.scoring import candidate_to_data

    job_row = await db.execute(select(Job).where(Job.id == job_id, Job.deleted_at.is_(None)))
    job = job_row.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    effective_target = body.target if body.target is not None else job.candidates_for_next_stage
    if effective_target is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job must have candidates_for_next_stage set, or pass 'target' in the request body",
        )
    effective_threshold = (
        body.threshold if body.threshold is not None
        else (job.threshold_score if job.threshold_score is not None else DEFAULT_THRESHOLD_SCORE)
    )

    applicant_subq = (
        select(JobApplication.candidate_id)
        .where(
            JobApplication.job_id == job_id,
            JobApplication.candidate_id.is_not(None),
            JobApplication.deleted_at.is_(None),
        )
        .scalar_subquery()
    )

    p1_result = await db.execute(
        select(
            CandidateJobScore.id,
            CandidateJobScore.overall_score,
            CandidateJobScore.updated_at,
            CandidateJobScore.candidate_id,
        ).where(
            CandidateJobScore.job_id == job_id,
            CandidateJobScore.candidate_id.in_(applicant_subq),
        )
    )
    p1_rows = p1_result.all()

    assignment = assign_tiers(list(p1_rows), effective_target, effective_threshold)
    s_count = sum(1 for _, tier in assignment.entries if tier == "S")
    borderline_rows = [r for r, tier in assignment.entries if tier == "A"]
    slots_remaining = effective_target - s_count
    dimensions = body.custom_dimensions or _derive_tiebreaker_dimensions(job)

    if not borderline_rows or slots_remaining <= 0:
        return TiebreakerResponse(
            comparison_id=None,
            slots_remaining=max(0, slots_remaining),
            total_borderline=len(borderline_rows),
            dimensions=dimensions,
            results=[],
            summary="No tiebreaker needed: target slots are filled by clearly qualifying candidates.",
        )

    borderline_ids = [r.candidate_id for r in borderline_rows]
    cands_result = await db.execute(
        select(Candidate).where(Candidate.id.in_(borderline_ids), Candidate.deleted_at.is_(None))
    )
    candidates_map = {c.id: c for c in cands_result.scalars().all()}

    from app.parser.schemas import CandidateData as _CData
    labeled: list[tuple[str, str, _CData]] = []
    for row in borderline_rows:
        c = candidates_map.get(row.candidate_id)
        if c is None:
            continue
        labeled.append((str(c.id), c.name or f"Candidate {row.candidate_id}", candidate_to_data(c)))

    if not labeled:
        return TiebreakerResponse(
            comparison_id=None,
            slots_remaining=slots_remaining,
            total_borderline=len(borderline_rows),
            dimensions=dimensions,
            results=[],
            summary="No tiebreaker candidates could be loaded.",
        )

    comparison = Comparison(job_id=job.id, status="pending")
    db.add(comparison)
    await db.flush()

    try:
        tb_result = await _llm.tiebreaker_analysis(
            candidates=labeled,
            job_title=job.title,
            job_description=job.description,
            required_skills=list(job.required_skills or []),
            required_seniority=job.required_seniority,
            dimensions=dimensions,
            slots_remaining=slots_remaining,
        )
    except (LLMTimeoutError, LLMParseError) as exc:
        comparison.status = "failed"
        await db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    now = datetime.now(timezone.utc)
    name_to_id = {name: cid for (cid, name, _) in labeled}

    results: list[TiebreakerCandidateResult] = []
    output_rank = 0
    for item in tb_result.results:
        name = item.get("name", "")
        cid_str = name_to_id.get(name)
        if cid_str is None:
            # LLM returned a name we cannot resolve — skip to avoid orphaned records
            continue

        output_rank += 1
        candidate_id = uuid.UUID(cid_str)

        dim_ratings: dict[str, TiebreakerDimensionRating] = {}
        dim_scores_for_db: dict[str, int] = {}
        for dim_name, dim_val in item.get("dimension_ratings", {}).items():
            if isinstance(dim_val, dict):
                r = max(1, min(5, int(dim_val.get("rating", 3))))
                dim_ratings[dim_name] = TiebreakerDimensionRating(rating=r, notes=str(dim_val.get("notes", "")))
                dim_scores_for_db[dim_name] = r
            elif isinstance(dim_val, (int, float)):
                r = max(1, min(5, int(dim_val)))
                dim_ratings[dim_name] = TiebreakerDimensionRating(rating=r, notes="")
                dim_scores_for_db[dim_name] = r

        reasoning = str(item.get("reasoning", ""))
        cr = ComparisonResult(
            comparison_id=comparison.id,
            candidate_id=candidate_id,
            rank=output_rank,
            dimension_scores=dim_scores_for_db,
            reasoning=reasoning,
        )
        db.add(cr)
        results.append(TiebreakerCandidateResult(
            candidate_id=candidate_id,
            candidate_name=name,
            rank=output_rank,
            recommended=output_rank <= slots_remaining,
            dimension_ratings=dim_ratings,
            reasoning=reasoning,
        ))

    comparison.status = "completed"
    comparison.completed_at = now
    comparison.verdict = {
        "is_tiebreaker": True,
        "slots_remaining": slots_remaining,
        "tiebreaker_dimensions": dimensions,
        "summary": tb_result.summary,
    }

    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.TIEBREAKER_RUN,
        resource_type="comparison",
        resource_id=comparison.id,
        request_id=getattr(request.state, "request_id", None),
        after={
            "slots_remaining": slots_remaining,
            "total_borderline": len(labeled),
            "recommended": [str(r.candidate_id) for r in results if r.recommended],
        },
        meta={"job_id": str(job_id), "dimensions": dimensions},
    )
    await db.commit()

    return TiebreakerResponse(
        comparison_id=comparison.id,
        slots_remaining=slots_remaining,
        total_borderline=len(labeled),
        dimensions=dimensions,
        results=results,
        summary=tb_result.summary,
        created_at=now,
    )
