import uuid

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    candidate_id: uuid.UUID
    message: str = Field(min_length=1, max_length=2000)
    job_id: uuid.UUID | None = None
