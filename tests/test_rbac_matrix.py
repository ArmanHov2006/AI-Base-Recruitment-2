"""
RBAC matrix tests — parametrized role × endpoint coverage.

Strategy:
  - Mini FastAPI app per test, no lifespan, isolated dependency_overrides.
  - get_current_user overridden to inject the target role's user.
  - get_db overridden with AsyncMock to avoid Postgres connections.
  - For ownership rows the DB mock is patched to return a seeded Job object.
  - Assert 403 vs non-403 only (404/422/2xx all mean "passed authz").
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.ai.router import router as ai_router
from app.analytics.router import router as analytics_router
from app.auth import get_current_user
from app.candidates.router import router as candidates_router
from app.database import get_db
from app.evaluations.router import router as evaluations_router
from app.jobs.router import router as jobs_router
from app.notes.router import router as notes_router
from app.parser.router import router as parser_router
from app.storage.router import router as storage_router
from app.users.models import UserRole
from tests.conftest import make_mock_db, make_user

# ── stable placeholder IDs ────────────────────────────────────────────────────

_CANDIDATE_ID = uuid.UUID("bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb")
_JOB_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
_FILE_ID = "550e8400-e29b-41d4-a716-446655440000"

# ── shared mini-app factory ────────────────────────────────────────────────────


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(ai_router)
    app.include_router(analytics_router)
    app.include_router(candidates_router)
    app.include_router(evaluations_router)
    app.include_router(jobs_router)
    app.include_router(notes_router)
    app.include_router(parser_router)
    app.include_router(storage_router)
    return app


def _override_user_and_db(app: FastAPI, role: UserRole) -> MagicMock:
    """Inject a mock user + mock DB into *app*. Returns the user mock."""
    user = make_user(role)
    mock_db = make_mock_db()

    async def user_override():
        return user

    async def db_override() -> AsyncGenerator:
        yield mock_db

    app.dependency_overrides[get_current_user] = user_override
    app.dependency_overrides[get_db] = db_override
    return user


# ── parametrize matrix ────────────────────────────────────────────────────────

# (role, method, path, expected_status_type)
# status_type "forbidden" → assert 403, "allowed" → assert != 403

_MATRIX: list[tuple[str, str, str, str]] = [
    # POST /ai/chat
    ("admin",      "POST", "/ai/chat",          "allowed"),
    ("recruiter",  "POST", "/ai/chat",          "allowed"),
    ("hr_manager", "POST", "/ai/chat",          "allowed"),
    ("viewer",     "POST", "/ai/chat",          "forbidden"),

    # GET /candidates/semantic-search
    ("admin",      "GET", "/candidates/semantic-search?q=python", "allowed"),
    ("recruiter",  "GET", "/candidates/semantic-search?q=python", "allowed"),
    ("hr_manager", "GET", "/candidates/semantic-search?q=python", "allowed"),
    ("viewer",     "GET", "/candidates/semantic-search?q=python", "forbidden"),

    # GET /evaluations/candidates/{id}/interview-questions
    ("admin",      "GET", f"/candidates/{_CANDIDATE_ID}/interview-questions?job_id={_JOB_ID}", "allowed"),
    ("recruiter",  "GET", f"/candidates/{_CANDIDATE_ID}/interview-questions?job_id={_JOB_ID}", "allowed"),
    ("hr_manager", "GET", f"/candidates/{_CANDIDATE_ID}/interview-questions?job_id={_JOB_ID}", "allowed"),
    ("viewer",     "GET", f"/candidates/{_CANDIDATE_ID}/interview-questions?job_id={_JOB_ID}", "forbidden"),

    # POST /parse
    ("admin",      "POST", "/parse",            "allowed"),
    ("recruiter",  "POST", "/parse",            "allowed"),
    ("hr_manager", "POST", "/parse",            "allowed"),
    ("viewer",     "POST", "/parse",            "forbidden"),

    # GET /files/{id}/download-url
    ("admin",      "GET", f"/files/{_FILE_ID}/download-url", "allowed"),
    ("recruiter",  "GET", f"/files/{_FILE_ID}/download-url", "allowed"),
    ("hr_manager", "GET", f"/files/{_FILE_ID}/download-url", "allowed"),
    ("viewer",     "GET", f"/files/{_FILE_ID}/download-url", "forbidden"),

    # GET /candidates/export.csv
    ("admin",      "GET", "/candidates/export.csv",  "allowed"),
    ("recruiter",  "GET", "/candidates/export.csv",  "allowed"),
    ("hr_manager", "GET", "/candidates/export.csv",  "allowed"),
    ("viewer",     "GET", "/candidates/export.csv",  "forbidden"),

    # GET /candidates/export.xlsx
    ("admin",      "GET", "/candidates/export.xlsx", "allowed"),
    ("recruiter",  "GET", "/candidates/export.xlsx", "allowed"),
    ("hr_manager", "GET", "/candidates/export.xlsx", "allowed"),
    ("viewer",     "GET", "/candidates/export.xlsx", "forbidden"),

    # GET /candidates/{id}/export.pdf
    ("admin",      "GET", f"/candidates/{_CANDIDATE_ID}/export.pdf", "allowed"),
    ("recruiter",  "GET", f"/candidates/{_CANDIDATE_ID}/export.pdf", "allowed"),
    ("hr_manager", "GET", f"/candidates/{_CANDIDATE_ID}/export.pdf", "allowed"),
    ("viewer",     "GET", f"/candidates/{_CANDIDATE_ID}/export.pdf", "forbidden"),

    # GET /analytics/export.pdf
    ("admin",      "GET", "/analytics/export.pdf", "allowed"),
    ("recruiter",  "GET", "/analytics/export.pdf", "allowed"),
    ("hr_manager", "GET", "/analytics/export.pdf", "allowed"),
    ("viewer",     "GET", "/analytics/export.pdf", "forbidden"),

    # GET /analytics/overview
    ("admin",      "GET", "/analytics/overview", "allowed"),
    ("recruiter",  "GET", "/analytics/overview", "allowed"),
    ("hr_manager", "GET", "/analytics/overview", "allowed"),
    ("viewer",     "GET", "/analytics/overview", "forbidden"),

    # POST /candidates/{id}/notes  — ALL roles allowed (notes use get_current_user)
    ("admin",      "POST", f"/candidates/{_CANDIDATE_ID}/notes", "allowed"),
    ("recruiter",  "POST", f"/candidates/{_CANDIDATE_ID}/notes", "allowed"),
    ("hr_manager", "POST", f"/candidates/{_CANDIDATE_ID}/notes", "allowed"),
    ("viewer",     "POST", f"/candidates/{_CANDIDATE_ID}/notes", "allowed"),

    # GET /candidates/{id}  — ALL roles allowed
    ("admin",      "GET", f"/candidates/{_CANDIDATE_ID}", "allowed"),
    ("recruiter",  "GET", f"/candidates/{_CANDIDATE_ID}", "allowed"),
    ("hr_manager", "GET", f"/candidates/{_CANDIDATE_ID}", "allowed"),
    ("viewer",     "GET", f"/candidates/{_CANDIDATE_ID}", "allowed"),

    # GET /jobs/{id}/leaderboard  — ALL roles allowed
    ("admin",      "GET", f"/jobs/{_JOB_ID}/leaderboard", "allowed"),
    ("recruiter",  "GET", f"/jobs/{_JOB_ID}/leaderboard", "allowed"),
    ("hr_manager", "GET", f"/jobs/{_JOB_ID}/leaderboard", "allowed"),
    ("viewer",     "GET", f"/jobs/{_JOB_ID}/leaderboard", "allowed"),
]

_ROLE_MAP = {
    "admin":      UserRole.ADMIN,
    "recruiter":  UserRole.RECRUITER,
    "hr_manager": UserRole.HR_MANAGER,
    "viewer":     UserRole.VIEWER,
}

# Request bodies for methods that need them
_BODIES: dict[tuple[str, str], dict] = {
    ("POST", "/ai/chat"):  {"candidate_id": str(_CANDIDATE_ID), "message": "Tell me about this candidate"},
    ("POST", "/parse"):    {"file_id": _FILE_ID},
    ("POST", f"/candidates/{_CANDIDATE_ID}/notes"): {"text": "Test note"},
}


def _body_for(method: str, path: str) -> dict | None:
    # Strip query string for key lookup
    clean = path.split("?")[0]
    return _BODIES.get((method, clean))


@pytest.mark.parametrize(
    "role_name,method,path,expected",
    [(r, m, p, e) for r, m, p, e in _MATRIX],
    ids=[f"{r}-{m}-{p.split('?')[0].replace('/', '_').strip('_')}" for r, m, p, _ in _MATRIX],
)
async def test_rbac_matrix(
    role_name: str,
    method: str,
    path: str,
    expected: str,
) -> None:
    """Assert 403 vs non-403 for each role×endpoint combination."""
    app = _build_app()
    role = _ROLE_MAP[role_name]
    _override_user_and_db(app, role)

    body = _body_for(method, path)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.request(method, path, json=body)

    if expected == "forbidden":
        assert resp.status_code == 403, (
            f"{role_name} {method} {path}: expected 403, got {resp.status_code} — {resp.text[:200]}"
        )
    else:
        assert resp.status_code != 403, (
            f"{role_name} {method} {path}: expected non-403, got {resp.status_code} — {resp.text[:200]}"
        )


# ── ownership rows: PATCH /jobs/{job_id} ─────────────────────────────────────


def _make_job_mock(creator_id: uuid.UUID) -> MagicMock:
    """Return a mock Job object whose .creator_id matches creator_id."""
    from app.jobs.models import Job

    job = MagicMock(spec=Job)
    job.id = _JOB_ID
    job.creator_id = creator_id
    job.deleted_at = None
    job.title = "Test Job"
    return job


async def test_patch_job_hr_manager_not_owner_gets_403() -> None:
    """HR_MANAGER who did NOT create the job must get 403."""
    app = _build_app()

    hr_manager_b = make_user(UserRole.HR_MANAGER)
    hr_manager_b.id = uuid.UUID("cccccccc-cccc-4ccc-cccc-cccccccccccc")

    # The job was created by a *different* HR manager (hr_manager_A)
    hr_manager_a_id = uuid.UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
    job_mock = _make_job_mock(creator_id=hr_manager_a_id)

    mock_db = make_mock_db()
    # db.get(Job, job_id) is used in require_job_owner_or_elevated
    mock_db.get = AsyncMock(return_value=job_mock)

    async def user_override():
        return hr_manager_b

    async def db_override() -> AsyncGenerator:
        yield mock_db

    app.dependency_overrides[get_current_user] = user_override
    app.dependency_overrides[get_db] = db_override

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.patch(f"/jobs/{_JOB_ID}", json={"title": "Updated"})

    assert resp.status_code == 403, (
        f"HR_MANAGER (non-owner) PATCH /jobs/{{id}}: expected 403, got {resp.status_code} — {resp.text[:200]}"
    )


async def test_patch_job_hr_manager_owner_gets_non_403() -> None:
    """HR_MANAGER who created the job must pass authz (non-403)."""
    app = _build_app()

    hr_manager_a = make_user(UserRole.HR_MANAGER)
    hr_manager_a.id = uuid.UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")

    # The job was created by this same HR manager
    job_mock = _make_job_mock(creator_id=hr_manager_a.id)

    mock_db = make_mock_db()
    mock_db.get = AsyncMock(return_value=job_mock)

    # After authz passes, update_job calls db.execute() to SELECT the job again.
    # We return the same job mock so it doesn't 404.
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = job_mock
    mock_db.execute = AsyncMock(return_value=exec_result)

    async def user_override():
        return hr_manager_a

    async def db_override() -> AsyncGenerator:
        yield mock_db

    app.dependency_overrides[get_current_user] = user_override
    app.dependency_overrides[get_db] = db_override

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.patch(f"/jobs/{_JOB_ID}", json={"title": "Updated"})

    assert resp.status_code != 403, (
        f"HR_MANAGER (owner) PATCH /jobs/{{id}}: expected non-403, got {resp.status_code} — {resp.text[:200]}"
    )


async def test_patch_job_viewer_gets_403() -> None:
    """VIEWER must get 403 on PATCH /jobs/{id} regardless of ownership."""
    app = _build_app()

    viewer = make_user(UserRole.VIEWER)
    mock_db = make_mock_db()

    async def user_override():
        return viewer

    async def db_override() -> AsyncGenerator:
        yield mock_db

    app.dependency_overrides[get_current_user] = user_override
    app.dependency_overrides[get_db] = db_override

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.patch(f"/jobs/{_JOB_ID}", json={"title": "Updated"})

    assert resp.status_code == 403, (
        f"VIEWER PATCH /jobs/{{id}}: expected 403, got {resp.status_code} — {resp.text[:200]}"
    )


async def test_patch_job_admin_gets_non_403() -> None:
    """ADMIN must pass authz on PATCH /jobs/{id} regardless of ownership."""
    app = _build_app()

    admin = make_user(UserRole.ADMIN)
    job_mock = _make_job_mock(creator_id=uuid.uuid4())  # owned by someone else

    mock_db = make_mock_db()
    mock_db.get = AsyncMock(return_value=job_mock)

    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = job_mock
    mock_db.execute = AsyncMock(return_value=exec_result)

    async def user_override():
        return admin

    async def db_override() -> AsyncGenerator:
        yield mock_db

    app.dependency_overrides[get_current_user] = user_override
    app.dependency_overrides[get_db] = db_override

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.patch(f"/jobs/{_JOB_ID}", json={"title": "Updated"})

    assert resp.status_code != 403, (
        f"ADMIN PATCH /jobs/{{id}}: expected non-403, got {resp.status_code} — {resp.text[:200]}"
    )


async def test_patch_job_recruiter_gets_non_403() -> None:
    """RECRUITER must pass authz on PATCH /jobs/{id} regardless of ownership."""
    app = _build_app()

    recruiter = make_user(UserRole.RECRUITER)
    job_mock = _make_job_mock(creator_id=uuid.uuid4())

    mock_db = make_mock_db()
    mock_db.get = AsyncMock(return_value=job_mock)

    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = job_mock
    mock_db.execute = AsyncMock(return_value=exec_result)

    async def user_override():
        return recruiter

    async def db_override() -> AsyncGenerator:
        yield mock_db

    app.dependency_overrides[get_current_user] = user_override
    app.dependency_overrides[get_db] = db_override

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.patch(f"/jobs/{_JOB_ID}", json={"title": "Updated"})

    assert resp.status_code != 403, (
        f"RECRUITER PATCH /jobs/{{id}}: expected non-403, got {resp.status_code} — {resp.text[:200]}"
    )
