import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.gdpr.router import router as gdpr_router
from app.users.models import UserRole
from tests.conftest import make_user

_CAND_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440010")
_NOW = datetime.now(timezone.utc)


def _candidate() -> MagicMock:
    c = MagicMock()
    c.id = _CAND_ID
    c.file_id = "file-1"
    c.status = "parsed"
    c.name = "Jane Doe"
    c.email = "jane@example.com"
    c.phone = "+37400000000"
    c.skills = ["Python"]
    c.years_experience = 5.0
    c.education = []
    c.work_experiences = []
    c.location = "Yerevan"
    c.seniority = "senior"
    c.summary = None
    c.desired_position = "Backend Engineer"
    c.certifications = ["AWS SAA"]
    c.languages = ["Armenian", "English"]
    c.linkedin_url = "https://linkedin.com/in/jane"
    c.github_url = None
    c.desired_salary = 5000
    c.created_at = _NOW
    c.deleted_at = None
    return c


def _application() -> MagicMock:
    a = MagicMock()
    a.id = uuid.uuid4()
    a.job_id = uuid.uuid4()
    a.candidate_id = _CAND_ID
    a.resume_file_id = "resume-1"
    a.status = "interview"
    a.error_message = None
    a.applied_at = _NOW
    a.updated_at = _NOW
    a.deleted_at = None
    return a


def _note() -> MagicMock:
    n = MagicMock()
    n.id = uuid.uuid4()
    n.candidate_id = _CAND_ID
    n.author_id = uuid.uuid4()
    n.text = "Strong candidate"
    n.created_at = _NOW
    n.updated_at = _NOW
    n.deleted_at = None
    return n


def _result(*, scalar=None, items=None) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalars.return_value.all.return_value = items or []
    return r


def _make_app(
    execute_results: list, *, role: UserRole = UserRole.ADMIN
) -> tuple[FastAPI, AsyncMock]:
    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.execute = AsyncMock(side_effect=execute_results)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    app = FastAPI()
    app.include_router(gdpr_router)

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    app.dependency_overrides[get_db] = db_override
    user = make_user(role)
    app.dependency_overrides[require_admin] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user
    return app, mock_db


@pytest.fixture
async def admin_client() -> AsyncGenerator[tuple[AsyncClient, AsyncMock], None]:
    # execute order: candidate, applications, evaluations, notes,
    # business_events, audit_log (record() only does db.add, no execute)
    cand = _candidate()
    app_row = _application()
    note_row = _note()
    results = [
        _result(scalar=cand),
        _result(items=[app_row]),
        _result(items=[]),
        _result(items=[note_row]),
        _result(items=[]),
        _result(items=[]),
    ]
    app, mock_db = _make_app(results)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_db


async def test_gdpr_export_returns_full_bundle(
    admin_client: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = admin_client
    r = await client.get(f"/candidates/{_CAND_ID}/gdpr-export")
    assert r.status_code == 200

    # Downloads as an attachment file.
    assert "attachment" in r.headers["content-disposition"]
    assert f"gdpr-export-{_CAND_ID}.json" in r.headers["content-disposition"]

    data = r.json()
    assert data["candidate"]["id"] == str(_CAND_ID)
    assert data["candidate"]["email"] == "jane@example.com"
    assert data["candidate"]["linkedin_url"] == "https://linkedin.com/in/jane"
    assert len(data["applications"]) == 1
    assert data["applications"][0]["candidate_id"] == str(_CAND_ID)
    assert len(data["notes"]) == 1
    assert data["notes"][0]["text"] == "Strong candidate"
    assert data["export_metadata"]["record_counts"]["applications"] == 1
    assert data["export_metadata"]["record_counts"]["notes"] == 1

    # The export was recorded + committed as a business event.
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


async def test_gdpr_export_candidate_not_found_returns_404() -> None:
    app, _ = _make_app([_result(scalar=None)])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/candidates/{_CAND_ID}/gdpr-export")
    assert r.status_code == 404


async def test_gdpr_export_invalid_uuid_returns_422() -> None:
    app, _ = _make_app([])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/candidates/not-a-uuid/gdpr-export")
    assert r.status_code == 422


async def test_gdpr_export_non_admin_forbidden() -> None:
    # Don't override require_admin — let the real role check run against a recruiter.
    mock_db = AsyncMock(spec=AsyncSession)
    app = FastAPI()
    app.include_router(gdpr_router)

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    recruiter = make_user(UserRole.RECRUITER)
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = lambda: recruiter

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/candidates/{_CAND_ID}/gdpr-export")
    assert r.status_code == 403
