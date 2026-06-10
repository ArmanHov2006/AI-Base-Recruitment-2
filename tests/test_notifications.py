"""Tests for /notifications endpoints."""

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.notifications.router import router as notifications_router
from app.users.models import UserRole
from tests.conftest import make_mock_db, make_user, make_valid_token

AUTH = {"Authorization": f"Bearer {make_valid_token(UserRole.RECRUITER)}"}
_NOW = datetime.now(timezone.utc)
_USER_ID = uuid.uuid4()
_NOTIF_ID = uuid.uuid4()


def _make_notif(**overrides: object) -> MagicMock:
    n = MagicMock()
    n.id = _NOTIF_ID
    n.user_id = _USER_ID
    n.type = "new_application"
    n.payload = {"job_title": "Engineer"}
    n.read_at = None
    n.created_at = _NOW
    for k, v in overrides.items():
        setattr(n, k, v)
    return n


@pytest.fixture
async def client_and_db() -> AsyncGenerator[tuple[AsyncClient, AsyncMock], None]:
    mock_db = make_mock_db()
    _app = FastAPI()
    _app.include_router(notifications_router)
    fake_user = make_user(UserRole.RECRUITER)
    fake_user.id = _USER_ID
    _app.dependency_overrides[get_current_user] = lambda: fake_user

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    _app.dependency_overrides[get_db] = db_override
    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as c:
        yield c, mock_db


# ── GET /notifications ────────────────────────────────────────────────────────

async def test_list_notifications_returns_items_and_count(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    notif = _make_notif()
    mock_db.execute.return_value.scalars.return_value.all.return_value = [notif]
    mock_db.execute.return_value.scalar_one.return_value = 1
    r = await client.get("/notifications", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "unread_count" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["type"] == "new_application"


async def test_list_notifications_empty(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    mock_db.execute.return_value.scalar_one.return_value = 0
    r = await client.get("/notifications", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["unread_count"] == 0


async def test_list_notifications_unauthenticated_returns_401(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    _app = client._transport.app  # type: ignore[attr-defined]
    _app.dependency_overrides.pop(get_current_user, None)
    r = await client.get("/notifications")
    assert r.status_code == 401


# ── PATCH /notifications/{id}/read ────────────────────────────────────────────

async def test_mark_notification_read_returns_updated(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    notif = _make_notif(read_at=None)
    mock_db.execute.return_value.scalar_one_or_none.return_value = notif
    r = await client.patch(f"/notifications/{_NOTIF_ID}/read", headers=AUTH)
    assert r.status_code == 200
    assert notif.read_at is not None


async def test_mark_already_read_notification_is_idempotent(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    notif = _make_notif(read_at=_NOW)
    mock_db.execute.return_value.scalar_one_or_none.return_value = notif
    r = await client.patch(f"/notifications/{_NOTIF_ID}/read", headers=AUTH)
    assert r.status_code == 200


async def test_mark_nonexistent_notification_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    r = await client.patch(f"/notifications/{_NOTIF_ID}/read", headers=AUTH)
    assert r.status_code == 404


# ── POST /notifications/read-all ─────────────────────────────────────────────

async def test_mark_all_read_returns_204(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    r = await client.post("/notifications/read-all", headers=AUTH)
    assert r.status_code == 204
    mock_db.commit.assert_called_once()
