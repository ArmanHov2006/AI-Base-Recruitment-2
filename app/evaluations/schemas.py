import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.applications.schemas import UserSettableStatus

EvalStage = Literal["reviewing", "shortlisted", "interview", "offer", "hired", "rejected"]


class CreateEvaluationRequest(BaseModel):
    job_id: uuid.UUID
    stage: EvalStage
    overall_rating: int | None = None
    technical_score: int | None = None
    communication_score: int | None = None
    leadership_score: int | None = None
    cultural_fit_score: int | None = None
    english_score: int | None = None
    domain_score: int | None = None
    feedback: str | None = None
    ai_suggested_rating: int | None = None


class UpdateEvaluationRequest(BaseModel):
    stage: EvalStage | None = None
    overall_rating: int | None = None
    technical_score: int | None = None
    communication_score: int | None = None
    leadership_score: int | None = None
    cultural_fit_score: int | None = None
    english_score: int | None = None
    domain_score: int | None = None
    feedback: str | None = None
    ai_suggested_rating: int | None = None


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    evaluator_id: uuid.UUID
    evaluator_name: str | None = None
    stage: str
    overall_rating: int | None
    technical_score: int | None
    communication_score: int | None
    leadership_score: int | None
    cultural_fit_score: int | None
    english_score: int | None
    domain_score: int | None
    feedback: str | None
    ai_suggested_rating: int | None
    created_at: datetime
    updated_at: datetime


class StageTransitionRequest(BaseModel):
    stage: UserSettableStatus
    reason: str | None = None
