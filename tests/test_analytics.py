"""Tests for /analytics endpoints."""

from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.router import router as analytics_router
from app.auth import get_current_user, require_admin
from app.database import get_db
from app.users.models import UserRole
from tests.conftest import make_mock_db, make_user, make_valid_token

AUTH = {"Authorization": f"Bearer {make_valid_token(UserRole.RECRUITER)}"}
ADMIN_AUTH = {"Authorization": f"Bearer {make_valid_token(UserRole.ADMIN)}"}


@pytest.fixture
async def client_and_db() -> AsyncGenerator[tuple[AsyncClient, AsyncMock], None]:
    mock_db = make_mock_db()
    _app = FastAPI()
    _app.include_router(analytics_router)
    recruiter = make_user(UserRole.RECRUITER)
    _app.dependency_overrides[get_current_user] = lambda: recruiter
    _app.dependency_overrides[require_admin] = lambda: recruiter

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    _app.dependency_overrides[get_db] = db_override
    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as c:
        yield c, mock_db


def _setup_overview(mock_db: AsyncMock) -> None:
    """Configure mock to return stable overview data across multiple execute calls."""
    call_count = [0]
    results = [
        _scalar_one(5),   # total_candidates
        _scalar_one(3),   # total_jobs
        _scalar_one(10),  # total_applications
        _rows([]),         # applications by status (group-by)
        _rows([]),         # avg score
        _rows([]),         # top skills
    ]

    def _side_effect(*args: object, **kwargs: object) -> MagicMock:
        idx = min(call_count[0], len(results) - 1)
        call_count[0] += 1
        return results[idx]

    mock_db.execute = AsyncMock(side_effect=_side_effect)


def _scalar_one(value: int) -> MagicMock:
    r = MagicMock()
    r.scalar_one.return_value = value
    r.scalar_one_or_none.return_value = value
    r.scalars.return_value.all.return_value = []
    r.all.return_value = []
    return r


def _rows(rows: list) -> MagicMock:
    r = MagicMock()
    r.scalar_one.return_value = 0
    r.scalars.return_value.all.return_value = rows
    r.all.return_value = rows
    return r


# ── GET /analytics/overview ───────────────────────────────────────────────────

async def test_overview_returns_correct_shape(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _setup_overview(mock_db)
    r = await client.get("/analytics/overview", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert "total_candidates" in data
    assert "total_jobs" in data
    assert "total_applications" in data
    assert "applications_by_status" in data
    assert "top_skills" in data


async def test_overview_unauthenticated_returns_401(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    _app = client._transport.app  # type: ignore[attr-defined]
    _app.dependency_overrides.pop(get_current_user, None)
    r = await client.get("/analytics/overview")
    assert r.status_code == 401


# ── GET /analytics/funnel ─────────────────────────────────────────────────────

async def test_funnel_returns_stages(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    mock_db.execute.return_value.all.return_value = []
    mock_db.execute.return_value.scalar_one.return_value = 0
    r = await client.get("/analytics/funnel", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert "stages" in data
    assert isinstance(data["stages"], list)


async def test_funnel_with_job_id_filter(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    import uuid
    client, mock_db = client_and_db
    mock_db.execute.return_value.all.return_value = []
    mock_db.execute.return_value.scalar_one.return_value = 0
    job_id = uuid.uuid4()
    r = await client.get(f"/analytics/funnel?job_id={job_id}", headers=AUTH)
    assert r.status_code == 200


# ── GET /analytics/recruiter-activity ────────────────────────────────────────

async def test_recruiter_activity_admin_returns_200(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    mock_db.execute.return_value.all.return_value = []
    r = await client.get("/analytics/recruiter-activity", headers=ADMIN_AUTH)
    assert r.status_code == 200
    data = r.json()
    assert "recruiters" in data


async def test_recruiter_activity_non_admin_denied(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    _app = client._transport.app  # type: ignore[attr-defined]
    _app.dependency_overrides[require_admin] = lambda: (_ for _ in ()).throw(
        __import__("fastapi").HTTPException(status_code=403)
    )
    r = await client.get("/analytics/recruiter-activity", headers=AUTH)
    assert r.status_code == 403


# ── GET /analytics/sources ────────────────────────────────────────────────────

def _setup_sources(mock_db: AsyncMock, rows: list) -> None:
    """Set up mock DB to return source rows then absorb the business event add."""
    call_count = [0]
    results = [_rows(rows)]

    def _side_effect(*args: object, **kwargs: object) -> MagicMock:
        idx = min(call_count[0], len(results) - 1)
        call_count[0] += 1
        return results[idx]

    mock_db.execute = AsyncMock(side_effect=_side_effect)


async def test_sources_returns_correct_shape(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db

    row1 = MagicMock()
    row1.source = "linkedin"
    row1.cnt = 10
    row2 = MagicMock()
    row2.source = "referral"
    row2.cnt = 5
    row3 = MagicMock()
    row3.source = "unknown"
    row3.cnt = 2

    _setup_sources(mock_db, [row1, row2, row3])

    r = await client.get("/analytics/sources", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 3
    assert data["data"][0]["source"] == "linkedin"
    assert data["data"][0]["count"] == 10


async def test_sources_empty_returns_empty_list(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _setup_sources(mock_db, [])
    r = await client.get("/analytics/sources", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["data"] == []


async def test_sources_unauthenticated_returns_401(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    _app = client._transport.app  # type: ignore[attr-defined]
    _app.dependency_overrides.pop(get_current_user, None)
    r = await client.get("/analytics/sources")
    assert r.status_code == 401
