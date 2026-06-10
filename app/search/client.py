"""Elasticsearch async client singleton and index management.

Design notes:
- One ``candidates`` index; per-field analyzers cover Armenian (hye),
  Russian/Cyrillic (rus), and English.
- Synonyms are injected at index-creation time via a synonym_graph filter.
  The list lives in ``app/search/synonyms.py`` — editable without code changes;
  requires index recreation or ``_reload_search_analyzers`` to take effect.
- pgvector handles /semantic-search and /similar — ES is text-only.
- When ELASTICSEARCH_URL is empty/unset the client is None and callers
  should fall back gracefully (Postgres search).
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.search.synonyms import SKILL_SYNONYMS

log = logging.getLogger(__name__)

_es_client: Any | None = None  # elasticsearch.AsyncElasticsearch | None

CANDIDATES_INDEX = "candidates"

# ---------------------------------------------------------------------------
# Index settings — analyzers
# ---------------------------------------------------------------------------

_SETTINGS: dict[str, Any] = {
    "analysis": {
        "filter": {
            # Synonym expansion (BM25 + synonym-aware search)
            "skill_synonyms": {
                "type": "synonym_graph",
                "synonyms": SKILL_SYNONYMS,
                # Bake synonyms in at index time. An updateable filter is
                # search-time only and can't be used by an index-time analyzer
                # (these analyzers are the field `analyzer` in the mappings).
                # Editing synonyms.py requires recreating the index.
                "updateable": False,
                # Skip rules that can't be built (e.g. multi-word synonyms
                # containing a stopword like "infrastructure as code") instead
                # of failing the whole index. See ES synonym_graph docs.
                "lenient": True,
            },
            # Edge-ngram for autocomplete prefix matching
            "edge_ngram_filter": {
                "type": "edge_ngram",
                "min_gram": 2,
                "max_gram": 20,
            },
            # Language-specific stop words
            "armenian_stop": {
                "type": "stop",
                "stopwords": "_armenian_",
            },
            "russian_stop": {
                "type": "stop",
                "stopwords": "_russian_",
            },
            "russian_stemmer": {
                "type": "stemmer",
                "language": "russian",
            },
            "english_stop": {
                "type": "stop",
                "stopwords": "_english_",
            },
            "english_stemmer": {
                "type": "stemmer",
                "language": "english",
            },
            "english_possessive_stemmer": {
                "type": "stemmer",
                "language": "possessive_english",
            },
        },
        "analyzer": {
            # English with synonym expansion — primary analyzer for most fields
            "english_with_synonyms": {
                "tokenizer": "standard",
                "filter": [
                    "english_possessive_stemmer",
                    "lowercase",
                    "english_stop",
                    "english_stemmer",
                    "skill_synonyms",
                ],
            },
            # Russian / Cyrillic
            "russian_with_synonyms": {
                "tokenizer": "standard",
                "filter": [
                    "lowercase",
                    "russian_stop",
                    "russian_stemmer",
                    "skill_synonyms",
                ],
            },
            # Armenian — no built-in ES stemmer; use lowercase + icu_folding.
            # The standard tokenizer handles Armenian Unicode adequately;
            # icu_folding is available if the analysis-icu plugin is installed
            # (falls back gracefully if not).
            "armenian_analyzer": {
                "tokenizer": "standard",
                "filter": [
                    "lowercase",
                    "armenian_stop",
                ],
            },
            # Autocomplete — edge-ngram at index time, standard at search time
            "autocomplete": {
                "tokenizer": "standard",
                "filter": [
                    "lowercase",
                    "edge_ngram_filter",
                ],
            },
            "autocomplete_search": {
                "tokenizer": "standard",
                "filter": ["lowercase"],
            },
        },
    }
}

# ---------------------------------------------------------------------------
# Index mappings
# ---------------------------------------------------------------------------

_MAPPINGS: dict[str, Any] = {
    "properties": {
        "candidate_id": {"type": "keyword"},
        # Multi-field text: English, Russian, Armenian, keyword, autocomplete
        "name": {
            "type": "text",
            "analyzer": "english_with_synonyms",
            "fields": {
                "russian": {"type": "text", "analyzer": "russian_with_synonyms"},
                "armenian": {"type": "text", "analyzer": "armenian_analyzer"},
                "keyword": {"type": "keyword", "ignore_above": 256},
                "autocomplete": {
                    "type": "text",
                    "analyzer": "autocomplete",
                    "search_analyzer": "autocomplete_search",
                },
            },
        },
        "email": {"type": "keyword"},
        "location": {
            "type": "text",
            "analyzer": "english_with_synonyms",
            "fields": {
                "russian": {"type": "text", "analyzer": "russian_with_synonyms"},
                "armenian": {"type": "text", "analyzer": "armenian_analyzer"},
                "keyword": {"type": "keyword", "ignore_above": 256},
            },
        },
        "seniority": {"type": "keyword"},
        "years_experience": {"type": "float"},
        "desired_salary": {"type": "integer"},
        "desired_position": {
            "type": "text",
            "analyzer": "english_with_synonyms",
            "fields": {
                "russian": {"type": "text", "analyzer": "russian_with_synonyms"},
                "armenian": {"type": "text", "analyzer": "armenian_analyzer"},
                "keyword": {"type": "keyword", "ignore_above": 256},
            },
        },
        "summary": {
            "type": "text",
            "analyzer": "english_with_synonyms",
            "fields": {
                "russian": {"type": "text", "analyzer": "russian_with_synonyms"},
                "armenian": {"type": "text", "analyzer": "armenian_analyzer"},
            },
        },
        # Skills: text for synonym-aware search + keyword sub-field for facets
        "skills": {
            "type": "text",
            "analyzer": "english_with_synonyms",
            "fields": {
                "keyword": {"type": "keyword", "ignore_above": 128},
            },
        },
        "certifications": {
            "type": "text",
            "analyzer": "english_with_synonyms",
            "fields": {
                "keyword": {"type": "keyword", "ignore_above": 128},
            },
        },
        "languages": {"type": "keyword"},
        "resume_language": {"type": "keyword"},
        "status": {"type": "keyword"},
        "created_at": {"type": "date"},
        "deleted": {"type": "boolean"},
    }
}


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def get_es_client() -> Any | None:
    """Return the module-level AsyncElasticsearch singleton, or None if ES is unconfigured."""
    global _es_client
    if _es_client is not None:
        return _es_client
    if not settings.elasticsearch_url:
        return None
    try:
        from elasticsearch import AsyncElasticsearch  # type: ignore[import-untyped]

        kwargs: dict[str, Any] = {"hosts": [settings.elasticsearch_url]}
        if settings.elasticsearch_username and settings.elasticsearch_password:
            kwargs["basic_auth"] = (
                settings.elasticsearch_username,
                settings.elasticsearch_password,
            )
        _es_client = AsyncElasticsearch(**kwargs)
        log.info("elasticsearch.client_created", extra={"url": settings.elasticsearch_url})
    except ImportError:
        log.warning("elasticsearch package not installed — ES search disabled")
        _es_client = None
    return _es_client


async def ensure_index() -> None:
    """Create the candidates index with correct settings if it does not exist.

    Called at startup (lifespan) and idempotent — safe to call on every boot.
    """
    es = get_es_client()
    if es is None:
        return
    try:
        exists = await es.indices.exists(index=CANDIDATES_INDEX)
        if not exists:
            await es.indices.create(
                index=CANDIDATES_INDEX,
                settings=_SETTINGS,
                mappings=_MAPPINGS,
            )
            log.info("elasticsearch.index_created", extra={"index": CANDIDATES_INDEX})
        else:
            log.debug("elasticsearch.index_exists", extra={"index": CANDIDATES_INDEX})
    except Exception as exc:  # noqa: BLE001
        log.warning("elasticsearch.ensure_index_failed", extra={"exc": str(exc)})


async def close_es_client() -> None:
    """Close the async ES client (called at app shutdown)."""
    global _es_client
    if _es_client is not None:
        try:
            await _es_client.close()
        except Exception:  # noqa: BLE001
            pass
        _es_client = None
