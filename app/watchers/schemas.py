import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WatcherUserSummary(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None


class JobWatcherResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: WatcherUserSummary
    filters: dict
    created_at: datetime


class AddJobWatcherRequest(BaseModel):
    user_id: uuid.UUID
    filters: dict = {}


class UpdateJobWatcherFiltersRequest(BaseModel):
    filters: dict


class CandidateWatcherResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: WatcherUserSummary
    created_at: datetime


class AddCandidateWatcherRequest(BaseModel):
    user_id: uuid.UUID | None = None  # None = add self
