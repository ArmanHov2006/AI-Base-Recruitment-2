import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateComparisonRequest(BaseModel):
    job_id: uuid.UUID
    candidate_ids: list[uuid.UUID]

    @field_validator("candidate_ids")
    @classmethod
    def validate_candidate_ids(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(v) < 2:
            raise ValueError("At least 2 candidates required for comparison")
        if len(v) > 20:
            raise ValueError("Maximum 20 candidates per comparison")
        if len(set(v)) != len(v):
            raise ValueError("Duplicate candidate IDs are not allowed")
        return v


class DimensionScores(BaseModel):
    skills_match: int
    experience_level: int
    education: int
    seniority_fit: int


class SkillScore(BaseModel):
    name: str
    score: int


class SkillBreakdown(BaseModel):
    technical: list[SkillScore] = []
    soft: list[SkillScore] = []


class ComparisonVerdict(BaseModel):
    summary: str
    recommended_candidate_id: uuid.UUID
    decision: Literal["strong", "moderate", "weak"]
    decision_tags: list[str] = Field(default_factory=list, max_length=5)


class ComparisonResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    candidate_id: uuid.UUID
    overall_score: int | None
    overall_score_10: float | None = None
    dimension_scores: dict
    skill_breakdown: SkillBreakdown | None = None
    reasoning: str | None
    rank: int | None
    created_at: datetime


class ComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    status: str
    head_to_head_analysis: str | None
    verdict: ComparisonVerdict | None = None
    created_at: datetime
    completed_at: datetime | None
    results: list[ComparisonResultResponse] = []


class HeadToHeadResponse(BaseModel):
    analysis: str
    verdict: ComparisonVerdict | None = None


class LeaderboardEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    candidate_id: uuid.UUID
    candidate_name: str | None
    candidate_email: str | None = None
    candidate_seniority: str | None = None
    overall_score: int | None
    overall_score_10: float | None = None
    dimension_scores: dict
    skill_breakdown: SkillBreakdown | None
    reasoning: str | None
    model_tag: str | None = None
    scored_at: datetime | None = None
    updated_at: datetime | None = None


class ShortlistEntry(LeaderboardEntry):
    tier: Literal["S", "A", "B", "F"] | None = None


class ShortlistResponse(BaseModel):
    mode: Literal["tiered", "qualified_only"]
    target: int | None
    threshold: float
    cut_rating: float | None
    scored_count: int
    applicant_count: int
    latest_scored_at: datetime | None
    entries: list[ShortlistEntry]


class RunTiebreakerRequest(BaseModel):
    target: int | None = Field(default=None, ge=1)
    threshold: float | None = Field(default=None, ge=0.0, le=10.0)
    custom_dimensions: list[str] | None = Field(default=None, max_length=8)


class TiebreakerDimensionRating(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    notes: str


class TiebreakerCandidateResult(BaseModel):
    candidate_id: uuid.UUID
    candidate_name: str | None
    rank: int
    recommended: bool
    dimension_ratings: dict[str, TiebreakerDimensionRating]
    reasoning: str


class TiebreakerResponse(BaseModel):
    comparison_id: uuid.UUID | None = None
    slots_remaining: int
    total_borderline: int
    dimensions: list[str]
    results: list[TiebreakerCandidateResult]
    summary: str
    created_at: datetime | None = None
