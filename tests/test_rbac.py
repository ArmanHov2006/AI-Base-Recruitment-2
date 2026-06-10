"""
RBAC test suite.

Three groups:
  401 — real JWT validation path (get_current_user NOT overridden)
  403 — VIEWER role blocked from require_write endpoints
  non-403 — write-allowed roles (ADMIN/RECRUITER/HR_MANAGER) pass the gate

Strategy:
  - Fresh mini FastAPI app per test (no lifespan, isolated dependency_overrides)
  - get_current_user overridden for role tests; real JWT validation for 401 tests
  - get_db overridden with AsyncMock to avoid Postgres connections
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.applications.router import router as applications_router
from app.auth import get_current_user
from app.candidates.router import router as candidates_router
from app.comparisons.router import router as comparisons_router
from app.database import get_db
from app.jobs.router import router as jobs_router
from app.parser.router import router as parser_router
from app.parser.schemas import CandidateData
from app.storage.router import router as storage_router
from app.users.models import UserRole
from tests.conftest import (
    make_bad_sig_token,
    make_expired_token,
    make_mock_db,
    make_user,
    make_valid_token,
)

# ── fixed IDs used across all tests ───────────────────────────────────────────

_JOB_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
_CANDIDATE_ID = uuid.UUID("bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb")
_CANDIDATE_ID_2 = uuid.UUID("cccccccc-cccc-4ccc-cccc-cccccccccccc")
_APP_ID = uuid.UUID("dddddddd-dddd-4ddd-dddd-dddddddddddd")
_COMPARISON_ID = uuid.UUID("eeeeeeee-eeee-4eee-eeee-eeeeeeeeeeee")
_FILE_ID = "550e8400-e29b-41d4-a716-446655440000"

PDF_BYTES = b"%PDF-1.4 1 0 obj<</Type /Catalog>>endobj\n%%EOF"

# ── endpoint lists ─────────────────────────────────────────────────────────────

# All require_write-guarded endpoints (multipart upload tested separately)
_WRITE_ENDPOINTS: list[tuple[str, str, dict | None]] = [
    ("POST",   "/jobs",                                             {"title": "Eng"}),
    ("DELETE", f"/jobs/{_JOB_ID}",                                  None),
    ("POST",   f"/jobs/{_JOB_ID}/applications",                     {"file_id": _FILE_ID}),
    ("PATCH",  f"/jobs/{_JOB_ID}/applications/{_APP_ID}",           {"status": "screening"}),
    ("DELETE", f"/jobs/{_JOB_ID}/applications/{_APP_ID}",           None),
    ("POST",   "/candidates",                                       {"file_id": _FILE_ID}),
    ("DELETE", f"/candidates/{_CANDIDATE_ID}",                      None),
    (
        "POST",
        "/comparisons",
        {
            "job_id": str(_JOB_ID),
            "candidate_ids": [str(_CANDIDATE_ID), str(_CANDIDATE_ID_2)],
        },
    ),
    ("POST",   f"/comparisons/{_COMPARISON_ID}/analyze",             None),
]

# All get_current_user-guarded (read-only) endpoints
_READ_ENDPOINTS: list[tuple[str, str, dict | None]] = [
    ("GET", "/jobs",                                        None),
    ("GET", f"/jobs/{_JOB_ID}",                            None),
    ("GET", f"/jobs/{_JOB_ID}/leaderboard",                None),
    ("GET", f"/jobs/{_JOB_ID}/applications",               None),
    ("GET", f"/jobs/{_JOB_ID}/applications/{_APP_ID}",     None),
    ("GET", "/candidates",                                 None),
    ("GET", f"/candidates/{_CANDIDATE_ID}",                None),
    ("GET", "/comparisons",                                None),
    ("GET", f"/comparisons/{_COMPARISON_ID}",              None),
]

_WRITE_ROLES = [UserRole.ADMIN, UserRole.RECRUITER, UserRole.HR_MANAGER]


# ── shared fixture ─────────────────────────────────────────────────────────────

@pytest.fixture
async def rbac_client() -> AsyncGenerator[tuple[AsyncClient, FastAPI], None]:
    """Fresh mini-app per test — no lifespan, empty dependency_overrides."""
    _app = FastAPI()
    _app.include_router(candidates_router)
    _app.include_router(jobs_router)
    _app.include_router(applications_router)
    _app.include_router(comparisons_router)
    _app.include_router(storage_router)
    _app.include_router(parser_router)

    async with AsyncClient(
        transport=ASGITransport(app=_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c, _app


# ── 401: real JWT validation ───────────────────────────────────────────────────

class TestUnauthenticated:
    """
    get_current_user is NOT overridden — exercises real JWT decode path.
    get_db IS overridden to avoid Postgres connections.
    """

    @pytest.fixture(autouse=True)
    async def setup_db(
        self, rbac_client: tuple[AsyncClient, FastAPI]
    ) -> AsyncGenerator[None, None]:
        _, app = rbac_client
        mock_db = make_mock_db()

        async def db_override() -> AsyncGenerator:
            yield mock_db

        app.dependency_overrides[get_db] = db_override
        yield

    @pytest.mark.parametrize(
        "method,path,body",
        _WRITE_ENDPOINTS
        + _READ_ENDPOINTS
        + [("POST", "/parse", {"file_id": _FILE_ID})],
    )
    async def test_no_token_returns_401(
        self,
        rbac_client: tuple[AsyncClient, FastAPI],
        method: str,
        path: str,
        body: dict | None,
    ) -> None:
        client, _ = rbac_client
        r = await client.request(method, path, json=body)
        assert r.status_code == 401, (
            f"{method} {path}: expected 401 (no token), got {r.status_code}"
        )

    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("POST",   "/jobs",                  {"title": "Eng"}),
            ("GET",    "/jobs",                  None),
            ("DELETE", f"/candidates/{_CANDIDATE_ID}", None),
            (
                "POST",
                "/comparisons",
                {
                    "job_id": str(_JOB_ID),
                    "candidate_ids": [str(_CANDIDATE_ID), str(_CANDIDATE_ID_2)],
                },
            ),
            ("GET",  "/comparisons", None),
            ("POST", "/parse",       {"file_id": _FILE_ID}),
        ],
    )
    async def test_bad_token_returns_401(
        self,
        rbac_client: tuple[AsyncClient, FastAPI],
        method: str,
        path: str,
        body: dict | None,
    ) -> None:
        client, _ = rbac_client
        r = await client.request(
            method, path,
            headers={"Authorization": "Bearer not.a.real.jwt"},
            json=body,
        )
        assert r.status_code == 401, (
            f"{method} {path}: expected 401 (bad token), got {r.status_code}"
        )

    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("POST", "/jobs",  {"title": "Eng"}),
            ("GET",  "/jobs",  None),
            ("POST", "/parse", {"file_id": _FILE_ID}),
        ],
    )
    async def test_expired_token_returns_401(
        self,
        rbac_client: tuple[AsyncClient, FastAPI],
        method: str,
        path: str,
        body: dict | None,
    ) -> None:
        client, _ = rbac_client
        token = make_expired_token(UserRole.ADMIN)
        r = await client.request(
            method, path,
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        assert r.status_code == 401, (
            f"{method} {path}: expected 401 (expired token), got {r.status_code}"
        )

    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("POST", "/jobs", {"title": "Eng"}),
            ("GET",  "/jobs", None),
        ],
    )
    async def test_bad_signature_returns_401(
        self,
        rbac_client: tuple[AsyncClient, FastAPI],
        method: str,
        path: str,
        body: dict | None,
    ) -> None:
        client, _ = rbac_client
        token = make_bad_sig_token(UserRole.ADMIN)
        r = await client.request(
            method, path,
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        assert r.status_code == 401, (
            f"{method} {path}: expected 401 (bad signature), got {r.status_code}"
        )

    async def test_valid_jwt_user_not_in_db_returns_401(
        self,
        rbac_client: tuple[AsyncClient, FastAPI],
    ) -> None:
        """Valid JWT structure, but DB returns no user → 401."""
        # make_mock_db already returns scalar_one_or_none()=None by default
        client, _ = rbac_client
        token = make_valid_token(UserRole.ADMIN)
        r = await client.get("/jobs", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401

    async def test_valid_jwt_inactive_user_returns_401(
        self,
        rbac_client: tuple[AsyncClient, FastAPI],
    ) -> None:
        """Valid JWT, user found in DB but is_active=False → 401."""
        _, app = rbac_client
        inactive = make_user(UserRole.ADMIN)
        inactive.is_active = False

        inactive_result = MagicMock()
        inactive_result.scalar_one_or_none.return_value = inactive
        inactive_db = make_mock_db()
        inactive_db.execute = AsyncMock(return_value=inactive_result)

        async def db_override() -> AsyncGenerator:
            yield inactive_db

        app.dependency_overrides[get_db] = db_override

        client, _ = rbac_client
        token = make_valid_token(UserRole.ADMIN)
        r = await client.get("/jobs", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401


# ── 403: VIEWER blocked from all require_write endpoints ─────────────────────

class TestViewerForbidden:
    """VIEWER role must get 403 on every require_write-guarded endpoint."""

    @pytest.fixture(autouse=True)
    async def inject_viewer(
        self, rbac_client: tuple[AsyncClient, FastAPI]
    ) -> AsyncGenerator[None, None]:
        _, app = rbac_client
        viewer = make_user(UserRole.VIEWER)

        async def override():
            return viewer

        app.dependency_overrides[get_current_user] = override
        yield

    @pytest.mark.parametrize("method,path,body", _WRITE_ENDPOINTS)
    async def test_viewer_gets_403_on_write_endpoint(
        self,
        rbac_client: tuple[AsyncClient, FastAPI],
        method: str,
        path: str,
        body: dict | None,
    ) -> None:
        client, _ = rbac_client
        r = await client.request(method, path, json=body)
        assert r.status_code == 403, (
            f"VIEWER on {method} {path}: expected 403, got {r.status_code}"
        )

    async def test_viewer_gets_403_on_upload(
        self, rbac_client: tuple[AsyncClient, FastAPI]
    ) -> None:
        client, _ = rbac_client
        r = await client.post(
            "/files/upload",
            files={"file": ("resume.pdf", PDF_BYTES, "application/pdf")},
        )
        assert r.status_code == 403


# ── read access: VIEWER allowed on get_current_user endpoints ─────────────────

class TestViewerCanRead:
    """VIEWER must not receive 403 on any read-only (get_current_user) endpoint."""

    @pytest.fixture(autouse=True)
    async def setup(
        self, rbac_client: tuple[AsyncClient, FastAPI]
    ) -> AsyncGenerator[None, None]:
        _, app = rbac_client
        viewer = make_user(UserRole.VIEWER)
        mock_db = make_mock_db()

        async def user_override():
            return viewer

        async def db_override() -> AsyncGenerator:
            yield mock_db

        app.dependency_overrides[get_current_user] = user_override
        app.dependency_overrides[get_db] = db_override
        yield

    @pytest.mark.parametrize("method,path,body", _READ_ENDPOINTS)
    async def test_viewer_not_forbidden_on_read_endpoint(
        self,
        rbac_client: tuple[AsyncClient, FastAPI],
        method: str,
        path: str,
        body: dict | None,
    ) -> None:
        client, _ = rbac_client
        r = await client.request(method, path, json=body)
        assert r.status_code != 403, (
            f"VIEWER on {method} {path} got 403 — should have read access"
        )
        # 200 (empty list) or 404 (resource not in mock) are both acceptable
        assert r.status_code in (200, 404, 422), (
            f"Unexpected {r.status_code} for VIEWER on {method} {path}: {r.text[:200]}"
        )


# ── non-403: write roles pass the RBAC gate ───────────────────────────────────

class TestWriteRolesNotForbidden:
    """
    ADMIN, RECRUITER, HR_MANAGER must not receive 403 on require_write endpoints.

    DB mock returns scalar_one_or_none()=None by default, so most endpoints
    return 404 (resource not found) or 500 (serialization of ORM id=None).
    Both are acceptable — we only assert the RBAC layer did NOT block the request.
    """

    def _setup_overrides(self, app: FastAPI, role: UserRole) -> None:
        user = make_user(role)
        mock_db = make_mock_db()

        async def user_override():
            return user

        async def db_override() -> AsyncGenerator:
            yield mock_db

        app.dependency_overrides[get_current_user] = user_override
        app.dependency_overrides[get_db] = db_override

    @pytest.mark.parametrize("role", _WRITE_ROLES)
    async def test_create_job_not_forbidden(
        self, rbac_client: tuple[AsyncClient, FastAPI], role: UserRole
    ) -> None:
        client, app = rbac_client
        self._setup_overrides(app, role)
        r = await client.post("/jobs", json={"title": "Software Engineer"})
        assert r.status_code != 403, f"{role.value} got 403 on POST /jobs"

    @pytest.mark.parametrize("role", _WRITE_ROLES)
    async def test_delete_job_not_forbidden(
        self, rbac_client: tuple[AsyncClient, FastAPI], role: UserRole
    ) -> None:
        client, app = rbac_client
        self._setup_overrides(app, role)
        r = await client.delete(f"/jobs/{_JOB_ID}")
        assert r.status_code != 403, f"{role.value} got 403 on DELETE /jobs/{{id}}"

    @pytest.mark.parametrize("role", _WRITE_ROLES)
    async def test_create_application_not_forbidden(
        self, rbac_client: tuple[AsyncClient, FastAPI], role: UserRole
    ) -> None:
        """_load_job returns None → 404; RBAC gate already passed."""
        client, app = rbac_client
        self._setup_overrides(app, role)
        r = await client.post(
            f"/jobs/{_JOB_ID}/applications", json={"file_id": _FILE_ID}
        )
        assert r.status_code != 403, f"{role.value} got 403 on POST application"

    @pytest.mark.parametrize("role", _WRITE_ROLES)
    async def test_patch_application_not_forbidden(
        self, rbac_client: tuple[AsyncClient, FastAPI], role: UserRole
    ) -> None:
        """_load_application returns None → 404; RBAC gate already passed."""
        client, app = rbac_client
        self._setup_overrides(app, role)
        r = await client.patch(
            f"/jobs/{_JOB_ID}/applications/{_APP_ID}",
            json={"status": "screening"},
        )
        assert r.status_code != 403, f"{role.value} got 403 on PATCH application"

    @pytest.mark.parametrize("role", _WRITE_ROLES)
    async def test_delete_application_not_forbidden(
        self, rbac_client: tuple[AsyncClient, FastAPI], role: UserRole
    ) -> None:
        client, app = rbac_client
        self._setup_overrides(app, role)
        r = await client.delete(f"/jobs/{_JOB_ID}/applications/{_APP_ID}")
        assert r.status_code != 403, f"{role.value} got 403 on DELETE application"

    @pytest.mark.parametrize("role", _WRITE_ROLES)
    async def test_create_candidate_not_forbidden(
        self, rbac_client: tuple[AsyncClient, FastAPI], role: UserRole
    ) -> None:
        """No email in body → duplicate check skipped entirely."""
        client, app = rbac_client
        self._setup_overrides(app, role)
        r = await client.post("/candidates", json={"file_id": _FILE_ID})
        assert r.status_code != 403, f"{role.value} got 403 on POST /candidates"

    @pytest.mark.parametrize("role", _WRITE_ROLES)
    async def test_delete_candidate_not_forbidden(
        self, rbac_client: tuple[AsyncClient, FastAPI], role: UserRole
    ) -> None:
        client, app = rbac_client
        self._setup_overrides(app, role)
        r = await client.delete(f"/candidates/{_CANDIDATE_ID}")
        assert r.status_code != 403, f"{role.value} got 403 on DELETE /candidates/{{id}}"

    @pytest.mark.parametrize("role", _WRITE_ROLES)
    async def test_create_comparison_not_forbidden(
        self, rbac_client: tuple[AsyncClient, FastAPI], role: UserRole
    ) -> None:
        """Job lookup returns None → 404 before any LLM call; RBAC gate passed."""
        client, app = rbac_client
        self._setup_overrides(app, role)
        r = await client.post(
            "/comparisons",
            json={
                "job_id": str(_JOB_ID),
                "candidate_ids": [str(_CANDIDATE_ID), str(_CANDIDATE_ID_2)],
            },
        )
        assert r.status_code != 403, f"{role.value} got 403 on POST /comparisons"

    @pytest.mark.parametrize("role", _WRITE_ROLES)
    async def test_analyze_comparison_not_forbidden(
        self, rbac_client: tuple[AsyncClient, FastAPI], role: UserRole
    ) -> None:
        """Comparison lookup returns None → 404 before any LLM call; RBAC gate passed."""
        client, app = rbac_client
        self._setup_overrides(app, role)
        r = await client.post(f"/comparisons/{_COMPARISON_ID}/analyze")
        assert r.status_code != 403, f"{role.value} got 403 on POST compare/analyze"

    @pytest.mark.parametrize("role", _WRITE_ROLES)
    async def test_upload_file_not_forbidden(
        self, rbac_client: tuple[AsyncClient, FastAPI], role: UserRole
    ) -> None:
        client, app = rbac_client
        self._setup_overrides(app, role)
        with patch("app.storage.router._put_object"):
            r = await client.post(
                "/files/upload",
                files={"file": ("resume.pdf", PDF_BYTES, "application/pdf")},
            )
        assert r.status_code != 403, f"{role.value} got 403 on POST /files/upload"


# ── /parse edge cases ──────────────────────────────────────────────────────────

async def test_parse_requires_auth(rbac_client: tuple[AsyncClient, FastAPI]) -> None:
    """No token → 401 on /parse."""
    client, app = rbac_client
    mock_db = make_mock_db()

    async def db_override() -> AsyncGenerator:
        yield mock_db

    app.dependency_overrides[get_db] = db_override
    r = await client.post("/parse", json={"file_id": _FILE_ID})
    assert r.status_code == 401


async def test_viewer_cannot_call_parse(rbac_client: tuple[AsyncClient, FastAPI]) -> None:
    """/parse is guarded by require_write → VIEWER gets 403."""
    client, app = rbac_client
    viewer = make_user(UserRole.VIEWER)
    mock_db = make_mock_db()

    async def user_override():
        return viewer

    async def db_override() -> AsyncGenerator:
        yield mock_db

    app.dependency_overrides[get_current_user] = user_override
    app.dependency_overrides[get_db] = db_override

    fake_result = CandidateData()
    with patch("app.parser.router.parse_and_validate", new=AsyncMock(return_value=fake_result)):
        r = await client.post("/parse", json={"file_id": _FILE_ID})

    assert r.status_code == 403
