"""Shared resume parsing logic used by both /parse and /jobs/{id}/applications."""

import datetime
import re
import uuid

from fastapi import HTTPException, status
from minio.error import S3Error
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import get_llm_client
from app.llm.base import LLMParseError, LLMTimeoutError
from app.parser.extractor import delete_file, extract_github_url, extract_linkedin_url, extract_text, fetch_file_bytes
from app.parser.lang_detect import detect_language
from app.parser.schemas import CandidateData, WorkExperience

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_llm = get_llm_client()


def _parse_year_month(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        year_str, month_str = value.split("-", 1)
        return int(year_str), int(month_str)
    except (ValueError, AttributeError):
        return None


def calc_years(candidate: CandidateData) -> float | None:
    today = datetime.date.today()
    total_months = 0
    counted_any = False
    unparsed_present_roles = 0

    for exp in candidate.work_experiences:
        start = _parse_year_month(exp.start_date)
        if start is None:
            if exp.end_date is None:
                unparsed_present_roles += 1
            continue
        end = _parse_year_month(exp.end_date) or (today.year, today.month)
        months = (end[0] - start[0]) * 12 + (end[1] - start[1])
        if months > 0:
            total_months += months
            counted_any = True

    if counted_any:
        return round(total_months / 12, 2)

    if candidate.years_experience and candidate.years_experience > 0:
        return candidate.years_experience

    if unparsed_present_roles > 0:
        return float(unparsed_present_roles * 2)

    return candidate.years_experience


def _has_identity(candidate: CandidateData) -> bool:
    has_name = bool(candidate.name and candidate.name.strip())
    has_contact = bool(
        (candidate.email and candidate.email.strip())
        or (candidate.phone and candidate.phone.strip())
    )
    return has_name and has_contact


async def _build_job_context(db: AsyncSession, job_id: uuid.UUID) -> str:
    from app.jobs.models import Job  # local import avoids circular at module level

    job_row = await db.execute(
        select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
    )
    job = job_row.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    skills_str = ", ".join(job.required_skills) if job.required_skills else "not specified"
    desc_line = f"Description: {job.description}" if job.description else ""
    return (
        f"Role: {job.title}\n"
        f"Required skills: {skills_str}\n"
        f"{desc_line}"
    ).strip()


def validate_file_id(file_id: str) -> None:
    if not _UUID4_RE.match(file_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file_id must be a valid UUID4",
        )


async def parse_and_validate(
    file_id: str,
    db: AsyncSession,
    job_id: uuid.UUID | None = None,
) -> CandidateData:
    """Parse a resume from MinIO, run LLM extraction, compute years,
    enforce the identity gate, and normalize the email.

    On any failure (LLM error, missing identity), the source file is removed
    from MinIO and an HTTPException is raised.
    """
    validate_file_id(file_id)

    job_context = await _build_job_context(db, job_id) if job_id is not None else None

    try:
        content = await fetch_file_bytes(file_id)
    except S3Error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    full_text = extract_text(content)
    text = full_text[:8000]

    async def _extract_once() -> CandidateData:
        try:
            return await _llm.extract(text, job_context=job_context)
        except LLMTimeoutError as exc:
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc))
        except LLMParseError as exc:
            await delete_file(file_id)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
        except Exception as exc:
            await delete_file(file_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"LLM error: {exc}",
            ) from exc

    result = await _extract_once()
    # Retry once if identity fields are null — handles flaky LLM responses under load
    if not _has_identity(result):
        result = await _extract_once()

    if result.email:
        result.email = result.email.strip().lower() or None
    if result.name:
        result.name = result.name.strip() or None
    if result.phone:
        result.phone = result.phone.strip() or None
    if not result.linkedin_url:
        result.linkedin_url = extract_linkedin_url(full_text)
    if not result.github_url:
        result.github_url = extract_github_url(full_text)

    if not _has_identity(result):
        await delete_file(file_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Resume missing required identity (name plus email or phone)",
        )

    result.years_experience = calc_years(result)
    # F5 — detect resume language from the raw text and annotate the result.
    result.resume_language = detect_language(full_text)
    return result


__all__ = [
    "WorkExperience",
    "calc_years",
    "parse_and_validate",
    "validate_file_id",
]
