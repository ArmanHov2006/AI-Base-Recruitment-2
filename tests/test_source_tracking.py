"""Tests for C4: candidate source tracking on job_applications."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.applications.router import router as applications_router
from app.applications.schemas import APPLICATION_SOURCES
from app.auth import get_current_user, require_write
from app.database import get_db
from app.users.models import UserRole
from tests.conftest import make_mock_db, make_valid_token

AUTH = {"Authorization": f"Bearer {make_valid_token(UserRole.RECRUITER)}"}
_JOB_ID = uuid.uuid4()
_APP_ID = uuid.uuid4()
_FILE_ID = "550e8400-e29b-41d4-a716-446655440000"
_NOW = datetime.now(timezone.utc)


def _make_mock_job() -> MagicMock:
    job = MagicMock()
    job.id = _JOB_ID
    job.title = "Backend Engineer"
    job.creator_id = None
    job.deleted_at = None
    return job


def _make_mock_app(source: str | None = None) -> MagicMock:
    app = MagicMock()
    app.id = _APP_ID
    app.job_id = _JOB_ID
    app.candidate_id = None
    app.status = "parsing"
    app.resume_file_id = _FILE_ID
    app.error_message = None
    app.source = source
    app.applied_at = _NOW
    app.updated_at = _NOW
    app.allow_duplicate = False
    app.deleted_at = None
    return app


@pytest.fixture
async def client() -> AsyncClient:
    mock_db = make_mock_db()
    _app = FastAPI()
    _app.include_router(applications_router)
    _app.dependency_overrides[get_db] = lambda: mock_db

    _user = MagicMock()
    _user.id = uuid.uuid4()
    _user.role = UserRole.RECRUITER
    _app.dependency_overrides[get_current_user] = lambda: _user
    _app.dependency_overrides[require_write] = lambda: _user

    mock_db.execute = AsyncMock(
        return_value=MagicMock(**{"scalar_one_or_none.return_value": _make_mock_job()})
    )

    with patch("app.applications.router.validate_file_id"), \
         patch("app.applications.router.apply_pipeline_task") as mock_task, \
         patch("app.applications.router.record", new_callable=AsyncMock), \
         patch("app.applications.router.snapshot_application", return_value={}):
        mock_task.delay = MagicMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

        async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as c:
            yield c


@pytest.mark.asyncio
async def test_application_sources_defined() -> None:
    assert "linkedin" in APPLICATION_SOURCES
    assert "referral" in APPLICATION_SOURCES
    assert "other" in APPLICATION_SOURCES


@pytest.mark.asyncio
async def test_application_response_has_source_field() -> None:
    from app.applications.schemas import ApplicationResponse
    fields = ApplicationResponse.model_fields
    assert "source" in fields
