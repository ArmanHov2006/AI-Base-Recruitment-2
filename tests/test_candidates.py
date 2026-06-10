"""Tests for /candidates endpoints."""

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_write
from app.candidates.models import Candidate
from app.candidates.router import router as candidates_router
from app.database import get_db
from app.users.models import UserRole
from tests.conftest import make_mock_db, make_user, make_valid_token

AUTH = {"Authorization": f"Bearer {make_valid_token(UserRole.RECRUITER)}"}
VIEWER_AUTH = {"Authorization": f"Bearer {make_valid_token(UserRole.VIEWER)}"}

_FAKE_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440001")
_FAKE_FILE_ID = "550e8400-e29b-41d4-a716-446655440000"
_NOW = datetime.now(timezone.utc)


def _make_fake_orm(**overrides: object) -> MagicMock:
    orm = MagicMock(spec=Candidate)
    orm.id = _FAKE_ID
    orm.file_id = _FAKE_FILE_ID
    orm.status = "parsed"
    orm.name = "Jane Doe"
    orm.email = "jane@example.com"
    orm.phone = None
    orm.skills = ["python", "fastapi"]
    orm.years_experience = 5.0
    orm.education = []
    orm.work_experiences = []
    orm.location = "Yerevan"
    orm.seniority = "senior"
    orm.summary = None
    orm.desired_position = "Backend Engineer"
    orm.certifications = []
    orm.languages = []
    orm.linkedin_url = None
    orm.github_url = None
    orm.desired_salary = None
    orm.photo_url = None
    orm.current_resume_version = 1
    orm.created_at = _NOW
    orm.deleted_at = None
    for k, v in overrides.items():
        setattr(orm, k, v)
    return orm


_CREATE_BODY = {
    "file_id": _FAKE_FILE_ID,
    "name": "Jane Doe",
    "email": "jane@example.com",
    "skills": ["Python", "FastAPI"],
    "years_experience": 5.0,
    "seniority": "senior",
}


@pytest.fixture
async def client_and_db() -> AsyncGenerator[tuple[AsyncClient, AsyncMock], None]:
    mock_db = make_mock_db()
    _app = FastAPI()
    _app.include_router(candidates_router)

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    _app.dependency_overrides[get_db] = db_override
    _fake_user = make_user(UserRole.RECRUITER)
    _app.dependency_overrides[get_current_user] = lambda: _fake_user
    _app.dependency_overrides[require_write] = lambda: _fake_user
    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as c:
        yield c, mock_db


# ── POST /candidates ──────────────────────────────────────────────────────────

async def test_create_candidate_returns_201(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _now = datetime.now(timezone.utc)

    # Intercept db.add to inject columns normally set by SQLAlchemy defaults at flush time
    added: list[object] = []
    def _add(obj: object) -> None:
        if isinstance(obj, Candidate):
            obj.id = _FAKE_ID  # type: ignore[assignment]
            obj.status = "parsed"  # type: ignore[assignment]
            obj.created_at = _now  # type: ignore[assignment]
        added.append(obj)
    mock_db.add = _add

    r = await client.post("/candidates", headers=AUTH, json=_CREATE_BODY)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Jane Doe"
    assert data["status"] == "parsed"
    assert data["file_id"] == _FAKE_FILE_ID
    assert "python" in data["skills"]
    assert "id" in data


async def test_create_candidate_duplicate_email_returns_409(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    existing = _make_fake_orm()
    mock_db.execute.return_value.scalar_one_or_none.return_value = existing
    r = await client.post("/candidates", headers=AUTH, json=_CREATE_BODY)
    assert r.status_code == 409


async def test_create_candidate_missing_file_id_returns_422(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    r = await client.post("/candidates", headers=AUTH, json={"name": "No File"})
    assert r.status_code == 422


# ── GET /candidates ───────────────────────────────────────────────────────────

async def test_list_candidates_returns_list(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    fake = _make_fake_orm()
    mock_db.execute.return_value.scalars.return_value.all.return_value = [fake]
    r = await client.get("/candidates", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "Jane Doe"


async def test_list_candidates_empty(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    r = await client.get("/candidates", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []


async def test_list_candidates_viewer_allowed(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _app = client._transport.app  # type: ignore[attr-defined]
    viewer = make_user(UserRole.VIEWER)
    _app.dependency_overrides[get_current_user] = lambda: viewer
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    r = await client.get("/candidates", headers=VIEWER_AUTH)
    assert r.status_code == 200


# ── GET /candidates/{id} ──────────────────────────────────────────────────────

async def test_get_candidate_returns_200(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    fake = _make_fake_orm()
    mock_db.execute.return_value.scalar_one_or_none.return_value = fake
    r = await client.get(f"/candidates/{_FAKE_ID}", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Jane Doe"
    assert data["seniority"] == "senior"
    assert data["location"] == "Yerevan"


async def test_get_candidate_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    r = await client.get(f"/candidates/{_FAKE_ID}", headers=AUTH)
    assert r.status_code == 404


async def test_get_candidate_invalid_uuid_returns_422(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    r = await client.get("/candidates/not-a-uuid", headers=AUTH)
    assert r.status_code == 422


# ── PATCH /candidates/{id} ────────────────────────────────────────────────────

async def test_patch_candidate_returns_200(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    fake = _make_fake_orm()
    mock_db.execute.return_value.scalar_one_or_none.return_value = fake
    r = await client.patch(
        f"/candidates/{_FAKE_ID}",
        headers=AUTH,
        json={"name": "Jane Updated", "location": "Tbilisi"},
    )
    assert r.status_code == 200


async def test_patch_candidate_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    r = await client.patch(
        f"/candidates/{_FAKE_ID}",
        headers=AUTH,
        json={"name": "Jane Updated"},
    )
    assert r.status_code == 404


async def test_patch_candidate_viewer_denied(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _app = client._transport.app  # type: ignore[attr-defined]
    _app.dependency_overrides[require_write] = lambda: (_ for _ in ()).throw(
        __import__("fastapi").HTTPException(status_code=403)
    )
    r = await client.patch(
        f"/candidates/{_FAKE_ID}",
        headers=VIEWER_AUTH,
        json={"name": "Jane Updated"},
    )
    assert r.status_code == 403


# ── DELETE /candidates/{id} ───────────────────────────────────────────────────

async def test_delete_candidate_returns_204(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    fake = _make_fake_orm(deleted_at=None)
    mock_db.execute.return_value.scalar_one_or_none.return_value = fake
    r = await client.delete(f"/candidates/{_FAKE_ID}", headers=AUTH)
    assert r.status_code == 204
    assert fake.deleted_at is not None


async def test_delete_candidate_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    r = await client.delete(f"/candidates/{_FAKE_ID}", headers=AUTH)
    assert r.status_code == 404


async def test_delete_already_deleted_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    # The router queries WHERE deleted_at IS NULL — a soft-deleted record returns nothing.
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    r = await client.delete(f"/candidates/{_FAKE_ID}", headers=AUTH)
    assert r.status_code == 404
