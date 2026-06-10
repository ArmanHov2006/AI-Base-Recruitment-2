import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class CreateNoteRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be blank")
        return v


class UpdateNoteRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be blank")
        return v


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    candidate_id: uuid.UUID
    author_id: uuid.UUID
    text: str
    created_at: datetime
    updated_at: datetime
