"""Tests for GET /files/{file_id}/download-url presigned URL endpoint."""

from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from minio.error import S3Error

from app.auth import get_current_user
from app.storage.router import router as storage_router
from app.users.models import UserRole
from tests.conftest import make_user

VALID_FILE_ID = "550e8400-e29b-41d4-a716-446655440000"
SIGNED_URL = f"https://minio.local/resumes/{VALID_FILE_ID}?X-Amz-Expires=300&X-Amz-Signature=abc"


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app = FastAPI()
    app.include_router(storage_router)
    recruiter = make_user(UserRole.RECRUITER)
    app.dependency_overrides[get_current_user] = lambda: recruiter
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_presigned_url_happy_path(client: AsyncClient) -> None:
    with patch("app.storage.router._presigned_get", return_value=SIGNED_URL):
        r = await client.get(f"/files/{VALID_FILE_ID}/download-url")
    assert r.status_code == 200
    data = r.json()
    assert data["url"] == SIGNED_URL
    assert data["expires_in"] == 300


async def test_presigned_url_invalid_file_id(client: AsyncClient) -> None:
    r = await client.get("/files/not-a-uuid/download-url")
    assert r.status_code == 400


async def test_presigned_url_object_missing(client: AsyncClient) -> None:
    err = S3Error(
        code="NoSuchKey",
        message="not found",
        resource=VALID_FILE_ID,
        request_id="x",
        host_id="y",
        response=None,
    )
    with patch("app.storage.router._presigned_get", side_effect=err):
        r = await client.get(f"/files/{VALID_FILE_ID}/download-url")
    assert r.status_code == 404


async def test_presigned_url_requires_auth() -> None:
    app = FastAPI()
    app.include_router(storage_router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.get(f"/files/{VALID_FILE_ID}/download-url")
    assert r.status_code == 401
