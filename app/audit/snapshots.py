"""
Full-row snapshot helpers for audit before/after fields.

Rules:
- Only access scalar columns — no relationships or lazy-loaded attrs
  (async SQLAlchemy raises MissingGreenlet on lazy loads)
- Normalise types: UUID→str, datetime→isoformat, enum→.value, None→None
- Exclude secrets: hashed_password, token_hash fields
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


def _s(v: Any) -> Any:
    """Normalise a scalar value for JSONB storage."""
    if v is None:
        return None
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if hasattr(v, "value"):  # enum
        return v.value
    return v


def snapshot_job(job: Any) -> dict:
    return {
        "id": _s(job.id),
        "title": job.title,
        "description": job.description,
        "required_skills": job.required_skills,
        "required_technical_skills": job.required_technical_skills,
        "required_soft_skills": job.required_soft_skills,
        "required_seniority": job.required_seniority,
        "location": job.location,
        "decision_tags": job.decision_tags,
        "creator_id": _s(job.creator_id),
        "created_at": _s(job.created_at),
        "deleted_at": _s(job.deleted_at),
    }


def snapshot_candidate(candidate: Any) -> dict:
    return {
        "id": _s(candidate.id),
        "file_id": candidate.file_id,
        "status": candidate.status,
        "name": candidate.name,
        "email": candidate.email,
        "phone": candidate.phone,
        "skills": candidate.skills,
        "years_experience": candidate.years_experience,
        "education": candidate.education,
        "work_experiences": candidate.work_experiences,
        "location": candidate.location,
        "seniority": candidate.seniority,
        "summary": candidate.summary,
        "desired_position": candidate.desired_position,
        "certifications": candidate.certifications,
        "languages": candidate.languages,
        "linkedin_url": candidate.linkedin_url,
        "github_url": candidate.github_url,
        "desired_salary": candidate.desired_salary,
        "created_at": _s(candidate.created_at),
        "deleted_at": _s(candidate.deleted_at),
        # embedding excluded — large binary, not useful in audit diff
    }


def snapshot_application(app: Any) -> dict:
    return {
        "id": _s(app.id),
        "job_id": _s(app.job_id),
        "candidate_id": _s(app.candidate_id),
        "resume_file_id": app.resume_file_id,
        "status": app.status,
        "error_message": app.error_message,
        "interview_scheduled_at": _s(app.interview_scheduled_at),
        "interview_location": app.interview_location,
        "applied_at": _s(app.applied_at),
        "updated_at": _s(app.updated_at),
        "deleted_at": _s(app.deleted_at),
    }


def snapshot_evaluation(evaluation: Any) -> dict:
    return {
        "id": _s(evaluation.id),
        "candidate_id": _s(evaluation.candidate_id),
        "job_id": _s(evaluation.job_id),
        "evaluator_id": _s(evaluation.evaluator_id),
        "stage": evaluation.stage,
        "overall_rating": evaluation.overall_rating,
        "technical_score": evaluation.technical_score,
        "communication_score": evaluation.communication_score,
        "leadership_score": evaluation.leadership_score,
        "cultural_fit_score": evaluation.cultural_fit_score,
        "english_score": evaluation.english_score,
        "domain_score": evaluation.domain_score,
        "feedback": evaluation.feedback,
        "ai_suggested_rating": evaluation.ai_suggested_rating,
        "created_at": _s(evaluation.created_at),
        "updated_at": _s(evaluation.updated_at),
        "deleted_at": _s(evaluation.deleted_at),
    }


def snapshot_note(note: Any) -> dict:
    return {
        "id": _s(note.id),
        "candidate_id": _s(note.candidate_id),
        "author_id": _s(note.author_id),
        "text": note.text,
        "created_at": _s(note.created_at),
        "updated_at": _s(note.updated_at),
        "deleted_at": _s(note.deleted_at),
    }


def snapshot_user(user: Any) -> dict:
    # Excludes: hashed_password, token fields
    return {
        "id": _s(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": _s(user.role),
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "created_at": _s(user.created_at),
        "deleted_at": _s(user.deleted_at),
    }


def snapshot_invite(invite: Any) -> dict:
    # Excludes: token_hash (raw secret)
    return {
        "id": _s(invite.id),
        "email": invite.email,
        "role": _s(invite.role),
        "expires_at": _s(invite.expires_at),
        "used_at": _s(invite.used_at),
        "created_by": _s(invite.created_by),
        "created_at": _s(invite.created_at),
    }
