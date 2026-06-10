"""Tests for /candidates/{id}/notes endpoints."""

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_write
from app.database import get_db
from app.notes.router import router as notes_router
from app.users.models import UserRole
from tests.conftest import make_mock_db, make_user, make_valid_token

_CANDIDATE_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440001")
_NOTE_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440002")
_AUTHOR_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440003")
_NOW = datetime.now(timezone.utc)

AUTH = {"Authorization": f"Bearer {make_valid_token(UserRole.RECRUITER)}"}
VIEWER_AUTH = {"Authorization": f"Bearer {make_valid_token(UserRole.VIEWER)}"}


def _make_candidate_orm() -> MagicMock:
    c = MagicMock()
    c.id = _CANDIDATE_ID
    c.deleted_at = None
    return c


def _make_note_orm(**overrides: object) -> MagicMock:
    n = MagicMock()
    n.id = _NOTE_ID
    n.candidate_id = _CANDIDATE_ID
    n.author_id = _AUTHOR_ID
    n.text = "Great candidate"
    n.created_at = _NOW
    n.updated_at = _NOW
    n.deleted_at = None
    for k, v in overrides.items():
        setattr(n, k, v)
    return n


@pytest.fixture
async def client_and_db() -> AsyncGenerator[tuple[AsyncClient, AsyncMock], None]:
    mock_db = make_mock_db()
    _app = FastAPI()
    _app.include_router(notes_router)
    recruiter = make_user(UserRole.RECRUITER)
    recruiter.id = _AUTHOR_ID
    recruiter.role = UserRole.RECRUITER
    _app.dependency_overrides[get_current_user] = lambda: recruiter
    _app.dependency_overrides[require_write] = lambda: recruiter

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    _app.dependency_overrides[get_db] = db_override
    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as c:
        yield c, mock_db


def _setup_execute_sequence(mock_db: AsyncMock, *responses: MagicMock) -> None:
    """Set successive execute() return values for multi-query routes."""
    iter_responses = iter(responses)

    async def _side_effect(*args: object, **kwargs: object) -> MagicMock:
        try:
            return next(iter_responses)
        except StopIteration:
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            r.scalars.return_value.all.return_value = []
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


# ── GET /candidates/{id}/notes ────────────────────────────────────────────────

async def test_list_notes_returns_list(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    candidate = _make_candidate_orm()
    note = _make_note_orm()
    _setup_execute_sequence(mock_db, _found(candidate), _found(note))
    r = await client.get(f"/candidates/{_CANDIDATE_ID}/notes", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


async def test_list_notes_candidate_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _setup_execute_sequence(mock_db, _empty())
    r = await client.get(f"/candidates/{_CANDIDATE_ID}/notes", headers=AUTH)
    assert r.status_code == 404


async def test_list_notes_unauthenticated_returns_401(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    _app = client._transport.app  # type: ignore[attr-defined]
    _app.dependency_overrides.pop(get_current_user, None)
    r = await client.get(f"/candidates/{_CANDIDATE_ID}/notes")
    assert r.status_code == 401


# ── POST /candidates/{id}/notes ───────────────────────────────────────────────

async def test_create_note_returns_201(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    candidate = _make_candidate_orm()
    _setup_execute_sequence(mock_db, _found(candidate))

    from datetime import datetime, timezone

    from app.notes.models import CandidateNote

    _now = datetime.now(timezone.utc)
    added: list[object] = []

    def _add(obj: object) -> None:
        if isinstance(obj, CandidateNote):
            obj.id = _NOTE_ID  # type: ignore[assignment]
            obj.created_at = _now  # type: ignore[assignment]
            obj.updated_at = _now  # type: ignore[assignment]
        added.append(obj)

    mock_db.add = _add
    r = await client.post(
        f"/candidates/{_CANDIDATE_ID}/notes",
        headers=AUTH,
        json={"text": "Strong communication skills"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["text"] == "Strong communication skills"
    assert data["author_id"] == str(_AUTHOR_ID)


async def test_create_note_blank_text_returns_422(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    r = await client.post(
        f"/candidates/{_CANDIDATE_ID}/notes",
        headers=AUTH,
        json={"text": "   "},
    )
    assert r.status_code == 422


async def test_create_note_candidate_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _setup_execute_sequence(mock_db, _empty())
    r = await client.post(
        f"/candidates/{_CANDIDATE_ID}/notes",
        headers=AUTH,
        json={"text": "A note"},
    )
    assert r.status_code == 404


async def test_create_note_viewer_allowed(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    # A3: VIEWER must be able to leave notes; endpoint uses get_current_user now
    client, _ = client_and_db
    _app = client._transport.app  # type: ignore[attr-defined]
    viewer = make_user(UserRole.VIEWER)
    _app.dependency_overrides[get_current_user] = lambda: viewer
    r = await client.post(
        f"/candidates/{_CANDIDATE_ID}/notes",
        headers=VIEWER_AUTH,
        json={"text": "A note"},
    )
    assert r.status_code != 403


# ── PATCH /candidates/{id}/notes/{note_id} ────────────────────────────────────

async def test_patch_note_by_author_returns_200(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    # update_note only calls _load_note (no _load_candidate)
    note = _make_note_orm(author_id=_AUTHOR_ID)
    _setup_execute_sequence(mock_db, _found(note))
    r = await client.patch(
        f"/candidates/{_CANDIDATE_ID}/notes/{_NOTE_ID}",
        headers=AUTH,
        json={"text": "Updated note text"},
    )
    assert r.status_code == 200
    assert note.text == "Updated note text"


async def test_patch_note_by_other_user_returns_403(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    other_author = uuid.uuid4()
    note = _make_note_orm(author_id=other_author)
    _setup_execute_sequence(mock_db, _found(note))
    r = await client.patch(
        f"/candidates/{_CANDIDATE_ID}/notes/{_NOTE_ID}",
        headers=AUTH,
        json={"text": "Try to edit someone else's note"},
    )
    assert r.status_code == 403


async def test_patch_note_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _setup_execute_sequence(mock_db, _empty())
    r = await client.patch(
        f"/candidates/{_CANDIDATE_ID}/notes/{_NOTE_ID}",
        headers=AUTH,
        json={"text": "Updated note"},
    )
    assert r.status_code == 404


# ── DELETE /candidates/{id}/notes/{note_id} ───────────────────────────────────

async def test_delete_note_by_author_returns_204(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    # delete_note only calls _load_note (no _load_candidate)
    note = _make_note_orm(author_id=_AUTHOR_ID)
    _setup_execute_sequence(mock_db, _found(note))
    r = await client.delete(
        f"/candidates/{_CANDIDATE_ID}/notes/{_NOTE_ID}", headers=AUTH
    )
    assert r.status_code == 204
    assert note.deleted_at is not None


async def test_delete_note_by_non_author_non_admin_returns_403(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    note = _make_note_orm(author_id=uuid.uuid4())
    _setup_execute_sequence(mock_db, _found(note))
    r = await client.delete(
        f"/candidates/{_CANDIDATE_ID}/notes/{_NOTE_ID}", headers=AUTH
    )
    assert r.status_code == 403


async def test_delete_note_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _setup_execute_sequence(mock_db, _empty())
    r = await client.delete(
        f"/candidates/{_CANDIDATE_ID}/notes/{_NOTE_ID}", headers=AUTH
    )
    assert r.status_code == 404
