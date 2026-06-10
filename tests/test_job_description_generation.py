"""Tests for F7: POST /jobs/generate-description endpoint."""
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.jobs.router import router as jobs_router
from app.llm.base import LLMParseError, LLMTimeoutError
from app.users.models import UserRole
from tests.conftest import make_mock_db, make_user

_GENERATE_URL = "/jobs/generate-description"

_VALID_BODY = {
    "title": "Senior Backend Engineer",
    "seniority": "senior",
    "required_skills": ["Python", "FastAPI", "PostgreSQL"],
    "notes": "Focus on financial systems experience",
}

_DRAFT_RESPONSE = {
    "summary": "We are seeking a Senior Backend Engineer to build robust financial APIs.",
    "responsibilities": [
        "Design and maintain RESTful APIs using FastAPI",
        "Optimize PostgreSQL queries for high-throughput workloads",
        "Collaborate with the product team on feature specifications",
        "Conduct code reviews and mentor junior engineers",
    ],
    "requirements": [
        "5+ years of Python development experience",
        "Strong knowledge of FastAPI and SQLAlchemy",
        "Experience with PostgreSQL and async patterns",
        "Familiarity with financial systems is a plus",
    ],
}


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _build_app(mock_db: AsyncMock, role: UserRole = UserRole.RECRUITER) -> FastAPI:
    app = FastAPI()
    app.include_router(jobs_router)

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    app.dependency_overrides[get_db] = db_override
    fake_user = make_user(role)
    app.dependency_overrides[get_current_user] = lambda: fake_user
    # Override all require_role(...) variants to return the fake user
    for dep in list(app.dependency_overrides):
        pass
    # Override via function — require_role returns a callable; we patch
    # the dependency at the router level by overriding get_current_user
    # which is called inside require_role's inner _dep function.
    return app


# ---------------------------------------------------------------------------
# Test 1 — happy path: LLM returns valid draft
# ---------------------------------------------------------------------------


async def test_generate_description_success() -> None:
    mock_db = make_mock_db()

    with patch("app.jobs.router._llm") as mock_llm:
        mock_llm.generate_job_description = AsyncMock(return_value=_DRAFT_RESPONSE)

        app = _build_app(mock_db)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(_GENERATE_URL, json=_VALID_BODY)

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"] == _DRAFT_RESPONSE["summary"]
    assert data["responsibilities"] == _DRAFT_RESPONSE["responsibilities"]
    assert data["requirements"] == _DRAFT_RESPONSE["requirements"]


# ---------------------------------------------------------------------------
# Test 2 — LLM timeout → 502
# ---------------------------------------------------------------------------


async def test_generate_description_llm_timeout_returns_502() -> None:
    mock_db = make_mock_db()

    with patch("app.jobs.router._llm") as mock_llm:
        mock_llm.generate_job_description = AsyncMock(
            side_effect=LLMTimeoutError("LLM timed out")
        )

        app = _build_app(mock_db)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(_GENERATE_URL, json=_VALID_BODY)

    assert r.status_code == 502
    assert "timed out" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 3 — LLM parse error → 502
# ---------------------------------------------------------------------------


async def test_generate_description_llm_parse_error_returns_502() -> None:
    mock_db = make_mock_db()

    with patch("app.jobs.router._llm") as mock_llm:
        mock_llm.generate_job_description = AsyncMock(
            side_effect=LLMParseError("LLM returned invalid data")
        )

        app = _build_app(mock_db)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(_GENERATE_URL, json=_VALID_BODY)

    assert r.status_code == 502


# ---------------------------------------------------------------------------
# Test 4 — missing required fields → 422
# ---------------------------------------------------------------------------


async def test_generate_description_missing_title_returns_422() -> None:
    mock_db = make_mock_db()

    with patch("app.jobs.router._llm"):
        app = _build_app(mock_db)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Missing both title and seniority
            r = await client.post(_GENERATE_URL, json={})

    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Test 5 — business event is recorded on success
# ---------------------------------------------------------------------------


async def test_generate_description_records_business_event() -> None:
    mock_db = make_mock_db()

    with patch("app.jobs.router._llm") as mock_llm, \
         patch("app.jobs.router.record") as mock_record:
        mock_llm.generate_job_description = AsyncMock(return_value=_DRAFT_RESPONSE)
        mock_record.return_value = None  # record is async; make it awaitable
        mock_record = AsyncMock(return_value=None)

        # Re-patch correctly
        with patch("app.jobs.router.record", new=mock_record):
            app = _build_app(mock_db)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(_GENERATE_URL, json=_VALID_BODY)

    assert r.status_code == 200
    mock_record.assert_called_once()
    call_kwargs = mock_record.call_args.kwargs
    assert call_kwargs["action"].value == "job_description.generated"
    assert call_kwargs["resource_type"] == "job_description_draft"
    assert call_kwargs["meta"]["title"] == _VALID_BODY["title"]


# ---------------------------------------------------------------------------
# Test 6 — optional fields (no skills, no notes) are accepted
# ---------------------------------------------------------------------------


async def test_generate_description_minimal_body() -> None:
    mock_db = make_mock_db()

    with patch("app.jobs.router._llm") as mock_llm:
        mock_llm.generate_job_description = AsyncMock(return_value=_DRAFT_RESPONSE)

        app = _build_app(mock_db)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                _GENERATE_URL,
                json={"title": "Software Engineer", "seniority": "mid"},
            )

    assert r.status_code == 200
    # Verify LLM was called with empty skills and no notes
    call_kwargs = mock_llm.generate_job_description.call_args.kwargs
    assert call_kwargs["skills"] == []
    assert call_kwargs["notes"] is None


# ---------------------------------------------------------------------------
# Test 7 — VIEWER role is blocked (403)
# ---------------------------------------------------------------------------


async def test_generate_description_viewer_forbidden() -> None:
    mock_db = make_mock_db()

    # We need the real require_role check to fire — override only get_current_user
    # with a VIEWER, leave require_role wired up.
    with patch("app.jobs.router._llm"):

        app = FastAPI()
        app.include_router(jobs_router)

        async def db_override() -> AsyncGenerator[AsyncSession, None]:
            yield mock_db  # type: ignore[misc]

        viewer = make_user(UserRole.VIEWER)

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = lambda: viewer

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(_GENERATE_URL, json=_VALID_BODY)

    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Test 8 — rate limit decorator is applied (check it exists on the route)
# ---------------------------------------------------------------------------


def test_generate_description_route_has_rate_limit_decorator() -> None:
    """Verify the endpoint has the slowapi rate-limit marker.

    The limiter wraps the function using functools.wraps, which sets __wrapped__
    on the decorated function. This confirms the decorator was applied.
    """
    from app.jobs.router import generate_job_description as _fn

    # slowapi uses functools.wraps → __wrapped__ is set on the decorated function
    assert hasattr(_fn, "__wrapped__"), (
        "Rate limit decorator (@limiter.limit) not applied to generate_job_description"
    )
