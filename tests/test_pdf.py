import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.router import router as analytics_router
from app.analytics.schemas import FunnelResponse, FunnelStage, OverviewResponse, SkillCount
from app.auth import get_current_user
from app.candidates.router import router as candidates_router
from app.database import get_db
from app.pdf.builders import analytics_pdf, candidate_pdf
from app.users.models import UserRole
from tests.conftest import make_user

_CAND_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440099")


def _candidate() -> MagicMock:
    c = MagicMock()
    c.id = _CAND_ID
    c.name = "Jane Doe"
    c.email = "jane@example.com"
    c.phone = "+37411223344"
    c.location = "Yerevan"
    c.seniority = "senior"
    c.years_experience = 7.5
    c.desired_position = "Backend Engineer"
    c.desired_salary = 6000
    c.linkedin_url = "https://linkedin.com/in/jane"
    c.github_url = "https://github.com/jane"
    c.summary = "Pragmatic backend engineer with a focus on Python services."
    c.skills = ["Python (expert)", "FastAPI (proficient)", "PostgreSQL (proficient)"]
    c.certifications = ["AWS Solutions Architect"]
    c.languages = ["Armenian", "English", "Russian"]
    c.work_experiences = [
        {
            "role": "Senior Engineer",
            "company": "Acme",
            "start_date": "2021-03",
            "end_date": None,
            "description": "Led the payments platform.",
            "achievements": ["Cut latency 40%", "Mentored 3 juniors"],
        }
    ]
    c.education = [{"institution": "YSU", "degree": "BSc CS", "year": 2016}]
    c.created_at = datetime.now(timezone.utc)
    c.deleted_at = None
    return c


# ── Builder unit tests ────────────────────────────────────────────────────────


def test_candidate_pdf_builder_returns_pdf_bytes() -> None:
    pdf = candidate_pdf(_candidate())
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000  # non-trivial document


def test_candidate_pdf_handles_empty_candidate() -> None:
    empty = MagicMock()
    for attr in (
        "name", "email", "phone", "location", "seniority", "summary",
        "desired_position", "linkedin_url", "github_url",
    ):
        setattr(empty, attr, None)
    empty.years_experience = None
    empty.desired_salary = None
    empty.skills = []
    empty.certifications = []
    empty.languages = []
    empty.work_experiences = []
    empty.education = []
    pdf = candidate_pdf(empty)
    assert pdf[:4] == b"%PDF"


def test_analytics_pdf_builder_returns_pdf_bytes() -> None:
    overview = OverviewResponse(
        total_candidates=12,
        active_candidates=12,
        total_jobs=3,
        total_applications=40,
        applications_by_status={"applied": 30, "hired": 2},
        top_skills=[SkillCount(skill="Python", count=8), SkillCount(skill="SQL", count=5)],
    )
    funnel = FunnelResponse(
        stages=[
            FunnelStage(stage="applied", count=40, conversion_rate=None),
            FunnelStage(stage="hired", count=2, conversion_rate=5.0),
        ]
    )
    pdf = analytics_pdf(overview, funnel)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


# ── Endpoint integration tests ────────────────────────────────────────────────


def _result(*, scalar=None, scalar_one=None, items=None, one=None) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalar_one.return_value = scalar_one
    r.all.return_value = items or []
    if one is not None:
        r.one.return_value = one
    return r


@pytest.fixture
async def candidates_client() -> AsyncGenerator[tuple[AsyncClient, AsyncMock], None]:
    mock_db = AsyncMock(spec=AsyncSession)
    app = FastAPI()
    app.include_router(candidates_router)

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.RECRUITER)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_db


async def test_candidate_export_pdf_returns_pdf(
    candidates_client: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = candidates_client
    mock_db.execute = AsyncMock(return_value=_result(scalar=_candidate()))
    r = await client.get(f"/candidates/{_CAND_ID}/export.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert f"candidate_{_CAND_ID}.pdf" in r.headers["content-disposition"]
    assert r.content[:4] == b"%PDF"


async def test_candidate_export_pdf_404(
    candidates_client: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = candidates_client
    mock_db.execute = AsyncMock(return_value=_result(scalar=None))
    r = await client.get(f"/candidates/{_CAND_ID}/export.pdf")
    assert r.status_code == 404


async def test_analytics_export_pdf_returns_pdf() -> None:
    mock_db = AsyncMock(spec=AsyncSession)
    # get_overview: count×3 (scalar_one), status rows, skill rows
    # get_time_to_hire: overall row (one), per-job rows (all)
    status_row = MagicMock(status="applied", cnt=10)
    skill_row = MagicMock(skill="Python", cnt=4)
    overall_row = MagicMock()
    overall_row.avg_days = 5.0
    mock_db.execute = AsyncMock(
        side_effect=[
            _result(scalar_one=5),   # total_candidates
            _result(scalar_one=2),   # total_jobs
            _result(scalar_one=10),  # total_applications
            _result(scalar_one=3),   # active_candidates
            _result(items=[status_row]),
            _result(items=[skill_row]),
            _result(one=overall_row),
            _result(items=[]),
        ]
    )
    app = FastAPI()
    app.include_router(analytics_router)

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.RECRUITER)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/analytics/export.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "analytics.pdf" in r.headers["content-disposition"]
    assert r.content[:4] == b"%PDF"
