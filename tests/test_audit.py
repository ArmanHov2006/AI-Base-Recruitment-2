"""Audit log middleware tests.

Strategy: mini FastAPI app + AuditLogMiddleware + patched async_session_factory.
Captures every AuditLog instance added to the session for inspection.
"""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.audit.middleware import AuditLogMiddleware
from app.audit.models import AuditLog
from app.users.models import UserRole
from tests.conftest import make_user


@pytest.fixture
async def audit_client() -> AsyncGenerator[tuple[AsyncClient, list[AuditLog]], None]:
    """Mini app with AuditLogMiddleware + capturing fake session."""
    captured: list[AuditLog] = []

    fake_session = MagicMock()
    fake_session.add = lambda obj: captured.append(obj)
    fake_session.commit = AsyncMock()

    @asynccontextmanager
    async def fake_factory():
        yield fake_session

    app = FastAPI()
    app.add_middleware(AuditLogMiddleware)

    @app.post("/candidates")
    async def create_candidate(request: Request) -> dict:
        request.state.user = make_user(UserRole.RECRUITER)
        return {"id": str(uuid.uuid4())}

    @app.get("/candidates")
    async def list_candidates(request: Request) -> list:
        request.state.user = make_user(UserRole.RECRUITER)
        return []

    @app.post("/auth/login")
    async def login() -> dict:
        return {"access_token": "x"}

    @app.delete("/jobs/{job_id}")
    async def delete_job(job_id: str) -> dict:
        # No user set → simulates 401 (middleware should record with user_id=NULL)
        return {"deleted": job_id}

    with patch("app.audit.middleware.async_session_factory", fake_factory):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c, captured


async def test_write_creates_audit_row(
    audit_client: tuple[AsyncClient, list[AuditLog]],
) -> None:
    client, captured = audit_client
    r = await client.post("/candidates", json={})
    assert r.status_code == 200
    assert len(captured) == 1
    row = captured[0]
    assert row.method == "POST"
    assert row.path == "/candidates"
    assert row.status_code == 200
    assert row.user_id is not None


async def test_read_does_not_create_audit_row(
    audit_client: tuple[AsyncClient, list[AuditLog]],
) -> None:
    client, captured = audit_client
    r = await client.get("/candidates")
    assert r.status_code == 200
    assert captured == []


async def test_skip_path_no_audit(
    audit_client: tuple[AsyncClient, list[AuditLog]],
) -> None:
    client, captured = audit_client
    r = await client.post("/auth/login", json={})
    assert r.status_code == 200
    assert captured == []


async def test_audit_records_without_user(
    audit_client: tuple[AsyncClient, list[AuditLog]],
) -> None:
    """No request.state.user set → user_id = NULL, still recorded."""
    client, captured = audit_client
    r = await client.delete(f"/jobs/{uuid.uuid4()}")
    assert r.status_code == 200
    assert len(captured) == 1
    assert captured[0].user_id is None
    assert captured[0].method == "DELETE"
