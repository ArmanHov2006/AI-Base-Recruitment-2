import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class InterviewSessionCreate(BaseModel):
    application_id: uuid.UUID
    candidate_id: uuid.UUID
    job_id: uuid.UUID


class InterviewSessionRead(BaseModel):
    id: uuid.UUID
    status: str
    questions: list[Any]
    display_name: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InterviewAnswerRead(BaseModel):
    id: uuid.UUID
    question_index: int
    question_text: str
    transcript: str | None
    failure_reason: str | None
    attempt_consumed_at: datetime | None

    model_config = {"from_attributes": True}


# Lane A schemas — presigned upload and attempt-lock


class UploadUrlRequest(BaseModel):
    content_type: str


class UploadUrlResponse(BaseModel):
    url: str
    fields: dict[str, str]
    file_id: str


class StartAttemptResponse(BaseModel):
    session_id: uuid.UUID
    question_index: int
    attempt_consumed_at: datetime
