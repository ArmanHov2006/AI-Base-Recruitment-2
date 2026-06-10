"""Guardrail tests for the job_applications.status CHECK constraint.

Test 1 is always run: it parses the SQL CHECK clause out of migration
0017 and asserts the value list matches the runtime tuple in
``app.applications.schemas.APPLICATION_STATUSES``. If either list drifts,
this test fails in CI and forces the developer to keep them in sync.

Test 2 is an integration check that requires a real Postgres database.
It is gated behind the ``TEST_DATABASE_URL`` environment variable so
this file does not introduce any new test infrastructure. When the
variable is set, the test connects, inserts a placeholder ``jobs`` row,
then attempts to insert a ``job_applications`` row with
``status = 'new'`` and asserts the CHECK constraint raises
``IntegrityError``. The whole transaction is rolled back regardless of
outcome so no state leaks into the target DB.
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest

from app.applications.schemas import APPLICATION_STATUSES

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "0003_jobs_and_applications.py"
)

_STATUS_TUPLE_RE = re.compile(
    r"_APPLICATION_STATUSES\s*=\s*\(([\s\S]+?)\)",
    re.MULTILINE,
)


def _extract_check_values() -> tuple[str, ...]:
    """Extract _APPLICATION_STATUSES tuple from migration 0003."""
    text = _MIGRATION_PATH.read_text(encoding="utf-8")
    match = _STATUS_TUPLE_RE.search(text)
    if match is None:
        raise AssertionError(
            f"Could not find '_APPLICATION_STATUSES' tuple in {_MIGRATION_PATH.name}"
        )
    inner = match.group(1)
    parts = [p.strip().strip("'").strip('"').rstrip(",") for p in inner.split(",")]
    return tuple(p for p in parts if p)


# ── Test 1: drift guard (always runs) ─────────────────────────────────────────


def test_application_statuses_match_migration_check_constraint() -> None:
    """The CHECK clause in 0017 must list exactly the runtime statuses.

    If this fails: either (a) someone added a status to
    ``APPLICATION_STATUSES`` without writing a follow-up migration that
    updates the CHECK constraint, or (b) someone changed the CHECK
    clause directly. Reconcile the two before merging.
    """
    migration_values = _extract_check_values()
    assert migration_values == APPLICATION_STATUSES, (
        f"Drift between APPLICATION_STATUSES={APPLICATION_STATUSES!r} "
        f"and 0017 CHECK clause={migration_values!r}"
    )


# ── Test 2: integration check (skipped without a test DB) ─────────────────────

_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(
    not _TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; integration check requires a real Postgres DB",
)
def test_status_constraint_rejects_unknown_value() -> None:
    """Inserting status='new' must raise IntegrityError when the CHECK is live.

    Assumes the target DB has migrations applied through 0017 (i.e. the
    same CI invariant that ``alembic upgrade head`` enforces). The whole
    transaction is rolled back so this test leaves no residue.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import IntegrityError

    sync_url = _TEST_DATABASE_URL  # type: ignore[assignment]
    assert sync_url is not None
    # The app uses postgresql+asyncpg at runtime; the sync driver here
    # avoids pulling asyncio into a plain pytest function.
    sync_url = sync_url.replace("postgresql+asyncpg", "postgresql+psycopg")
    sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql://")

    engine = create_engine(sync_url, future=True)
    job_id = uuid.uuid4()
    app_id = uuid.uuid4()

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(
                text("INSERT INTO jobs (id, title) VALUES (:id, :title)"),
                {"id": str(job_id), "title": "status-constraint test job"},
            )
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO job_applications "
                        "(id, job_id, resume_file_id, status) "
                        "VALUES (:id, :job_id, :rf, :status)"
                    ),
                    {
                        "id": str(app_id),
                        "job_id": str(job_id),
                        "rf": "test-rf",
                        "status": "new",
                    },
                )
        finally:
            trans.rollback()

    engine.dispose()
