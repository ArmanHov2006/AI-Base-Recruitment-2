"""Tests for /jobs/{id}/applications endpoints — single, bulk, stage transitions."""

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.models import JobApplication
from app.applications.router import router as applications_router
from app.auth import get_current_user, require_write
from app.database import get_db
from app.users.models import UserRole
from tests.conftest import make_mock_db, make_user, make_valid_token

_JOB_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
_APP_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440002")
_FILE_ID = "550e8400-e29b-41d4-a716-446655440000"
_NOW = datetime.now(timezone.utc)

AUTH = {"Authorization": f"Bearer {make_valid_token(UserRole.RECRUITER)}"}
VIEWER_AUTH = {"Authorization": f"Bearer {make_valid_token(UserRole.VIEWER)}"}


def _make_job_orm(**overrides: object) -> MagicMock:
    j = MagicMock()
    j.id = _JOB_ID
    j.title = "Backend Engineer"
    j.deleted_at = None
    j.creator_id = None
    for k, v in overrides.items():
        setattr(j, k, v)
    return j


def _make_app_orm(**overrides: object) -> MagicMock:
    a = MagicMock(spec=JobApplication)
    a.id = _APP_ID
    a.job_id = _JOB_ID
    a.candidate_id = None
    a.status = "parsing"
    a.resume_file_id = _FILE_ID
    a.error_message = None
    a.source = None
    a.applied_at = _NOW
    a.updated_at = _NOW
    a.deleted_at = None
    a.allow_duplicate = False
    a.interview_scheduled_at = None
    a.interview_location = None
    for k, v in overrides.items():
        setattr(a, k, v)
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


def _setup_execute_sequence(mock_db: AsyncMock, *responses: MagicMock) -> None:
    iter_responses = iter(responses)

    async def _side_effect(*args: object, **kwargs: object) -> MagicMock:
        try:
            return next(iter_responses)
        except StopIteration:
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            r.scalars.return_value.all.return_value = []
            r.all.return_value = []
            return r

    mock_db.execute = AsyncMock(side_effect=_side_effect)


def _found(obj: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    r.scalars.return_value.all.return_value = [obj] if obj else []
    return r


def _empty() -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    r.scalars.return_value.all.return_value = []
    return r


# ── POST /jobs/{id}/applications (single) ─────────────────────────────────────

async def test_create_application_returns_202(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    job = _make_job_orm()
    _make_app_orm()
    _now = datetime.now(timezone.utc)

    added: list[object] = []

    def _add(obj: object) -> None:
        if isinstance(obj, JobApplication):
            obj.id = _APP_ID  # type: ignore[assignment]
            obj.applied_at = _now  # type: ignore[assignment]
            obj.updated_at = _now  # type: ignore[assignment]
        added.append(obj)

    mock_db.add = _add
    _setup_execute_sequence(mock_db, _found(job))

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
    mock_task.delay.assert_called_once()


async def test_create_application_invalid_file_id_returns_400(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    job = _make_job_orm()
    _setup_execute_sequence(mock_db, _found(job))
    r = await client.post(
        f"/jobs/{_JOB_ID}/applications",
        headers=AUTH,
        json={"file_id": "not-a-valid-uuid"},
    )
    assert r.status_code == 400


async def test_create_application_job_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _setup_execute_sequence(mock_db, _empty())
    r = await client.post(
        f"/jobs/{_JOB_ID}/applications",
        headers=AUTH,
        json={"file_id": _FILE_ID},
    )
    assert r.status_code == 404


async def test_create_application_viewer_denied(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    _app = client._transport.app  # type: ignore[attr-defined]
    _app.dependency_overrides[require_write] = lambda: (_ for _ in ()).throw(
        __import__("fastapi").HTTPException(status_code=403)
    )
    r = await client.post(
        f"/jobs/{_JOB_ID}/applications",
        headers=VIEWER_AUTH,
        json={"file_id": _FILE_ID},
    )
    assert r.status_code == 403


# ── POST /jobs/{id}/applications/bulk ─────────────────────────────────────────

async def test_bulk_create_applications_returns_202(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    job = _make_job_orm()
    file_ids = [
        "550e8400-e29b-41d4-a716-446655440001",
        "550e8400-e29b-41d4-a716-446655440002",
        "550e8400-e29b-41d4-a716-446655440003",
    ]
    _now = datetime.now(timezone.utc)
    _idx = [0]

    def _add(obj: object) -> None:
        if isinstance(obj, JobApplication):
            obj.id = uuid.uuid4()  # type: ignore[assignment]
            obj.applied_at = _now  # type: ignore[assignment]
            obj.updated_at = _now  # type: ignore[assignment]

    mock_db.add = _add
    _setup_execute_sequence(mock_db, _found(job))

    with patch("app.applications.router.apply_pipeline_task") as mock_task:
        mock_task.delay = MagicMock()
        r = await client.post(
            f"/jobs/{_JOB_ID}/applications/bulk",
            headers=AUTH,
            json={"file_ids": file_ids},
        )

    assert r.status_code == 202
    data = r.json()
    assert "application_ids" in data
    assert len(data["application_ids"]) == 3
    assert mock_task.delay.call_count == 3


async def test_bulk_create_empty_file_ids_returns_422(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    r = await client.post(
        f"/jobs/{_JOB_ID}/applications/bulk",
        headers=AUTH,
        json={"file_ids": []},
    )
    assert r.status_code == 422


async def test_bulk_create_too_many_files_returns_422(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    # More than 100 file_ids
    file_ids = [f"550e8400-e29b-41d4-a716-{str(i).zfill(12)}" for i in range(101)]
    r = await client.post(
        f"/jobs/{_JOB_ID}/applications/bulk",
        headers=AUTH,
        json={"file_ids": file_ids},
    )
    assert r.status_code == 422


async def test_bulk_create_invalid_file_id_returns_400(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    job = _make_job_orm()
    _setup_execute_sequence(mock_db, _found(job))
    r = await client.post(
        f"/jobs/{_JOB_ID}/applications/bulk",
        headers=AUTH,
        json={"file_ids": ["not-a-uuid", "550e8400-e29b-41d4-a716-446655440002"]},
    )
    assert r.status_code == 400


# ── GET /jobs/{id}/applications ───────────────────────────────────────────────

async def test_list_applications_returns_list(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    job = _make_job_orm()
    app_orm = _make_app_orm(status="applied", candidate_id=None)
    _setup_execute_sequence(mock_db, _found(job), _found(app_orm))
    r = await client.get(f"/jobs/{_JOB_ID}/applications", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


async def test_list_applications_job_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _setup_execute_sequence(mock_db, _empty())
    r = await client.get(f"/jobs/{_JOB_ID}/applications", headers=AUTH)
    assert r.status_code == 404


# ── DELETE /jobs/{id}/applications/{app_id} ───────────────────────────────────
# Note: stage transitions live on the evaluations router — see test_evaluations.py

async def test_delete_application_returns_204(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    # delete_application only calls _load_application (no separate job lookup)
    app_orm = _make_app_orm()
    _setup_execute_sequence(mock_db, _found(app_orm))
    r = await client.delete(
        f"/jobs/{_JOB_ID}/applications/{_APP_ID}", headers=AUTH
    )
    assert r.status_code == 204
    assert app_orm.deleted_at is not None


async def test_delete_application_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _setup_execute_sequence(mock_db, _empty())
    r = await client.delete(
        f"/jobs/{_JOB_ID}/applications/{_APP_ID}", headers=AUTH
    )
    assert r.status_code == 404
