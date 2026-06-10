import asyncio
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import BusinessEventAction
from app.audit.events import record
from app.auth import get_current_user, require_write
from app.candidates.models import Candidate
from app.comparisons.models import Comparison, ComparisonResult
from app.comparisons.schemas import (
    ComparisonResponse,
    ComparisonResultResponse,
    ComparisonVerdict,
    CreateComparisonRequest,
    HeadToHeadResponse,
    SkillBreakdown,
)
from app.comparisons.scoring import candidate_to_data, score_with_cache
from app.comparisons.utils import to_ten_scale
from app.database import get_db
from app.jobs.models import Job
from app.limiter import limiter
from app.llm import get_llm_client
from app.llm.base import LLMParseError, LLMTimeoutError
from app.parser.schemas import CandidateData
from app.users.models import User

router = APIRouter(prefix="/comparisons", tags=["comparisons"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

_llm = get_llm_client()


def _build_comparison_response(comparison: Comparison, results: list[ComparisonResult]) -> ComparisonResponse:
    sorted_results = sorted(results, key=lambda r: r.rank or 999)
    verdict = None
    if comparison.verdict:
        try:
            verdict = ComparisonVerdict.model_validate(comparison.verdict)
        except Exception:
            verdict = None
    return ComparisonResponse(
        id=comparison.id,
        job_id=comparison.job_id,
        status=comparison.status,
        head_to_head_analysis=comparison.head_to_head_analysis,
        verdict=verdict,
        created_at=comparison.created_at,
        completed_at=comparison.completed_at,
        results=[
            ComparisonResultResponse(
                id=r.id,
                candidate_id=r.candidate_id,
                overall_score=r.overall_score,
                overall_score_10=to_ten_scale(r.overall_score),
                dimension_scores=r.dimension_scores,
                skill_breakdown=SkillBreakdown.model_validate(r.skill_breakdown) if r.skill_breakdown else None,
                reasoning=r.reasoning,
                rank=r.rank,
                created_at=r.created_at,
            )
            for r in sorted_results
        ],
    )


@router.get(
    "",
    response_model=list[ComparisonResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
async def list_comparisons(
    db: DbDep,
    job_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[ComparisonResponse]:
    query = select(Comparison).order_by(Comparison.created_at.desc())
    if job_id is not None:
        query = query.where(Comparison.job_id == job_id)
    query = query.limit(limit)
    comps_row = await db.execute(query)
    comparisons = list(comps_row.scalars().all())

    result_rows = await db.execute(
        select(ComparisonResult).where(
            ComparisonResult.comparison_id.in_([c.id for c in comparisons])
        )
    )
    all_results = list(result_rows.scalars().all())
    results_by_comp: dict[uuid.UUID, list[ComparisonResult]] = {}
    for r in all_results:
        results_by_comp.setdefault(r.comparison_id, []).append(r)

    return [
        _build_comparison_response(c, results_by_comp.get(c.id, []))
        for c in comparisons
    ]


@router.post(
    "",
    response_model=ComparisonResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
async def create_comparison(
    request: Request,
    body: CreateComparisonRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> ComparisonResponse:
    job_row = await db.execute(
        select(Job).where(Job.id == body.job_id, Job.deleted_at.is_(None))
    )
    job = job_row.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    candidates_row = await db.execute(
        select(Candidate).where(
            Candidate.id.in_(body.candidate_ids),
            Candidate.deleted_at.is_(None),
        )
    )
    candidates = list(candidates_row.scalars().all())
    found_ids = {c.id for c in candidates}
    missing = [str(cid) for cid in body.candidate_ids if cid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Candidates not found: {', '.join(missing)}",
        )

    comparison = Comparison(job_id=job.id, status="pending")
    db.add(comparison)
    await db.flush()

    try:
        scores = await asyncio.gather(*[score_with_cache(c, job, db) for c in candidates])
    except (LLMTimeoutError, LLMParseError) as exc:
        comparison.status = "failed"
        await db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    ranked = sorted(scores, key=lambda s: s[1], reverse=True)

    results: list[ComparisonResult] = []
    for rank, (candidate_id, overall_score, dimension_scores, reasoning, skill_breakdown) in enumerate(ranked, start=1):
        result = ComparisonResult(
            comparison_id=comparison.id,
            candidate_id=candidate_id,
            overall_score=overall_score,
            dimension_scores=dimension_scores,
            skill_breakdown=skill_breakdown,
            reasoning=reasoning,
            rank=rank,
        )
        db.add(result)
        results.append(result)

    comparison.status = "completed"
    comparison.completed_at = datetime.now(timezone.utc)
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.COMPARISON_CREATED,
        resource_type="comparison",
        resource_id=comparison.id,
        request_id=getattr(request.state, "request_id", None),
        after={"candidate_count": len(candidates), "top_candidate_id": str(ranked[0][0]) if ranked else None},
        meta={"job_id": str(body.job_id), "candidate_ids": [str(cid) for cid in body.candidate_ids]},
    )
    await db.commit()

    return _build_comparison_response(comparison, results)


@router.get(
    "/{comparison_id}",
    response_model=ComparisonResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
async def get_comparison(comparison_id: uuid.UUID, db: DbDep) -> ComparisonResponse:
    comp_row = await db.execute(
        select(Comparison).where(Comparison.id == comparison_id)
    )
    comparison = comp_row.scalar_one_or_none()
    if comparison is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found")

    results_row = await db.execute(
        select(ComparisonResult).where(ComparisonResult.comparison_id == comparison_id)
    )
    results = list(results_row.scalars().all())

    return _build_comparison_response(comparison, results)


@router.post(
    "/{comparison_id}/analyze",
    response_model=HeadToHeadResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/minute")
async def analyze_head_to_head(
    request: Request,
    comparison_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> HeadToHeadResponse:
    comp_row = await db.execute(
        select(Comparison).where(Comparison.id == comparison_id)
    )
    comparison = comp_row.scalar_one_or_none()
    if comparison is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found")
    if comparison.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Comparison is not completed (status: {comparison.status})",
        )

    # Idempotent: if we already have a structured verdict, return it.
    if comparison.verdict:
        try:
            cached = ComparisonVerdict.model_validate(comparison.verdict)
        except Exception:
            cached = None
        if cached is not None:
            return HeadToHeadResponse(
                analysis=comparison.head_to_head_analysis or cached.summary,
                verdict=cached,
            )

    job_row = await db.execute(select(Job).where(Job.id == comparison.job_id))
    job = job_row.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    results_row = await db.execute(
        select(ComparisonResult).where(ComparisonResult.comparison_id == comparison_id)
    )
    results = list(results_row.scalars().all())

    candidate_ids = [r.candidate_id for r in results]
    cands_row = await db.execute(
        select(Candidate).where(Candidate.id.in_(candidate_ids))
    )
    candidates_map = {c.id: c for c in cands_row.scalars().all()}

    labeled: list[tuple[str, str, CandidateData]] = []
    name_to_score: dict[str, int] = {}
    name_to_dims: dict[str, dict] = {}
    for result in sorted(results, key=lambda r: r.rank or 999):
        candidate = candidates_map.get(result.candidate_id)
        if candidate is None:
            continue
        name = candidate.name or f"Candidate {result.rank}"
        labeled.append((str(candidate.id), name, candidate_to_data(candidate)))
        name_to_score[name] = result.overall_score or 0
        if result.dimension_scores:
            name_to_dims[name] = result.dimension_scores

    try:
        structured = await _llm.compare_candidates_structured(
            candidates=labeled,
            job_title=job.title,
            job_description=job.description,
            required_skills=job.required_skills,
            job_decision_tags=list(job.decision_tags or []) or None,
            required_seniority=job.required_seniority,
            scores=name_to_score,
            dimension_scores=name_to_dims,
        )
    except (LLMTimeoutError, LLMParseError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    # Derive decision from top candidate's actual score — deterministic, not LLM-guessed.
    top_score = max(name_to_score.values(), default=0)
    if top_score >= 80:
        decision = "strong"
    elif top_score >= 60:
        decision = "moderate"
    else:
        decision = "weak"

    verdict_dict = {
        "summary": structured.summary,
        "recommended_candidate_id": structured.recommended_candidate_id,
        "decision": decision,
        "decision_tags": list(structured.decision_tags or []),
    }
    comparison.verdict = verdict_dict
    # Keep legacy text field populated for back-compat with any older readers.
    comparison.head_to_head_analysis = structured.summary
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.COMPARISON_ANALYZED,
        resource_type="comparison",
        resource_id=comparison_id,
        request_id=getattr(request.state, "request_id", None),
        after={
            "recommended_candidate_id": structured.recommended_candidate_id,
            "decision": structured.decision,
        },
        meta={"job_id": str(comparison.job_id)},
    )
    await db.commit()

    return HeadToHeadResponse(
        analysis=structured.summary,
        verdict=ComparisonVerdict.model_validate(verdict_dict),
    )
