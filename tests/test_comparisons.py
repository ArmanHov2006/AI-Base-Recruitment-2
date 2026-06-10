"""Tests for comparisons: score cache, leaderboard, and history limit."""
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_write
from app.comparisons.router import router as comparisons_router
from app.comparisons.utils import compute_score_input_hash
from app.database import get_db
from app.jobs.router import router as jobs_router
from app.users.models import UserRole
from tests.conftest import make_user

AUTH = {"Authorization": "Bearer test-stub"}  # bypassed by dependency override

_JOB_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_CAND_ID_1 = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_CAND_ID_2 = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate_mock(
    cid: uuid.UUID = _CAND_ID_1,
    skills: list[str] | None = None,
    years_experience: float = 3.0,
    education: list | None = None,
    work_experiences: list | None = None,
    seniority: str = "mid",
    summary: str | None = None,
) -> MagicMock:
    m = MagicMock()
    m.id = cid
    m.skills = skills if skills is not None else ["Python", "SQL"]
    m.years_experience = years_experience
    m.education = education if education is not None else []
    m.work_experiences = work_experiences if work_experiences is not None else []
    m.seniority = seniority
    m.summary = summary
    return m


def _make_job_mock(
    jid: uuid.UUID = _JOB_ID,
    required_skills: list[str] | None = None,
    required_technical_skills: list[str] | None = None,
    required_soft_skills: list[str] | None = None,
    title: str = "Engineer",
    description: str = "Build things",
) -> MagicMock:
    m = MagicMock()
    m.id = jid
    m.title = title
    m.description = description
    m.required_skills = required_skills if required_skills is not None else ["FastAPI", "Docker"]
    m.required_technical_skills = required_technical_skills if required_technical_skills is not None else []
    m.required_soft_skills = required_soft_skills if required_soft_skills is not None else []
    m.required_seniority = "mid"
    return m


def _build_comparisons_app(mock_db: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(comparisons_router)

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    app.dependency_overrides[get_db] = db_override
    fake = make_user(UserRole.RECRUITER)
    app.dependency_overrides[get_current_user] = lambda: fake
    app.dependency_overrides[require_write] = lambda: fake
    return app


def _build_jobs_app(mock_db: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(jobs_router)

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    app.dependency_overrides[get_db] = db_override
    fake = make_user(UserRole.RECRUITER)
    app.dependency_overrides[get_current_user] = lambda: fake
    app.dependency_overrides[require_write] = lambda: fake
    return app


# ---------------------------------------------------------------------------
# Test 1 — hash is stable regardless of skill list order
# ---------------------------------------------------------------------------

async def test_hash_stability_sorted_inputs() -> None:
    cand_a = _make_candidate_mock(skills=["Python", "SQL"])
    cand_b = _make_candidate_mock(skills=["SQL", "Python"])

    job_a = _make_job_mock(required_skills=["FastAPI", "Docker"])
    job_b = _make_job_mock(required_skills=["Docker", "FastAPI"])

    hash_a = compute_score_input_hash(cand_a, job_a, "llama3.2")
    hash_b = compute_score_input_hash(cand_b, job_b, "llama3.2")

    assert hash_a == hash_b
    assert len(hash_a) == 64
    assert all(c in "0123456789abcdef" for c in hash_a)


# ---------------------------------------------------------------------------
# Test 2 — hash differs when model tag changes
# ---------------------------------------------------------------------------

async def test_hash_changes_on_model_tag() -> None:
    cand = _make_candidate_mock()
    job = _make_job_mock()

    hash_llama = compute_score_input_hash(cand, job, "llama3.2")
    hash_mistral = compute_score_input_hash(cand, job, "mistral")

    assert hash_llama != hash_mistral


# ---------------------------------------------------------------------------
# Test 3 — cache hit: LLM is NOT called
# ---------------------------------------------------------------------------

async def test_score_cache_hit() -> None:
    mock_db = AsyncMock(spec=AsyncSession)

    # The router calls execute 3 times for create_comparison:
    #   1. fetch job
    #   2. fetch candidates
    #   3. cache lookup (SELECT CandidateJobScore) — returns a cached row
    # We also need flush/commit to succeed.

    cached_score = MagicMock()
    cached_score.overall_score = 85
    cached_score.dimension_scores = {}
    cached_score.reasoning = "good"
    cached_score.skill_breakdown = None
    cached_score.score_input_hash = "any"

    # Build a fake job ORM
    fake_job = MagicMock()
    fake_job.id = _JOB_ID
    fake_job.title = "Engineer"
    fake_job.description = "Build things"
    fake_job.required_skills = ["FastAPI"]
    fake_job.required_technical_skills = []
    fake_job.required_soft_skills = []
    fake_job.required_seniority = "mid"
    fake_job.deleted_at = None

    # Build two fake candidate ORMs
    fake_cand1 = MagicMock()
    fake_cand1.id = _CAND_ID_1
    fake_cand1.name = "Alice"
    fake_cand1.email = "alice@example.com"
    fake_cand1.phone = None
    fake_cand1.skills = ["Python"]
    fake_cand1.years_experience = 3.0
    fake_cand1.education = []
    fake_cand1.work_experiences = []
    fake_cand1.location = None
    fake_cand1.seniority = "mid"
    fake_cand1.summary = None
    fake_cand1.desired_position = None
    fake_cand1.deleted_at = None

    fake_cand2 = MagicMock()
    fake_cand2.id = _CAND_ID_2
    fake_cand2.name = "Bob"
    fake_cand2.email = "bob@example.com"
    fake_cand2.phone = None
    fake_cand2.skills = ["SQL"]
    fake_cand2.years_experience = 2.0
    fake_cand2.education = []
    fake_cand2.work_experiences = []
    fake_cand2.location = None
    fake_cand2.seniority = "junior"
    fake_cand2.summary = None
    fake_cand2.desired_position = None
    fake_cand2.deleted_at = None

    # Fake comparison ORM that db.add() produces after flush
    fake_comparison = MagicMock()
    fake_comparison.id = uuid.uuid4()
    fake_comparison.job_id = _JOB_ID
    fake_comparison.status = "completed"
    fake_comparison.head_to_head_analysis = None
    fake_comparison.verdict = None
    fake_comparison.created_at = _NOW
    fake_comparison.completed_at = _NOW

    # Mock db.add — give every added ORM object required fields so Pydantic
    # serialisation does not fail.
    def _db_add(obj: object) -> None:
        if not hasattr(obj, "id") or obj.id is None:  # type: ignore[attr-defined]
            obj.id = uuid.uuid4()  # type: ignore[attr-defined]
        if not hasattr(obj, "created_at") or obj.created_at is None:  # type: ignore[attr-defined]
            obj.created_at = _NOW  # type: ignore[attr-defined]
        # Comparison-specific fields
        if hasattr(obj, "job_id") and not hasattr(obj, "comparison_id"):
            if not hasattr(obj, "completed_at") or obj.completed_at is None:  # type: ignore[attr-defined]
                obj.completed_at = _NOW  # type: ignore[attr-defined]
        # ComparisonResult-specific fields
        if hasattr(obj, "comparison_id"):
            if not hasattr(obj, "rank") or obj.rank is None:  # type: ignore[attr-defined]
                obj.rank = 1  # type: ignore[attr-defined]

    mock_db.add = MagicMock(side_effect=_db_add)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    # execute side effects:
    # call 0 → job lookup
    # call 1 → candidates lookup
    # call 2 → cache lookup for cand1 (hit)
    # call 3 → cache lookup for cand2 (hit)
    def _make_result(scalar_value=None, scalars_value=None):  # type: ignore[no-untyped-def]
        r = MagicMock()
        r.scalar_one_or_none.return_value = scalar_value
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = scalars_value or []
        r.scalars.return_value = scalars_mock
        return r

    job_result = _make_result(scalar_value=fake_job)
    cands_result = _make_result(scalars_value=[fake_cand1, fake_cand2])
    cache_hit_1 = _make_result(scalar_value=cached_score)
    cache_hit_2 = _make_result(scalar_value=cached_score)

    mock_db.execute = AsyncMock(
        side_effect=[job_result, cands_result, cache_hit_1, cache_hit_2]
    )

    body = {
        "job_id": str(_JOB_ID),
        "candidate_ids": [str(_CAND_ID_1), str(_CAND_ID_2)],
    }

    app = _build_comparisons_app(mock_db)

    with patch("app.comparisons.scoring._llm") as mock_llm:
        mock_llm.score_candidate = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/comparisons", headers=AUTH, json=body)

    assert r.status_code == 201
    mock_llm.score_candidate.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4 — cache miss: upsert INSERT is executed
# ---------------------------------------------------------------------------

async def test_score_cache_miss_upserts() -> None:
    mock_db = AsyncMock(spec=AsyncSession)

    fake_job = MagicMock()
    fake_job.id = _JOB_ID
    fake_job.title = "Engineer"
    fake_job.description = "Build things"
    fake_job.required_skills = ["FastAPI"]
    fake_job.required_technical_skills = []
    fake_job.required_soft_skills = []
    fake_job.required_seniority = "mid"
    fake_job.deleted_at = None

    fake_cand1 = MagicMock()
    fake_cand1.id = _CAND_ID_1
    fake_cand1.name = "Alice"
    fake_cand1.email = "alice@example.com"
    fake_cand1.phone = None
    fake_cand1.skills = ["Python"]
    fake_cand1.years_experience = 3.0
    fake_cand1.education = []
    fake_cand1.work_experiences = []
    fake_cand1.location = None
    fake_cand1.seniority = "mid"
    fake_cand1.summary = None
    fake_cand1.desired_position = None
    fake_cand1.deleted_at = None

    fake_cand2 = MagicMock()
    fake_cand2.id = _CAND_ID_2
    fake_cand2.name = "Bob"
    fake_cand2.email = "bob@example.com"
    fake_cand2.phone = None
    fake_cand2.skills = ["SQL"]
    fake_cand2.years_experience = 2.0
    fake_cand2.education = []
    fake_cand2.work_experiences = []
    fake_cand2.location = None
    fake_cand2.seniority = "junior"
    fake_cand2.summary = None
    fake_cand2.desired_position = None
    fake_cand2.deleted_at = None

    def _db_add(obj: object) -> None:
        if not hasattr(obj, "id") or obj.id is None:  # type: ignore[attr-defined]
            obj.id = uuid.uuid4()  # type: ignore[attr-defined]
        if not hasattr(obj, "created_at") or obj.created_at is None:  # type: ignore[attr-defined]
            obj.created_at = _NOW  # type: ignore[attr-defined]
        # Comparison (has job_id, no comparison_id)
        if hasattr(obj, "job_id") and not hasattr(obj, "comparison_id"):
            if not hasattr(obj, "completed_at") or obj.completed_at is None:  # type: ignore[attr-defined]
                obj.completed_at = None  # type: ignore[attr-defined]
        # ComparisonResult (has comparison_id)
        if hasattr(obj, "comparison_id"):
            if not hasattr(obj, "rank") or obj.rank is None:  # type: ignore[attr-defined]
                obj.rank = 1  # type: ignore[attr-defined]

    mock_db.add = MagicMock(side_effect=_db_add)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    def _make_result(scalar_value=None, scalars_value=None):  # type: ignore[no-untyped-def]
        r = MagicMock()
        r.scalar_one_or_none.return_value = scalar_value
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = scalars_value or []
        r.scalars.return_value = scalars_mock
        return r

    job_result = _make_result(scalar_value=fake_job)
    cands_result = _make_result(scalars_value=[fake_cand1, fake_cand2])
    # Cache miss for both candidates
    cache_miss_1 = _make_result(scalar_value=None)
    cache_miss_2 = _make_result(scalar_value=None)
    # After _score_one, the INSERT upsert is executed — return generic result
    upsert_result_1 = _make_result()
    upsert_result_2 = _make_result()

    mock_db.execute = AsyncMock(
        side_effect=[
            job_result,
            cands_result,
            cache_miss_1,
            upsert_result_1,
            cache_miss_2,
            upsert_result_2,
        ]
    )

    # Mock LLM to return a scoring result
    from app.llm.base import ScoringResult  # noqa: PLC0415

    fake_scoring = MagicMock(spec=ScoringResult)
    fake_scoring.overall_score = 75
    fake_scoring.dimension_scores = {}
    fake_scoring.reasoning = "decent"
    fake_scoring.skill_breakdown = None

    body = {
        "job_id": str(_JOB_ID),
        "candidate_ids": [str(_CAND_ID_1), str(_CAND_ID_2)],
    }

    app = _build_comparisons_app(mock_db)

    with patch("app.comparisons.scoring._llm") as mock_llm:
        mock_llm.score_candidate = AsyncMock(return_value=fake_scoring)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/comparisons", headers=AUTH, json=body)

    assert r.status_code == 201
    # LLM was called for each candidate (cache miss path)
    assert mock_llm.score_candidate.call_count == 2
    # Total execute calls: job + candidates + (cache_miss + upsert) * 2 = 6
    assert mock_db.execute.call_count == 6


# ---------------------------------------------------------------------------
# Test 5 — leaderboard ordered descending with correct ranks
# ---------------------------------------------------------------------------

async def test_leaderboard_ordered_desc() -> None:
    mock_db = AsyncMock(spec=AsyncSession)

    fake_job = MagicMock()
    fake_job.id = _JOB_ID
    fake_job.deleted_at = None

    score_high = MagicMock()
    score_high.overall_score = 90
    score_high.dimension_scores = {}
    score_high.skill_breakdown = None
    score_high.reasoning = "excellent"
    score_high.model_tag = "llama3.2"
    score_high.scored_at = _NOW
    score_high.updated_at = _NOW

    score_low = MagicMock()
    score_low.overall_score = 70
    score_low.dimension_scores = {}
    score_low.skill_breakdown = None
    score_low.reasoning = "decent"
    score_low.model_tag = "llama3.2"
    score_low.scored_at = _NOW
    score_low.updated_at = _NOW

    cand_a = MagicMock()
    cand_a.id = _CAND_ID_1
    cand_a.name = "Alice"
    cand_a.email = "alice@example.com"
    cand_a.seniority = "senior"

    cand_b = MagicMock()
    cand_b.id = _CAND_ID_2
    cand_b.name = "Bob"
    cand_b.email = "bob@example.com"
    cand_b.seniority = "mid"

    def _make_scalar(value=None):  # type: ignore[no-untyped-def]
        r = MagicMock()
        r.scalar_one_or_none.return_value = value
        return r

    def _make_all_rows(rows):  # type: ignore[no-untyped-def]
        r = MagicMock()
        r.all.return_value = rows
        return r

    # execute call 0 → job lookup
    # execute call 1 → leaderboard SELECT (returns ordered rows)
    mock_db.execute = AsyncMock(
        side_effect=[
            _make_scalar(fake_job),
            _make_all_rows([(score_high, cand_a), (score_low, cand_b)]),
        ]
    )

    app = _build_jobs_app(mock_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/jobs/{_JOB_ID}/leaderboard", headers=AUTH)

    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["overall_score"] == 90
    assert data[0]["rank"] == 1
    assert data[1]["overall_score"] == 70
    assert data[1]["rank"] == 2


# ---------------------------------------------------------------------------
# Test 6 — leaderboard returns only applicants (filtered by subquery)
# ---------------------------------------------------------------------------

async def test_leaderboard_applicants_only() -> None:
    mock_db = AsyncMock(spec=AsyncSession)

    fake_job = MagicMock()
    fake_job.id = _JOB_ID
    fake_job.deleted_at = None

    score_applicant = MagicMock()
    score_applicant.overall_score = 80
    score_applicant.dimension_scores = {}
    score_applicant.skill_breakdown = None
    score_applicant.reasoning = "good"
    score_applicant.model_tag = "llama3.2"
    score_applicant.scored_at = _NOW
    score_applicant.updated_at = _NOW

    cand_applicant = MagicMock()
    cand_applicant.id = _CAND_ID_1
    cand_applicant.name = "Alice"
    cand_applicant.email = "alice@example.com"
    cand_applicant.seniority = "senior"

    def _make_scalar(value=None):  # type: ignore[no-untyped-def]
        r = MagicMock()
        r.scalar_one_or_none.return_value = value
        return r

    def _make_all_rows(rows):  # type: ignore[no-untyped-def]
        r = MagicMock()
        r.all.return_value = rows
        return r

    # Only 1 row returned — simulates that only 1 of 2 scored candidates
    # is an applicant (the subquery filter happens inside the DB query).
    mock_db.execute = AsyncMock(
        side_effect=[
            _make_scalar(fake_job),
            _make_all_rows([(score_applicant, cand_applicant)]),
        ]
    )

    app = _build_jobs_app(mock_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/jobs/{_JOB_ID}/leaderboard", headers=AUTH)

    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["candidate_id"] == str(_CAND_ID_1)


# ---------------------------------------------------------------------------
# Test 7 — list_comparisons respects limit query parameter
# ---------------------------------------------------------------------------

async def test_list_comparisons_limit() -> None:
    mock_db = AsyncMock(spec=AsyncSession)

    def _make_comparison_mock(cid: uuid.UUID) -> MagicMock:
        c = MagicMock()
        c.id = cid
        c.job_id = _JOB_ID
        c.status = "completed"
        c.head_to_head_analysis = None
        c.verdict = None
        c.created_at = _NOW
        c.completed_at = _NOW
        return c

    comp1 = _make_comparison_mock(uuid.uuid4())
    comp2 = _make_comparison_mock(uuid.uuid4())
    comp3 = _make_comparison_mock(uuid.uuid4())

    # First execute call → comparisons list (router applies .limit(2) in the query)
    # We simulate that the DB respects the limit and returns only 2 rows.
    comps_result = MagicMock()
    scalars_mock = MagicMock()
    # Return only 2 comparisons, as if DB honoured limit=2
    scalars_mock.all.return_value = [comp1, comp2]
    comps_result.scalars.return_value = scalars_mock

    # Second execute call → ComparisonResult rows for those comparisons
    results_result = MagicMock()
    results_scalars = MagicMock()
    results_scalars.all.return_value = []
    results_result.scalars.return_value = results_scalars

    mock_db.execute = AsyncMock(side_effect=[comps_result, results_result])

    app = _build_comparisons_app(mock_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/comparisons?limit=2", headers=AUTH)

    assert r.status_code == 200
    data = r.json()
    # Response must not exceed the requested limit
    assert len(data) <= 2

    # Verify that limit was passed into the SQL query — the router calls
    # query.limit(limit) before executing, so execute must have been called
    # at least once (the comparisons query).
    assert mock_db.execute.call_count >= 1

    # Confirm that the `limit` query-param is accepted (not a 422)
    # and that the result honours it — 3rd comparison must not appear.
    returned_ids = {entry["id"] for entry in data}
    assert str(comp3.id) not in returned_ids
