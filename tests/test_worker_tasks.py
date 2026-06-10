"""Celery task dispatch + body tests.

Strategy:
  - Verify `apply_pipeline_task.delay` is called from the applications router.
  - Verify `score_candidate_for_job_task.delay` is fired by the pipeline once
    the application reaches `status="applied"`.
  - Exercise the task body sync paths via direct call to the underlying async
    helpers (patching DB + LLM).
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.applications.router import router as applications_router
from app.auth import get_current_user, require_write
from app.database import get_db
from app.users.models import UserRole
from tests.conftest import make_user

_JOB_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
_FILE_ID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
async def app_client() -> AsyncGenerator[tuple[AsyncClient, FastAPI], None]:
    app = FastAPI()
    app.include_router(applications_router)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c, app


async def test_create_application_enqueues_apply_pipeline_task(
    app_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, app = app_client

    fake_job = MagicMock()
    fake_job.id = _JOB_ID
    fake_job.deleted_at = None
    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = fake_job

    db = MagicMock()
    db.execute = AsyncMock(return_value=job_result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    now = datetime.now(timezone.utc)

    async def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.applied_at = now
        obj.updated_at = now

    db.refresh = AsyncMock(side_effect=fake_refresh)

    async def db_override() -> AsyncGenerator:
        yield db

    user = make_user(UserRole.RECRUITER)
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_write] = lambda: user

    with patch("app.applications.router.apply_pipeline_task.delay") as delay:
        r = await client.post(
            f"/jobs/{_JOB_ID}/applications", json={"file_id": _FILE_ID}
        )

    assert r.status_code == 202, r.text
    delay.assert_called_once()
    (arg,) = delay.call_args.args
    uuid.UUID(arg)  # is a valid UUID4 string


async def test_pipeline_enqueues_score_task_on_success() -> None:
    """When run_apply_pipeline reaches status=applied, scoring task fires."""
    from app.applications.service import run_apply_pipeline

    application = MagicMock()
    application.id = uuid.uuid4()
    application.job_id = _JOB_ID
    application.resume_file_id = _FILE_ID
    application.candidate_id = None
    application.status = "parsing"

    candidate = MagicMock()
    candidate.id = uuid.uuid4()
    candidate.email = "x@example.com"

    app_result = MagicMock()
    app_result.scalar_one_or_none.return_value = application
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = None
    cand_result = MagicMock()
    cand_result.scalar_one_or_none.return_value = candidate

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[app_result, cand_result, existing_result])
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_factory():
        yield db

    parsed = MagicMock()
    parsed.email = "x@example.com"

    with (
        patch("app.applications.service.async_session_factory", fake_factory),
        patch(
            "app.applications.service.parse_and_validate",
            new=AsyncMock(return_value=parsed),
        ),
        patch("app.worker.tasks.score_candidate_for_job_task.delay") as score_delay,
    ):
        await run_apply_pipeline(application.id)

    score_delay.assert_called_once_with(str(candidate.id), str(_JOB_ID))


async def test_celery_app_imports() -> None:
    """Smoke: celery_app + task registration works without a live broker."""
    from app.worker.celery_app import celery_app
    from app.worker.tasks import apply_pipeline_task, score_candidate_for_job_task

    assert celery_app.main == "ai_recruitment"
    assert "apply_pipeline" in celery_app.tasks
    assert "score_candidate_for_job" in celery_app.tasks
    assert apply_pipeline_task.name == "apply_pipeline"
    assert score_candidate_for_job_task.name == "score_candidate_for_job"
