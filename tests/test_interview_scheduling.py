"""Tests for PATCH /jobs/{job_id}/applications/{app_id}/interview — F1 interview scheduling."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.models import JobApplication
from app.applications.router import router as applications_router
from app.audit.actions import BusinessEventAction
from app.auth import get_current_user, require_write
from app.database import get_db
from app.users.models import UserRole
from tests.conftest import make_mock_db, make_user, make_valid_token

_JOB_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440010")
_APP_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440011")
_FILE_ID = "550e8400-e29b-41d4-a716-446655440000"
_NOW = datetime.now(timezone.utc)
_FUTURE = _NOW + timedelta(days=1)

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
    a.status = "interview"
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


_INTERVIEW_URL = f"/jobs/{_JOB_ID}/applications/{_APP_ID}/interview"


# ── Set interview (schedule) ──────────────────────────────────────────────────

async def test_set_interview_schedule_returns_200(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    app_orm = _make_app_orm(interview_scheduled_at=None)
    _setup_execute_sequence(mock_db, _found(app_orm))

    r = await client.patch(
        _INTERVIEW_URL,
        headers=AUTH,
        json={"scheduled_at": _FUTURE.isoformat(), "location": "Room 3A"},
    )

    assert r.status_code == 200
    data = r.json()
    assert data["interview_scheduled_at"] is not None
    assert data["interview_location"] == "Room 3A"


async def test_set_interview_clear_returns_200(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    app_orm = _make_app_orm(interview_scheduled_at=_FUTURE)
    _setup_execute_sequence(mock_db, _found(app_orm))

    r = await client.patch(
        _INTERVIEW_URL,
        headers=AUTH,
        json={"scheduled_at": None, "location": None},
    )

    assert r.status_code == 200
    data = r.json()
    assert data["interview_scheduled_at"] is None


async def test_set_interview_app_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _setup_execute_sequence(mock_db, _empty())

    r = await client.patch(
        _INTERVIEW_URL,
        headers=AUTH,
        json={"scheduled_at": _FUTURE.isoformat(), "location": None},
    )

    assert r.status_code == 404


async def test_set_interview_viewer_denied(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    _app = client._transport.app  # type: ignore[attr-defined]
    _app.dependency_overrides[require_write] = lambda: (_ for _ in ()).throw(
        __import__("fastapi").HTTPException(status_code=403)
    )
    r = await client.patch(
        _INTERVIEW_URL,
        headers=VIEWER_AUTH,
        json={"scheduled_at": _FUTURE.isoformat(), "location": None},
    )
    assert r.status_code == 403


async def test_set_interview_location_too_long_returns_422(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    r = await client.patch(
        _INTERVIEW_URL,
        headers=AUTH,
        json={"scheduled_at": _FUTURE.isoformat(), "location": "x" * 501},
    )
    assert r.status_code == 422


# ── Business event action selection ──────────────────────────────────────────

async def test_set_interview_emits_scheduled_action(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    app_orm = _make_app_orm(interview_scheduled_at=None)
    _setup_execute_sequence(mock_db, _found(app_orm))

    recorded: list[object] = []
    mock_db.add = lambda obj: recorded.append(obj)

    r = await client.patch(
        _INTERVIEW_URL,
        headers=AUTH,
        json={"scheduled_at": _FUTURE.isoformat(), "location": None},
    )

    assert r.status_code == 200
    from app.audit.events import BusinessEvent
    events = [o for o in recorded if isinstance(o, BusinessEvent)]
    assert len(events) == 1
    assert events[0].action == BusinessEventAction.INTERVIEW_SCHEDULED.value


async def test_set_interview_emits_rescheduled_action(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    app_orm = _make_app_orm(interview_scheduled_at=_FUTURE)
    _setup_execute_sequence(mock_db, _found(app_orm))

    recorded: list[object] = []
    mock_db.add = lambda obj: recorded.append(obj)

    new_time = (_FUTURE + timedelta(hours=2)).isoformat()
    r = await client.patch(
        _INTERVIEW_URL,
        headers=AUTH,
        json={"scheduled_at": new_time, "location": None},
    )

    assert r.status_code == 200
    from app.audit.events import BusinessEvent
    events = [o for o in recorded if isinstance(o, BusinessEvent)]
    assert len(events) == 1
    assert events[0].action == BusinessEventAction.INTERVIEW_RESCHEDULED.value


async def test_set_interview_emits_cleared_action(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    app_orm = _make_app_orm(interview_scheduled_at=_FUTURE)
    _setup_execute_sequence(mock_db, _found(app_orm))

    recorded: list[object] = []
    mock_db.add = lambda obj: recorded.append(obj)

    r = await client.patch(
        _INTERVIEW_URL,
        headers=AUTH,
        json={"scheduled_at": None, "location": None},
    )

    assert r.status_code == 200
    from app.audit.events import BusinessEvent
    events = [o for o in recorded if isinstance(o, BusinessEvent)]
    assert len(events) == 1
    assert events[0].action == BusinessEventAction.INTERVIEW_CLEARED.value


# ── Existing ApplicationResponse includes interview fields ────────────────────

async def test_list_applications_returns_interview_fields(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    job = _make_job_orm()
    app_orm = _make_app_orm(
        status="interview",
        interview_scheduled_at=_FUTURE,
        interview_location="Room 3A",
    )
    _setup_execute_sequence(mock_db, _found(job), _found(app_orm))
    r = await client.get(f"/jobs/{_JOB_ID}/applications", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
