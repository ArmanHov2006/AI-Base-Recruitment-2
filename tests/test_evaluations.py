"""Tests for /candidates/{id}/evaluations endpoints."""

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.models import JobApplication
from app.auth import get_current_user, require_write
from app.database import get_db
from app.evaluations.models import CandidateEvaluation
from app.evaluations.router import router as evaluations_router
from app.users.models import UserRole
from tests.conftest import make_mock_db, make_user, make_valid_token

_CANDIDATE_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440010")
_EVAL_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440011")
_JOB_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440012")
_EVALUATOR_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440013")
_NOW = datetime.now(timezone.utc)

AUTH = {"Authorization": f"Bearer {make_valid_token(UserRole.RECRUITER)}"}
VIEWER_AUTH = {"Authorization": f"Bearer {make_valid_token(UserRole.VIEWER)}"}

_CREATE_BODY = {
    "job_id": str(_JOB_ID),
    "stage": "interview",
    "technical_score": 4,
    "communication_score": 3,
    "leadership_score": 3,
    "cultural_fit_score": 4,
    "english_score": 5,
    "domain_score": 3,
    "feedback": "Strong technical background",
}


def _make_candidate_orm() -> MagicMock:
    c = MagicMock()
    c.id = _CANDIDATE_ID
    c.deleted_at = None
    return c


def _make_job_orm() -> MagicMock:
    j = MagicMock()
    j.id = _JOB_ID
    j.title = "Senior Engineer"
    j.deleted_at = None
    j.creator_id = None
    return j


def _make_eval_orm(**overrides: object) -> MagicMock:
    e = MagicMock(spec=CandidateEvaluation)
    e.id = _EVAL_ID
    e.candidate_id = _CANDIDATE_ID
    e.job_id = _JOB_ID
    e.evaluator_id = _EVALUATOR_ID
    e.stage = "interview"
    e.overall_rating = None
    e.technical_score = 4
    e.communication_score = 3
    e.leadership_score = 3
    e.cultural_fit_score = 4
    e.english_score = 5
    e.domain_score = 3
    e.feedback = "Good candidate"
    e.ai_suggested_rating = None
    e.created_at = _NOW
    e.updated_at = _NOW
    e.deleted_at = None
    for k, v in overrides.items():
        setattr(e, k, v)
    return e


@pytest.fixture
async def client_and_db() -> AsyncGenerator[tuple[AsyncClient, AsyncMock], None]:
    mock_db = make_mock_db()
    _app = FastAPI()
    _app.include_router(evaluations_router)
    recruiter = make_user(UserRole.RECRUITER)
    recruiter.id = _EVALUATOR_ID
    recruiter.role = UserRole.RECRUITER
    _app.dependency_overrides[get_current_user] = lambda: recruiter
    _app.dependency_overrides[require_write] = lambda: recruiter

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    _app.dependency_overrides[get_db] = db_override
    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as c:
        yield c, mock_db


def _setup_execute_sequence(mock_db: AsyncMock, *responses: MagicMock) -> None:
    iter_responses = iter(responses)

    async def _side_effect(*args: object, **kwargs: object) -> MagicMock:
        try:
            return next(iter_responses)
        except StopIteration:
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            r.scalars.return_value.all.return_value = []
            r.all.return_value = []
            return r

    mock_db.execute = AsyncMock(side_effect=_side_effect)


def _found(obj: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    r.all.return_value = [(obj, "Jane Smith")] if obj else []
    r.scalars.return_value.all.return_value = [obj] if obj else []
    return r


def _empty() -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    r.all.return_value = []
    r.scalars.return_value.all.return_value = []
    return r


# ── POST /candidates/{id}/evaluations ─────────────────────────────────────────

async def test_create_evaluation_returns_201(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    candidate = _make_candidate_orm()
    job = _make_job_orm()
    _now = datetime.now(timezone.utc)

    added: list[object] = []

    def _add(obj: object) -> None:
        if isinstance(obj, CandidateEvaluation):
            obj.id = _EVAL_ID  # type: ignore[assignment]
            obj.created_at = _now  # type: ignore[assignment]
            obj.updated_at = _now  # type: ignore[assignment]
        added.append(obj)

    mock_db.add = _add

    # Sequence: _load_candidate, _load_job, (record add), refresh, evaluator lookup
    _setup_execute_sequence(
        mock_db,
        _found(candidate),
        _found(job),
        _empty(),           # evaluator name lookup
    )
    # db.refresh sets fields back on the object — use side_effect to re-apply timestamps
    mock_db.refresh = AsyncMock()

    r = await client.post(
        f"/candidates/{_CANDIDATE_ID}/evaluations",
        headers=AUTH,
        json=_CREATE_BODY,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["stage"] == "interview"
    assert data["technical_score"] == 4
    assert data["evaluator_id"] == str(_EVALUATOR_ID)


async def test_create_evaluation_candidate_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _setup_execute_sequence(mock_db, _empty())
    r = await client.post(
        f"/candidates/{_CANDIDATE_ID}/evaluations",
        headers=AUTH,
        json=_CREATE_BODY,
    )
    assert r.status_code == 404


async def test_create_evaluation_job_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    candidate = _make_candidate_orm()
    _setup_execute_sequence(mock_db, _found(candidate), _empty())
    r = await client.post(
        f"/candidates/{_CANDIDATE_ID}/evaluations",
        headers=AUTH,
        json=_CREATE_BODY,
    )
    assert r.status_code == 404


async def test_create_evaluation_viewer_denied(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    _app = client._transport.app  # type: ignore[attr-defined]
    _app.dependency_overrides[require_write] = lambda: (_ for _ in ()).throw(
        __import__("fastapi").HTTPException(status_code=403)
    )
    r = await client.post(
        f"/candidates/{_CANDIDATE_ID}/evaluations",
        headers=VIEWER_AUTH,
        json=_CREATE_BODY,
    )
    assert r.status_code == 403


async def test_create_evaluation_invalid_stage_returns_422(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, _ = client_and_db
    body = {**_CREATE_BODY, "stage": "not_a_valid_stage"}
    r = await client.post(
        f"/candidates/{_CANDIDATE_ID}/evaluations",
        headers=AUTH,
        json=body,
    )
    assert r.status_code == 422


# ── GET /candidates/{id}/evaluations ──────────────────────────────────────────

async def test_list_evaluations_returns_list(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    candidate = _make_candidate_orm()
    eval_orm = _make_eval_orm()
    # _load_candidate, then _fetch_evaluations_with_names (join query)
    _setup_execute_sequence(mock_db, _found(candidate), _found(eval_orm))
    r = await client.get(
        f"/candidates/{_CANDIDATE_ID}/evaluations", headers=AUTH
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["stage"] == "interview"


async def test_list_evaluations_candidate_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _setup_execute_sequence(mock_db, _empty())
    r = await client.get(
        f"/candidates/{_CANDIDATE_ID}/evaluations", headers=AUTH
    )
    assert r.status_code == 404


# ── PATCH /candidates/{id}/evaluations/{eval_id} ──────────────────────────────

async def test_patch_evaluation_returns_200(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    # update_evaluation only calls _load_evaluation (not _load_candidate)
    eval_orm = _make_eval_orm()
    # After refresh, evaluator lookup executes
    _setup_execute_sequence(mock_db, _found(eval_orm), _empty())
    mock_db.refresh = AsyncMock()
    r = await client.patch(
        f"/candidates/{_CANDIDATE_ID}/evaluations/{_EVAL_ID}",
        headers=AUTH,
        json={"feedback": "Very strong candidate"},
    )
    assert r.status_code == 200
    assert eval_orm.feedback == "Very strong candidate"


async def test_patch_evaluation_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    # update_evaluation only calls _load_evaluation
    _setup_execute_sequence(mock_db, _empty())
    r = await client.patch(
        f"/candidates/{_CANDIDATE_ID}/evaluations/{_EVAL_ID}",
        headers=AUTH,
        json={"feedback": "Updated"},
    )
    assert r.status_code == 404


# ── DELETE /candidates/{id}/evaluations/{eval_id} ─────────────────────────────

async def test_delete_evaluation_returns_204(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    # delete_evaluation only calls _load_evaluation
    eval_orm = _make_eval_orm()
    _setup_execute_sequence(mock_db, _found(eval_orm))
    r = await client.delete(
        f"/candidates/{_CANDIDATE_ID}/evaluations/{_EVAL_ID}", headers=AUTH
    )
    assert r.status_code == 204
    assert eval_orm.deleted_at is not None


async def test_delete_evaluation_not_found_returns_404(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    _setup_execute_sequence(mock_db, _empty())
    r = await client.delete(
        f"/candidates/{_CANDIDATE_ID}/evaluations/{_EVAL_ID}", headers=AUTH
    )
    assert r.status_code == 404


# ── Stage FSM tests (PATCH /jobs/{job_id}/applications/{app_id}/stage) ────────
# These are on the evaluations router, not the applications router.

_APP_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440090")


def _make_app_orm(**overrides: object) -> MagicMock:
    a = MagicMock(spec=JobApplication)
    a.id = _APP_ID
    a.job_id = _JOB_ID
    a.candidate_id = None
    a.status = "applied"
    a.resume_file_id = "550e8400-e29b-41d4-a716-446655440000"
    a.error_message = None
    a.applied_at = _NOW
    a.updated_at = _NOW
    a.deleted_at = None
    a.allow_duplicate = False
    for k, v in overrides.items():
        setattr(a, k, v)
    return a


async def test_stage_transition_valid_returns_200(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    job = _make_job_orm()
    app_orm = _make_app_orm(status="applied")
    # sequence: _load_job, _load_application, (candidate lookup skipped — candidate_id=None)
    _setup_execute_sequence(mock_db, _found(job), _found(app_orm))
    mock_db.refresh = AsyncMock()
    r = await client.patch(
        f"/jobs/{_JOB_ID}/applications/{_APP_ID}/stage",
        headers=AUTH,
        json={"stage": "reviewing"},
    )
    assert r.status_code == 200
    assert app_orm.status == "reviewing"


async def test_stage_transition_invalid_fsm_returns_409(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    job = _make_job_orm()
    app_orm = _make_app_orm(status="applied")
    _setup_execute_sequence(mock_db, _found(job), _found(app_orm))
    r = await client.patch(
        f"/jobs/{_JOB_ID}/applications/{_APP_ID}/stage",
        headers=AUTH,
        json={"stage": "offer"},  # applied → offer is invalid
    )
    assert r.status_code == 409


async def test_stage_transition_terminal_state_returns_409(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    job = _make_job_orm()
    app_orm = _make_app_orm(status="hired")  # terminal
    _setup_execute_sequence(mock_db, _found(job), _found(app_orm))
    r = await client.patch(
        f"/jobs/{_JOB_ID}/applications/{_APP_ID}/stage",
        headers=AUTH,
        json={"stage": "reviewing"},
    )
    assert r.status_code == 409


async def test_stage_transition_parsing_returns_409(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    client, mock_db = client_and_db
    job = _make_job_orm()
    app_orm = _make_app_orm(status="parsing")
    _setup_execute_sequence(mock_db, _found(job), _found(app_orm))
    r = await client.patch(
        f"/jobs/{_JOB_ID}/applications/{_APP_ID}/stage",
        headers=AUTH,
        json={"stage": "reviewing"},
    )
    assert r.status_code == 409
