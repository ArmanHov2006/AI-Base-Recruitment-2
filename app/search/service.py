"""Elasticsearch indexing + search service.

Public surface:
- ``index_candidate(candidate)`` — upsert one candidate document
- ``remove_candidate(candidate_id)`` — soft-delete (sets deleted=True)
- ``search_candidates(...)`` — BM25 text search with facets
- ``backfill_all_candidates(db)`` — index every active Postgres candidate
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import structlog

from app.search.client import CANDIDATES_INDEX, get_es_client

log = structlog.get_logger()
_stdlib_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Document helpers
# ---------------------------------------------------------------------------

def _candidate_to_doc(candidate: Any) -> dict[str, Any]:
    """Convert a SQLAlchemy Candidate ORM row to an ES document."""
    return {
        "candidate_id": str(candidate.id),
        "name": candidate.name or "",
        "email": candidate.email or "",
        "location": candidate.location or "",
        "seniority": candidate.seniority or "",
        "years_experience": candidate.years_experience,
        "desired_salary": candidate.desired_salary,
        "desired_position": candidate.desired_position or "",
        "summary": candidate.summary or "",
        "skills": candidate.skills or [],
        "certifications": candidate.certifications or [],
        "languages": candidate.languages or [],
        "resume_language": getattr(candidate, "resume_language", None) or "",
        "status": candidate.status or "parsed",
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        "deleted": candidate.deleted_at is not None,
    }


# ---------------------------------------------------------------------------
# Write operations (called from Celery tasks — must not raise for ES downtime)
# ---------------------------------------------------------------------------

async def index_candidate(candidate: Any) -> bool:
    """Upsert a candidate document into ES.  Returns True on success."""
    es = get_es_client()
    if es is None:
        return False
    try:
        doc = _candidate_to_doc(candidate)
        await es.index(
            index=CANDIDATES_INDEX,
            id=str(candidate.id),
            document=doc,
        )
        log.debug("es.indexed", candidate_id=str(candidate.id))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("es.index_failed", candidate_id=str(candidate.id), exc=str(exc))
        return False


async def remove_candidate(candidate_id: uuid.UUID) -> bool:
    """Mark a candidate as deleted in ES (soft-delete preserves history)."""
    es = get_es_client()
    if es is None:
        return False
    try:
        await es.update(
            index=CANDIDATES_INDEX,
            id=str(candidate_id),
            doc={"deleted": True},
            doc_as_upsert=False,
        )
        log.debug("es.removed", candidate_id=str(candidate_id))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("es.remove_failed", candidate_id=str(candidate_id), exc=str(exc))
        return False


async def backfill_all_candidates(db: Any) -> int:
    """Index every non-deleted candidate from Postgres into ES.

    Designed to be called from a one-shot Celery task.  Returns count indexed.
    """
    from sqlalchemy import select

    from app.candidates.models import Candidate

    result = await db.execute(
        select(Candidate).where(Candidate.deleted_at.is_(None))
    )
    candidates = result.scalars().all()
    indexed = 0
    for c in candidates:
        ok = await index_candidate(c)
        if ok:
            indexed += 1
    log.info("es.backfill_complete", total=len(candidates), indexed=indexed)
    return indexed


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def search_candidates(
    *,
    q: str | None = None,
    skills: list[str] | None = None,
    seniority: str | None = None,
    location: str | None = None,
    years_min: float | None = None,
    years_max: float | None = None,
    desired_salary_min: int | None = None,
    desired_salary_max: int | None = None,
    certification: str | None = None,
    status: str | None = None,
    resume_language: str | None = None,
    page: int = 1,
    size: int = 20,
) -> dict[str, Any] | None:
    """Execute BM25 text search with synonym expansion and return facets.

    Returns a dict with keys: ``hits`` (list of candidate_id strings),
    ``total``, ``facets`` (aggregation counts).
    Returns None if ES is unavailable (caller should fall back to Postgres).
    """
    es = get_es_client()
    if es is None:
        return None

    must_clauses: list[dict[str, Any]] = [
        {"term": {"deleted": False}}
    ]
    filter_clauses: list[dict[str, Any]] = []

    # Full-text query across all relevant fields
    if q:
        must_clauses.append({
            "multi_match": {
                "query": q,
                "fields": [
                    "name^3",
                    "name.russian^2",
                    "name.armenian^2",
                    "desired_position^2",
                    "desired_position.russian^2",
                    "desired_position.armenian^2",
                    "skills^2",
                    "summary",
                    "summary.russian",
                    "summary.armenian",
                    "location",
                    "location.russian",
                    "location.armenian",
                    "certifications",
                ],
                "type": "best_fields",
                "fuzziness": "AUTO",
                "prefix_length": 1,
                "operator": "or",
            }
        })

    # Skill filter (any-of, synonym-aware)
    if skills:
        for skill in skills:
            must_clauses.append({
                "match": {
                    "skills": {
                        "query": skill,
                        "fuzziness": "AUTO",
                        "prefix_length": 1,
                    }
                }
            })

    # Exact-match filters
    if seniority:
        filter_clauses.append({"term": {"seniority": seniority}})
    if status:
        filter_clauses.append({"term": {"status": status}})
    if resume_language:
        filter_clauses.append({"term": {"resume_language": resume_language}})

    # Location text filter
    if location:
        must_clauses.append({
            "multi_match": {
                "query": location,
                "fields": ["location", "location.russian", "location.armenian"],
                "type": "best_fields",
                "fuzziness": "AUTO",
            }
        })

    # Range filters
    range_fields: dict[str, dict[str, Any]] = {}
    if years_min is not None:
        range_fields.setdefault("years_experience", {})["gte"] = years_min
    if years_max is not None:
        range_fields.setdefault("years_experience", {})["lte"] = years_max
    if desired_salary_min is not None:
        range_fields.setdefault("desired_salary", {})["gte"] = desired_salary_min
    if desired_salary_max is not None:
        range_fields.setdefault("desired_salary", {})["lte"] = desired_salary_max
    for field, bounds in range_fields.items():
        filter_clauses.append({"range": {field: bounds}})

    # Certification filter
    if certification:
        must_clauses.append({
            "match": {
                "certifications": {
                    "query": certification,
                    "fuzziness": "AUTO",
                }
            }
        })

    query_body: dict[str, Any] = {
        "bool": {
            "must": must_clauses,
        }
    }
    if filter_clauses:
        query_body["bool"]["filter"] = filter_clauses

    # Aggregations for facets
    aggs: dict[str, Any] = {
        "by_seniority": {
            "terms": {"field": "seniority", "size": 20}
        },
        "by_skills": {
            "terms": {"field": "skills.keyword", "size": 50}
        },
        "by_location": {
            "terms": {"field": "location.keyword", "size": 30}
        },
        "by_status": {
            "terms": {"field": "status", "size": 10}
        },
        "by_resume_language": {
            "terms": {"field": "resume_language", "size": 10}
        },
    }

    from_ = (page - 1) * size

    try:
        resp = await es.search(
            index=CANDIDATES_INDEX,
            query=query_body,
            aggs=aggs,
            from_=from_,
            size=size,
            _source=["candidate_id"],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("es.search_failed", exc=str(exc))
        return None

    hits = resp["hits"]["hits"]
    total = resp["hits"]["total"]["value"]
    candidate_ids = [h["_source"]["candidate_id"] for h in hits]

    # Build facets from aggregations
    def _buckets(agg_name: str) -> list[dict[str, Any]]:
        raw = resp.get("aggregations", {}).get(agg_name, {}).get("buckets", [])
        return [{"value": b["key"], "count": b["doc_count"]} for b in raw]

    facets = {
        "seniority": _buckets("by_seniority"),
        "skills": _buckets("by_skills"),
        "location": _buckets("by_location"),
        "status": _buckets("by_status"),
        "resume_language": _buckets("by_resume_language"),
    }

    return {
        "candidate_ids": candidate_ids,
        "total": total,
        "facets": facets,
    }
