import uuid
from datetime import datetime

from pydantic import BaseModel


class SkillCount(BaseModel):
    skill: str
    count: int


class OverviewResponse(BaseModel):
    total_candidates: int
    active_candidates: int
    total_jobs: int
    total_applications: int
    applications_by_status: dict[str, int]
    top_skills: list[SkillCount]


class FunnelStage(BaseModel):
    stage: str
    count: int
    conversion_rate: float | None


class FunnelResponse(BaseModel):
    stages: list[FunnelStage]


class RecruiterActivityItem(BaseModel):
    evaluator_id: uuid.UUID
    evaluator_name: str | None
    evaluation_count: int
    avg_rating: float | None
    last_active: datetime | None


class RecruiterActivityResponse(BaseModel):
    recruiters: list[RecruiterActivityItem]


class JobTimeToHire(BaseModel):
    job_id: uuid.UUID
    job_title: str | None
    hired_count: int
    avg_days_to_hire: float | None


class TimeToHireResponse(BaseModel):
    overall_avg_days: float | None
    total_hired: int
    per_job: list[JobTimeToHire]


class CandidateSourceItem(BaseModel):
    source: str
    count: int


class CandidateSourcesResponse(BaseModel):
    data: list[CandidateSourceItem]
