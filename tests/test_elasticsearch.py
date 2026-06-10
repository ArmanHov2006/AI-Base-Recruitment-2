"""Tests for F4 — Elasticsearch search integration.

All tests run without a real ES instance.  We mock ``search_candidates``
from ``app.search.service`` to verify:
- ES path: results are fetched from Postgres by ES-returned IDs, facets propagated.
- Fallback path: when ES returns None (not configured), Postgres ILIKE is used.
- Write outbox: create/update/delete enqueue the correct Celery tasks.
- Backfill task: indexes all non-deleted candidates.
- ES removal: soft-delete updates deleted=True.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_write
from app.candidates.models import Candidate
from app.candidates.router import router as candidates_router
from app.candidates.schemas import CandidateListResponse, FacetBucket, SearchFacets
from app.database import get_db
from app.users.models import UserRole
from tests.conftest import make_mock_db, make_user, make_valid_token

AUTH = {"Authorization": f"Bearer {make_valid_token(UserRole.RECRUITER)}"}

_FAKE_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440099")
_FAKE_FILE_ID = "550e8400-e29b-41d4-a716-446655440000"
_NOW = datetime.now(timezone.utc)


def _make_fake_candidate(**overrides: object) -> MagicMock:
    orm = MagicMock(spec=Candidate)
    orm.id = _FAKE_ID
    orm.file_id = _FAKE_FILE_ID
    orm.status = "parsed"
    orm.name = "Arman Test"
    orm.email = "arman@example.am"
    orm.phone = None
    orm.skills = ["python", "fastapi"]
    orm.years_experience = 4.0
    orm.education = []
    orm.work_experiences = []
    orm.location = "Yerevan"
    orm.seniority = "mid"
    orm.summary = "Backend developer"
    orm.desired_position = "Backend Engineer"
    orm.certifications = []
    orm.languages = ["Armenian", "English"]
    orm.linkedin_url = None
    orm.github_url = None
    orm.desired_salary = None
    orm.photo_url = None
    orm.current_resume_version = 1
    orm.resume_language = "hy"
    orm.created_at = _NOW
    orm.deleted_at = None
    for k, v in overrides.items():
        setattr(orm, k, v)
    return orm


@pytest.fixture
async def client_and_db() -> AsyncGenerator[tuple[AsyncClient, AsyncMock], None]:
    mock_db = make_mock_db()
    _app = FastAPI()
    _app.include_router(candidates_router)

    async def db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db  # type: ignore[misc]

    _app.dependency_overrides[get_db] = db_override
    _fake_user = make_user(UserRole.RECRUITER)
    _app.dependency_overrides[get_current_user] = lambda: _fake_user
    _app.dependency_overrides[require_write] = lambda: _fake_user
    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as c:
        yield c, mock_db


# ---------------------------------------------------------------------------
# Schema tests — CandidateListResponse with facets
# ---------------------------------------------------------------------------

def test_candidate_list_response_default_facets() -> None:
    resp = CandidateListResponse.build(items=[], total=0, page=1, size=20)
    assert resp.facets == SearchFacets()
    assert resp.facets.seniority == []
    assert resp.facets.skills == []


def test_candidate_list_response_with_facets() -> None:
    facets = {
        "seniority": [{"value": "senior", "count": 5}],
        "skills": [{"value": "python", "count": 10}],
        "location": [],
        "status": [],
        "resume_language": [{"value": "hy", "count": 3}],
    }
    resp = CandidateListResponse.build(items=[], total=5, page=1, size=20, facets=facets)
    assert resp.facets.seniority == [FacetBucket(value="senior", count=5)]
    assert resp.facets.skills == [FacetBucket(value="python", count=10)]
    assert resp.facets.resume_language == [FacetBucket(value="hy", count=3)]
    assert resp.facets.location == []


# ---------------------------------------------------------------------------
# ES search path — ES returns results
# ---------------------------------------------------------------------------

async def test_search_uses_es_when_available(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    """When ES returns candidate IDs, those are fetched from Postgres in order."""
    client, mock_db = client_and_db
    fake = _make_fake_candidate()

    es_result = {
        "candidate_ids": [str(_FAKE_ID)],
        "total": 1,
        "facets": {
            "seniority": [{"value": "mid", "count": 1}],
            "skills": [],
            "location": [],
            "status": [],
            "resume_language": [{"value": "hy", "count": 1}],
        },
    }

    # DB returns the candidate when fetched by ID
    mock_db.execute.return_value.scalars.return_value.all.return_value = [fake]

    with patch("app.search.service.search_candidates", new=AsyncMock(return_value=es_result)):
        r = await client.get("/candidates/search", headers=AUTH, params={"q": "python"})

    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Arman Test"
    assert data["facets"]["seniority"][0]["value"] == "mid"
    assert data["facets"]["resume_language"][0]["value"] == "hy"


async def test_search_es_empty_results(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    """ES returning empty list produces empty response with zero total."""
    client, mock_db = client_and_db
    es_result = {
        "candidate_ids": [],
        "total": 0,
        "facets": {"seniority": [], "skills": [], "location": [], "status": [], "resume_language": []},
    }
    with patch("app.search.service.search_candidates", new=AsyncMock(return_value=es_result)):
        r = await client.get("/candidates/search", headers=AUTH, params={"q": "nonexistent"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


# ---------------------------------------------------------------------------
# Postgres fallback path — ES returns None
# ---------------------------------------------------------------------------

async def test_search_falls_back_to_postgres_when_es_unavailable(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    """When ES returns None (not configured), Postgres ILIKE is used."""
    client, mock_db = client_and_db
    fake = _make_fake_candidate()

    # Postgres path: first execute = count, second = rows
    count_result = MagicMock()
    count_result.scalar_one.return_value = 1
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = [fake]
    mock_db.execute = AsyncMock(side_effect=[count_result, rows_result])

    with patch("app.search.service.search_candidates", new=AsyncMock(return_value=None)):
        r = await client.get("/candidates/search", headers=AUTH, params={"q": "arman"})

    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    # Facets should be empty in Postgres fallback
    assert data["facets"]["seniority"] == []
    assert data["facets"]["skills"] == []


async def test_search_fallback_resume_language_filter(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    """resume_language filter works in the Postgres fallback path."""
    client, mock_db = client_and_db

    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(side_effect=[count_result, rows_result])

    with patch("app.search.service.search_candidates", new=AsyncMock(return_value=None)):
        r = await client.get(
            "/candidates/search", headers=AUTH, params={"resume_language": "hy"}
        )

    assert r.status_code == 200
    assert r.json()["total"] == 0


# ---------------------------------------------------------------------------
# Write outbox — create triggers ES index task
# ---------------------------------------------------------------------------

async def test_create_candidate_enqueues_es_index(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    """Creating a candidate calls _enqueue_es_index."""
    client, mock_db = client_and_db

    added: list[object] = []
    def _add(obj: object) -> None:
        if isinstance(obj, Candidate):
            obj.id = _FAKE_ID  # type: ignore[assignment]
            obj.status = "parsed"  # type: ignore[assignment]
            obj.created_at = _NOW  # type: ignore[assignment]
        added.append(obj)
    mock_db.add = _add

    body = {
        "file_id": _FAKE_FILE_ID,
        "name": "Hayk Candidate",
        "email": "hayk@example.am",
        "skills": ["python"],
    }

    enqueued: list[str] = []
    with patch("app.candidates.router._enqueue_es_index", side_effect=lambda cid: enqueued.append(cid)):
        r = await client.post("/candidates", headers=AUTH, json=body)

    assert r.status_code == 201
    assert enqueued == [str(_FAKE_ID)]


async def test_update_candidate_enqueues_es_index(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    """Updating a candidate calls _enqueue_es_index."""
    client, mock_db = client_and_db
    fake = _make_fake_candidate()
    mock_db.execute.return_value.scalar_one_or_none.return_value = fake

    enqueued: list[str] = []
    with patch("app.candidates.router._enqueue_es_index", side_effect=lambda cid: enqueued.append(cid)):
        r = await client.patch(
            f"/candidates/{_FAKE_ID}", headers=AUTH, json={"name": "Updated"}
        )

    assert r.status_code == 200
    assert enqueued == [str(_FAKE_ID)]


async def test_delete_candidate_enqueues_es_remove(
    client_and_db: tuple[AsyncClient, AsyncMock],
) -> None:
    """Deleting a candidate calls _enqueue_es_remove."""
    client, mock_db = client_and_db
    fake = _make_fake_candidate(deleted_at=None)
    mock_db.execute.return_value.scalar_one_or_none.return_value = fake

    enqueued: list[str] = []
    with patch("app.candidates.router._enqueue_es_remove", side_effect=lambda cid: enqueued.append(cid)):
        r = await client.delete(f"/candidates/{_FAKE_ID}", headers=AUTH)

    assert r.status_code == 204
    assert enqueued == [str(_FAKE_ID)]


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------

async def test_index_candidate_returns_false_when_es_not_configured() -> None:
    """index_candidate returns False gracefully when ES is not configured."""
    from app.search.service import index_candidate

    fake = _make_fake_candidate()
    with patch("app.search.service.get_es_client", return_value=None):
        result = await index_candidate(fake)
    assert result is False


async def test_remove_candidate_returns_false_when_es_not_configured() -> None:
    """remove_candidate returns False gracefully when ES is not configured."""
    from app.search.service import remove_candidate

    with patch("app.search.service.get_es_client", return_value=None):
        result = await remove_candidate(_FAKE_ID)
    assert result is False


async def test_search_candidates_returns_none_when_es_not_configured() -> None:
    """search_candidates returns None gracefully when ES is not configured."""
    from app.search.service import search_candidates

    with patch("app.search.service.get_es_client", return_value=None):
        result = await search_candidates(q="python")
    assert result is None


async def test_index_candidate_success() -> None:
    """index_candidate calls es.index and returns True."""
    from app.search.service import index_candidate

    fake = _make_fake_candidate()
    mock_es = AsyncMock()
    mock_es.index = AsyncMock()
    with patch("app.search.service.get_es_client", return_value=mock_es):
        result = await index_candidate(fake)
    assert result is True
    mock_es.index.assert_called_once()
    call_kwargs = mock_es.index.call_args.kwargs
    assert call_kwargs["id"] == str(_FAKE_ID)
    assert call_kwargs["document"]["deleted"] is False
    assert "skills" in call_kwargs["document"]


async def test_index_candidate_es_failure_returns_false() -> None:
    """index_candidate returns False (not raises) when ES throws."""
    from app.search.service import index_candidate

    fake = _make_fake_candidate()
    mock_es = AsyncMock()
    mock_es.index = AsyncMock(side_effect=RuntimeError("ES down"))
    with patch("app.search.service.get_es_client", return_value=mock_es):
        result = await index_candidate(fake)
    assert result is False


async def test_remove_candidate_marks_deleted() -> None:
    """remove_candidate calls es.update with deleted=True."""
    from app.search.service import remove_candidate

    mock_es = AsyncMock()
    mock_es.update = AsyncMock()
    with patch("app.search.service.get_es_client", return_value=mock_es):
        result = await remove_candidate(_FAKE_ID)
    assert result is True
    mock_es.update.assert_called_once()
    call_kwargs = mock_es.update.call_args.kwargs
    assert call_kwargs["doc"] == {"deleted": True}
    assert call_kwargs["id"] == str(_FAKE_ID)


async def test_search_candidates_builds_multi_match_query() -> None:
    """search_candidates calls es.search with a multi_match clause when q is set."""
    from app.search.service import search_candidates

    mock_es = AsyncMock()
    mock_es.search = AsyncMock(return_value={
        "hits": {"hits": [], "total": {"value": 0}},
        "aggregations": {},
    })
    with patch("app.search.service.get_es_client", return_value=mock_es):
        result = await search_candidates(q="python developer")

    assert result is not None
    assert result["total"] == 0
    assert result["candidate_ids"] == []

    call_kwargs = mock_es.search.call_args.kwargs
    query = call_kwargs["query"]
    must = query["bool"]["must"]
    # First must clause is deleted=false; second should be the multi_match
    assert any("multi_match" in clause for clause in must)


async def test_search_candidates_applies_skill_filter() -> None:
    """search_candidates adds a match clause per skill."""
    from app.search.service import search_candidates

    mock_es = AsyncMock()
    mock_es.search = AsyncMock(return_value={
        "hits": {"hits": [], "total": {"value": 0}},
        "aggregations": {},
    })
    with patch("app.search.service.get_es_client", return_value=mock_es):
        result = await search_candidates(skills=["kubernetes", "docker"])

    assert result is not None
    call_kwargs = mock_es.search.call_args.kwargs
    must = call_kwargs["query"]["bool"]["must"]
    skill_clauses = [c for c in must if "match" in c and "skills" in c.get("match", {})]
    assert len(skill_clauses) == 2


async def test_search_candidates_applies_seniority_filter() -> None:
    """search_candidates adds a seniority term filter clause."""
    from app.search.service import search_candidates

    mock_es = AsyncMock()
    mock_es.search = AsyncMock(return_value={
        "hits": {"hits": [], "total": {"value": 0}},
        "aggregations": {},
    })
    with patch("app.search.service.get_es_client", return_value=mock_es):
        await search_candidates(seniority="senior")

    call_kwargs = mock_es.search.call_args.kwargs
    filter_clauses = call_kwargs["query"]["bool"].get("filter", [])
    assert any(c.get("term", {}).get("seniority") == "senior" for c in filter_clauses)


async def test_search_candidates_applies_range_filters() -> None:
    """search_candidates adds range clauses for years and salary."""
    from app.search.service import search_candidates

    mock_es = AsyncMock()
    mock_es.search = AsyncMock(return_value={
        "hits": {"hits": [], "total": {"value": 0}},
        "aggregations": {},
    })
    with patch("app.search.service.get_es_client", return_value=mock_es):
        await search_candidates(years_min=2.0, years_max=10.0, desired_salary_min=50000)

    call_kwargs = mock_es.search.call_args.kwargs
    filter_clauses = call_kwargs["query"]["bool"].get("filter", [])
    range_clauses = [c for c in filter_clauses if "range" in c]
    # years_experience + desired_salary
    assert len(range_clauses) == 2


async def test_search_candidates_facets_parsed() -> None:
    """Aggregation buckets from ES are returned as facets."""
    from app.search.service import search_candidates

    mock_es = AsyncMock()
    mock_es.search = AsyncMock(return_value={
        "hits": {
            "hits": [{"_source": {"candidate_id": str(_FAKE_ID)}}],
            "total": {"value": 1},
        },
        "aggregations": {
            "by_seniority": {"buckets": [{"key": "senior", "doc_count": 3}]},
            "by_skills": {"buckets": [{"key": "python", "doc_count": 7}]},
            "by_location": {"buckets": []},
            "by_status": {"buckets": []},
            "by_resume_language": {"buckets": [{"key": "hy", "doc_count": 2}]},
        },
    })
    with patch("app.search.service.get_es_client", return_value=mock_es):
        result = await search_candidates(q="developer")

    assert result is not None
    assert result["facets"]["seniority"] == [{"value": "senior", "count": 3}]
    assert result["facets"]["skills"] == [{"value": "python", "count": 7}]
    assert result["facets"]["resume_language"] == [{"value": "hy", "count": 2}]


# ---------------------------------------------------------------------------
# Backfill task
# ---------------------------------------------------------------------------

async def test_backfill_indexes_all_candidates() -> None:
    """backfill_all_candidates indexes every non-deleted Postgres candidate."""
    from app.search.service import backfill_all_candidates

    fake1 = _make_fake_candidate()
    fake2 = _make_fake_candidate(id=uuid.uuid4(), email="other@example.am")

    mock_db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [fake1, fake2]
    mock_db.execute = AsyncMock(return_value=result)

    with patch("app.search.service.index_candidate", new=AsyncMock(return_value=True)) as mock_idx:
        count = await backfill_all_candidates(mock_db)

    assert count == 2
    assert mock_idx.call_count == 2


async def test_backfill_counts_only_successes() -> None:
    """backfill_all_candidates counts only documents successfully indexed."""
    from app.search.service import backfill_all_candidates

    fake1 = _make_fake_candidate()
    fake2 = _make_fake_candidate(id=uuid.uuid4())

    mock_db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [fake1, fake2]
    mock_db.execute = AsyncMock(return_value=result)

    # First succeeds, second fails
    with patch(
        "app.search.service.index_candidate",
        new=AsyncMock(side_effect=[True, False]),
    ):
        count = await backfill_all_candidates(mock_db)

    assert count == 1


# ---------------------------------------------------------------------------
# Synonym list sanity check
# ---------------------------------------------------------------------------

def test_synonym_list_has_kubernetes_entry() -> None:
    from app.search.synonyms import SKILL_SYNONYMS
    assert any("kubernetes" in s.lower() and "k8s" in s.lower() for s in SKILL_SYNONYMS)


def test_synonym_list_has_javascript_entry() -> None:
    from app.search.synonyms import SKILL_SYNONYMS
    assert any("javascript" in s.lower() for s in SKILL_SYNONYMS)


def test_synonym_list_no_empty_entries() -> None:
    from app.search.synonyms import SKILL_SYNONYMS
    for entry in SKILL_SYNONYMS:
        assert entry.strip(), f"Empty synonym entry found: {entry!r}"
