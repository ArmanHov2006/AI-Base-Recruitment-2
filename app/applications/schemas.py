import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.candidates.schemas import CandidateResponse

APPLICATION_STATUSES = (
    "parsing",
    "parse_failed",
    "applied",
    "reviewing",
    "shortlisted",
    "screening",
    "interview",
    "offer",
    "hired",
    "rejected",
    "withdrawn",
)

ApplicationStatus = Literal[
    "parsing",
    "parse_failed",
    "applied",
    "reviewing",
    "shortlisted",
    "screening",
    "interview",
    "offer",
    "hired",
    "rejected",
    "withdrawn",
]

# Subset that the user can manually set via PATCH — parsing/parse_failed are server-managed.
USER_SETTABLE_STATUSES = (
    "applied",
    "reviewing",
    "shortlisted",
    "screening",
    "interview",
    "offer",
    "hired",
    "rejected",
    "withdrawn",
)

UserSettableStatus = Literal[
    "applied",
    "reviewing",
    "shortlisted",
    "screening",
    "interview",
    "offer",
    "hired",
    "rejected",
    "withdrawn",
]


APPLICATION_SOURCES = (
    "linkedin",
    "indeed",
    "referral",
    "company_website",
    "job_fair",
    "headhunter",
    "other",
)


class CreateApplicationRequest(BaseModel):
    file_id: str
    source: str | None = None


class BulkCreateApplicationsRequest(BaseModel):
    file_ids: list[str]
    source: str | None = None

    @field_validator("file_ids")
    @classmethod
    def validate_file_ids(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("file_ids must not be empty")
        if len(v) > 100:
            raise ValueError("file_ids must not exceed 100 items per request")
        return v


class BulkCreateApplicationsResponse(BaseModel):
    application_ids: list[str]


class UpdateApplicationStatusRequest(BaseModel):
    status: UserSettableStatus


class SetInterviewRequest(BaseModel):
    scheduled_at: datetime | None = None
    location: Annotated[str | None, StringConstraints(max_length=500)] = None


class CandidateApplicationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    job_title: str | None = None
    status: ApplicationStatus
    interview_scheduled_at: datetime | None = None
    interview_location: str | None = None
    applied_at: datetime


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    candidate_id: uuid.UUID | None = None
    status: ApplicationStatus
    resume_file_id: str
    error_message: str | None = None
    source: str | None = None
    applied_at: datetime
    updated_at: datetime
    overall_score_10: float | None = None
    scored_at: datetime | None = None
    interview_scheduled_at: datetime | None = None
    interview_location: str | None = None
    candidate: CandidateResponse | None = None
