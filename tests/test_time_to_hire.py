import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.router import router as analytics_router
from app.auth import get_current_user
from app.database import get_db
from app.users.models import UserRole
from tests.conftest import make_user

_JOB_A = uuid.UUID("550e8400-e29b-41d4-a716-4466554400a1")
_JOB_B = uuid.UUID("550e8400-e29b-41d4-a716-4466554400b2")
_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _exec_result(rows: list) -> MagicMock:
    r = MagicMock()
    r.all.return_value = rows
    return r


def _hire_row(job_id: uuid.UUID, applied: datetime, hired: datetime) -> MagicMock:
    m = MagicMock()
    m.job_id = job_id
    m.applied_at = applied
    m.hired_at = hired
    return m


def _title_row(job_id: uuid.UUID, title: str) -> MagicMock:
    m = MagicMock()
    m.id = job_id
    m.title = title
    return m


def _make_client(execute_results: list) -> tuple[FastAPI, AsyncMock]:
    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.execute = AsyncMock(side_effect=execute_results)

    app = FastAPI()
    app.include_router(analytics_router)

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.RECRUITER)
    return app, mock_db


@pytest.fixture
async def populated_client() -> AsyncGenerator[AsyncClient, None]:
    hire_rows = [
        _hire_row(_JOB_A, _T0, _T0 + timedelta(days=2)),
        _hire_row(_JOB_A, _T0, _T0 + timedelta(days=4)),
        _hire_row(_JOB_B, _T0, _T0 + timedelta(days=10)),
    ]
    title_rows = [_title_row(_JOB_A, "Backend Engineer"), _title_row(_JOB_B, "Data Scientist")]
    app, _ = _make_client([_exec_result(hire_rows), _exec_result(title_rows)])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_time_to_hire_aggregates_overall_and_per_job(
    populated_client: AsyncClient,
) -> None:
    r = await populated_client.get("/analytics/time-to-hire")
    assert r.status_code == 200
    data = r.json()

    assert data["total_hired"] == 3
    # (2 + 4 + 10) / 3 = 5.333 → 5.3
    assert data["overall_avg_days"] == 5.3

    per_job = {j["job_title"]: j for j in data["per_job"]}
    assert per_job["Backend Engineer"]["hired_count"] == 2
    assert per_job["Backend Engineer"]["avg_days_to_hire"] == 3.0
    assert per_job["Data Scientist"]["hired_count"] == 1
    assert per_job["Data Scientist"]["avg_days_to_hire"] == 10.0


async def test_time_to_hire_empty_returns_nulls() -> None:
    app, _ = _make_client([_exec_result([])])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/analytics/time-to-hire")
    assert r.status_code == 200
    data = r.json()
    assert data["total_hired"] == 0
    assert data["overall_avg_days"] is None
    assert data["per_job"] == []


async def test_time_to_hire_clamps_negative_to_zero() -> None:
    # hired_at before applied_at (clock skew) must not produce negative days.
    hire_rows = [_hire_row(_JOB_A, _T0, _T0 - timedelta(days=3))]
    title_rows = [_title_row(_JOB_A, "Backend Engineer")]
    app, _ = _make_client([_exec_result(hire_rows), _exec_result(title_rows)])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/analytics/time-to-hire")
    assert r.status_code == 200
    data = r.json()
    assert data["overall_avg_days"] == 0.0
    assert data["per_job"][0]["avg_days_to_hire"] == 0.0
