import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateJobRequest(BaseModel):
    title: str
    description: str | None = None
    required_skills: list[str] = []
    required_seniority: str | None = None
    location: str | None = None
    required_technical_skills: list[str] = []
    required_soft_skills: list[str] = []
    decision_tags: dict | None = None
    threshold_score: float | None = Field(None, ge=0.0, le=10.0)
    candidates_for_next_stage: int | None = Field(None, ge=1)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    required_skills: list[str]
    required_seniority: str | None
    location: str | None
    required_technical_skills: list[str]
    required_soft_skills: list[str]
    decision_tags: dict | None
    threshold_score: float | None
    candidates_for_next_stage: int | None
    created_at: datetime
    deleted_at: datetime | None


class UpdateJobRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    required_skills: list[str] | None = None
    required_technical_skills: list[str] | None = None
    required_soft_skills: list[str] | None = None
    required_seniority: str | None = None
    location: str | None = None
    decision_tags: dict | None = None
    threshold_score: float | None = Field(None, ge=0.0, le=10.0)
    candidates_for_next_stage: int | None = Field(None, ge=1)


class JobAnalyticsSummary(BaseModel):
    total_applications: int
    scored_count: int


class SkillSplitRequest(BaseModel):
    title: str
    description: str | None = None
    existing_skills: list[str] = []


class SkillSplitResponse(BaseModel):
    technical: list[str]
    soft: list[str]


class GenerateDescriptionRequest(BaseModel):
    title: str
    seniority: str
    required_skills: list[str] = []
    notes: str | None = None


class GenerateDescriptionResponse(BaseModel):
    summary: str
    responsibilities: list[str]
    requirements: list[str]

