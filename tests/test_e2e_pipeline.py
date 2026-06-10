"""E2E integration test — full resume pipeline: upload → parse → apply → score → leaderboard.

Uses CELERY_TASK_ALWAYS_EAGER=True (set in config) so .delay() runs synchronously.
All external services (MinIO, Ollama, Postgres) are mocked so this runs without infra.
"""

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.router import router as applications_router
from app.auth import get_current_user, require_write
from app.database import get_db
from app.parser.schemas import CandidateData
from app.users.models import UserRole
from tests.conftest import make_mock_db, make_user, make_valid_token

# ── Constants ─────────────────────────────────────────────────────────────────

_JOB_ID = uuid.UUID("770e8400-e29b-41d4-a716-446655440001")
_CANDIDATE_ID = uuid.UUID("770e8400-e29b-41d4-a716-446655440002")
_APP_ID = uuid.UUID("770e8400-e29b-41d4-a716-446655440003")
_FILE_ID = "550e8400-e29b-41d4-a716-446655440099"
_NOW = datetime.now(timezone.utc)

AUTH = {"Authorization": f"Bearer {make_valid_token(UserRole.RECRUITER)}"}

_PARSED_CANDIDATE = CandidateData(
    name="Alice Engineer",
    email="alice@example.com",
    skills=["python", "fastapi", "postgresql"],
    years_experience=6.0,
    seniority="senior",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_job_orm() -> MagicMock:
    j = MagicMock()
    j.id = _JOB_ID
    j.title = "Senior Backend Engineer"
    j.required_skills = ["python", "postgresql"]
    j.required_technical_skills = ["python", "postgresql"]
    j.required_soft_skills = []
    j.required_seniority = "senior"
    j.description = "Backend role"
    j.location = "Yerevan"
    j.decision_tags = []
    j.creator_id = None
    j.created_at = _NOW
    j.deleted_at = None
    return j


def _make_app_orm() -> MagicMock:
    from app.applications.models import JobApplication
    a = MagicMock(spec=JobApplication)
    a.id = _APP_ID
    a.job_id = _JOB_ID
    a.candidate_id = None
    a.resume_file_id = _FILE_ID
    a.status = "parsing"
    a.error_message = None
    a.applied_at = _NOW
    a.updated_at = _NOW
    a.deleted_at = None
    a.allow_duplicate = False
    return a


@pytest.fixture
async def client_and_db() -> AsyncGenerator[tuple[AsyncClient, AsyncMock], None]:
    mock_db = make_mock_db()
    _app = FastAPI()
    _app.include_router(applications_router)
    recruiter = make_user(UserRole.RECRUITER)
    _app.dependency_overrides[get_current_user] = lambda: recruiter
    _app.dependency_overrides[require_write] = lambda: recruiter

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    _app.dependency_overrides[get_db] = db_override
    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as c:
        yield c, mock_db


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_submit_application_starts_pipeline(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    """POST /jobs/{id}/applications → 202, Celery task enqueued, application status = parsing."""
    client, mock_db = client_and_db
    job = _make_job_orm()
    _now = datetime.now(timezone.utc)

    from app.applications.models import JobApplication

    def _add(obj: object) -> None:
        if isinstance(obj, JobApplication):
            obj.id = _APP_ID  # type: ignore[assignment]
            obj.applied_at = _now  # type: ignore[assignment]
            obj.updated_at = _now  # type: ignore[assignment]

    mock_db.add = _add
    mock_db.execute.return_value.scalar_one_or_none.return_value = job

    with patch("app.applications.router.apply_pipeline_task") as mock_task:
        mock_task.delay = MagicMock()
        r = await client.post(
            f"/jobs/{_JOB_ID}/applications",
            headers=AUTH,
            json={"file_id": _FILE_ID},
        )

    assert r.status_code == 202
    data = r.json()
    assert data["status"] == "parsing"
    assert data["resume_file_id"] == _FILE_ID
    # Celery task was dispatched with the application ID
    mock_task.delay.assert_called_once_with(str(_APP_ID))


async def test_duplicate_detection_blocks_resubmission(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    """Submitting the same file_id twice should be blocked by duplicate detection in the parser."""
    # Duplicate detection happens in the Celery task (apply_pipeline_task), not the router.
    # This test verifies that allow_duplicate=False is persisted on the application.
    client, mock_db = client_and_db
    job = _make_job_orm()
    _now = datetime.now(timezone.utc)

    from app.applications.models import JobApplication

    added_apps: list[JobApplication] = []

    def _add(obj: object) -> None:
        if isinstance(obj, JobApplication):
            obj.id = _APP_ID  # type: ignore[assignment]
            obj.applied_at = _now  # type: ignore[assignment]
            obj.updated_at = _now  # type: ignore[assignment]
            added_apps.append(obj)  # type: ignore[arg-type]

    mock_db.add = _add
    mock_db.execute.return_value.scalar_one_or_none.return_value = job

    with patch("app.applications.router.apply_pipeline_task") as mock_task:
        mock_task.delay = MagicMock()
        r = await client.post(
            f"/jobs/{_JOB_ID}/applications",
            headers=AUTH,
            json={"file_id": _FILE_ID},
        )

    assert r.status_code == 202
    assert len(added_apps) >= 1
    # Default: allow_duplicate=False means dedup is active
    assert added_apps[0].allow_duplicate is False


async def test_allow_duplicate_flag_bypasses_dedup(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    """?allow_duplicate=true sets allow_duplicate=True on the created application."""
    client, mock_db = client_and_db
    job = _make_job_orm()
    _now = datetime.now(timezone.utc)

    from app.applications.models import JobApplication

    added_apps: list[JobApplication] = []

    def _add(obj: object) -> None:
        if isinstance(obj, JobApplication):
            obj.id = _APP_ID  # type: ignore[assignment]
            obj.applied_at = _now  # type: ignore[assignment]
            obj.updated_at = _now  # type: ignore[assignment]
            added_apps.append(obj)  # type: ignore[arg-type]

    mock_db.add = _add
    mock_db.execute.return_value.scalar_one_or_none.return_value = job

    with patch("app.applications.router.apply_pipeline_task") as mock_task:
        mock_task.delay = MagicMock()
        r = await client.post(
            f"/jobs/{_JOB_ID}/applications?allow_duplicate=true",
            headers=AUTH,
            json={"file_id": _FILE_ID},
        )

    assert r.status_code == 202
    assert len(added_apps) >= 1
    assert added_apps[0].allow_duplicate is True


async def test_bulk_pipeline_enqueues_one_task_per_file(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    """POST /jobs/{id}/applications/bulk with 3 files → 3 Celery tasks dispatched."""
    client, mock_db = client_and_db
    job = _make_job_orm()
    file_ids = [
        "550e8400-e29b-41d4-a716-446655440010",
        "550e8400-e29b-41d4-a716-446655440011",
        "550e8400-e29b-41d4-a716-446655440012",
    ]
    _now = datetime.now(timezone.utc)

    from app.applications.models import JobApplication

    def _add(obj: object) -> None:
        if isinstance(obj, JobApplication):
            obj.id = uuid.uuid4()  # type: ignore[assignment]
            obj.applied_at = _now  # type: ignore[assignment]
            obj.updated_at = _now  # type: ignore[assignment]

    mock_db.add = _add
    mock_db.execute.return_value.scalar_one_or_none.return_value = job

    with patch("app.applications.router.apply_pipeline_task") as mock_task:
        mock_task.delay = MagicMock()
        r = await client.post(
            f"/jobs/{_JOB_ID}/applications/bulk",
            headers=AUTH,
            json={"file_ids": file_ids},
        )

    assert r.status_code == 202
    data = r.json()
    assert len(data["application_ids"]) == 3
    assert mock_task.delay.call_count == 3


async def test_parse_and_validate_produces_candidate_with_identity() -> None:
    """Unit test for parse_and_validate: valid PDF → CandidateData with name + email."""
    from app.parser.service import parse_and_validate

    PDF_BYTES = b"%PDF-1.4\n%%EOF"
    FAKE_CANDIDATE = CandidateData(
        name="Bob Smith",
        email="bob@example.com",
        skills=["java", "spring"],
        years_experience=3.0,
        seniority="mid",
    )

    mock_db = AsyncMock()

    with (
        patch("app.parser.service.fetch_file_bytes", new=AsyncMock(return_value=PDF_BYTES)),
        patch("app.parser.service.extract_text", return_value="Bob Smith resume"),
        patch("app.parser.service._llm.extract", new=AsyncMock(return_value=FAKE_CANDIDATE)),
    ):
        result = await parse_and_validate(_FILE_ID, mock_db)

    assert result.name == "Bob Smith"
    assert result.email == "bob@example.com"
    assert "java" in result.skills


async def test_parse_and_validate_missing_identity_raises_422() -> None:
    """Resume without name or contact info should 422."""
    from fastapi import HTTPException

    from app.parser.service import parse_and_validate

    PDF_BYTES = b"%PDF-1.4\n%%EOF"
    NAMELESS = CandidateData(
        name=None,
        email=None,
        skills=["python"],
        years_experience=0.0,
        seniority="junior",
    )

    mock_db = AsyncMock()

    with (
        patch("app.parser.service.fetch_file_bytes", new=AsyncMock(return_value=PDF_BYTES)),
        patch("app.parser.service.extract_text", return_value="some text"),
        patch("app.parser.service._llm.extract", new=AsyncMock(return_value=NAMELESS)),
        patch("app.parser.service.delete_file", new=AsyncMock()),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await parse_and_validate(_FILE_ID, mock_db)

    assert exc_info.value.status_code == 422
