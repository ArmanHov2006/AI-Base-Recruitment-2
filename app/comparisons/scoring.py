"""Shared scoring helper.

Extracted from ``app.comparisons.router`` so the Celery worker can call the
same cached-score path used by the synchronous compare endpoint.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.models import Candidate
from app.comparisons.models import CandidateJobScore
from app.comparisons.utils import compute_score_input_hash
from app.config import settings
from app.jobs.models import Job
from app.llm import get_llm_client
from app.parser.schemas import CandidateData, Education, WorkExperience

_llm = get_llm_client()


def candidate_to_data(c: Candidate) -> CandidateData:
    return CandidateData(
        name=c.name,
        email=c.email,
        phone=c.phone,
        skills=c.skills,
        years_experience=c.years_experience,
        education=[Education(**e) for e in c.education],
        work_experiences=[WorkExperience(**e) for e in c.work_experiences],
        location=c.location,
        seniority=c.seniority,
        summary=c.summary,
        desired_position=c.desired_position,
    )


async def score_one(
    candidate: Candidate,
    job: Job,
) -> tuple[uuid.UUID, int, dict, str, dict | None]:
    data = candidate_to_data(candidate)
    result = await _llm.score_candidate(
        candidate=data,
        job_title=job.title,
        job_description=job.description,
        required_skills=job.required_skills,
        required_technical_skills=list(job.required_technical_skills or []),
        required_soft_skills=list(job.required_soft_skills or []),
        required_seniority=job.required_seniority,
    )
    return (
        candidate.id,
        result.overall_score,
        result.dimension_scores,
        result.reasoning,
        result.skill_breakdown,
    )


async def score_with_cache(
    candidate: Candidate,
    job: Job,
    db: AsyncSession,
) -> tuple[uuid.UUID, int, dict, str, dict | None]:
    model_tag = settings.openai_model if settings.llm_provider == "openai" else settings.ollama_model
    hash_val = compute_score_input_hash(candidate, job, model_tag)

    cached = await db.execute(
        select(CandidateJobScore).where(
            CandidateJobScore.job_id == job.id,
            CandidateJobScore.candidate_id == candidate.id,
            CandidateJobScore.score_input_hash == hash_val,
        )
    )
    row = cached.scalar_one_or_none()
    if row is not None:
        return (
            candidate.id,
            row.overall_score or 0,
            row.dimension_scores,
            row.reasoning or "",
            row.skill_breakdown,
        )

    candidate_id, overall_score, dimension_scores, reasoning, skill_breakdown = await score_one(
        candidate, job
    )

    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(CandidateJobScore)
        .values(
            job_id=job.id,
            candidate_id=candidate.id,
            overall_score=overall_score,
            dimension_scores=dimension_scores,
            skill_breakdown=skill_breakdown,
            reasoning=reasoning,
            model_tag=model_tag,
            score_input_hash=hash_val,
            scored_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            constraint="uq_candidate_job_scores_job_candidate",
            set_={
                "overall_score": overall_score,
                "dimension_scores": dimension_scores,
                "skill_breakdown": skill_breakdown,
                "reasoning": reasoning,
                "model_tag": model_tag,
                "score_input_hash": hash_val,
                "updated_at": now,
            },
        )
    )
    await db.execute(stmt)

    return (candidate_id, overall_score, dimension_scores, reasoning, skill_breakdown)
