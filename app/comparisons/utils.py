import hashlib
import json

from app.candidates.models import Candidate
from app.jobs.models import Job


def to_ten_scale(score_100: int | None) -> float | None:
    """Convert a 0-100 overall score to a 0-10 display value in 0.5 steps.

    Storage stays 0-100 (high-resolution sort key); the coarse 0.5-step scale
    is a presentation concern derived at the API edge.
    """
    if score_100 is None:
        return None
    return round(score_100 / 10 * 2) / 2


def compute_score_input_hash(candidate: Candidate, job: Job, model_tag: str) -> str:
    payload = {
        "model_tag": model_tag,
        "job_title": job.title,
        "job_description": job.description,
        "required_skills": sorted(job.required_skills or []),
        "required_technical_skills": sorted(job.required_technical_skills or []),
        "required_soft_skills": sorted(job.required_soft_skills or []),
        "candidate_skills": sorted(candidate.skills or []),
        "years_experience": candidate.years_experience,
        "education": sorted(
            [json.dumps(e, sort_keys=True) for e in (candidate.education or [])]
        ),
        "work_experiences": sorted(
            [json.dumps(w, sort_keys=True) for w in (candidate.work_experiences or [])]
        ),
        "seniority": candidate.seniority,
        "summary": candidate.summary,
        "required_seniority": job.required_seniority,
    }
    serialized = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
