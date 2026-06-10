"""Backfill candidate search surfaces: pgvector embeddings + Elasticsearch index.

Fixes two silent gaps:
  1. Embeddings are only generated when a candidate is applied to a job
     (worker._embed_candidate_from_application). Candidates created by plain
     resume upload never get an embedding, so semantic-search returns nothing.
  2. The ES `candidates` index is only written on candidate create (fire-and-forget
     Celery task). Candidates that predate ES wiring are never indexed, so
     keyword search returns total:0 while Postgres holds the rows.

This script embeds every non-deleted candidate missing an embedding, then
reindexes every non-deleted candidate into ES.

Idempotent: skips candidates that already have an embedding; ES index is an upsert.

Usage:
    uv run python scripts/backfill_search.py
    uv run python scripts/backfill_search.py --embeddings-only
    uv run python scripts/backfill_search.py --es-only
"""
import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select

from app.candidates.models import Candidate
from app.database import async_session_factory
from app.llm.factory import get_llm_client
from app.search.service import backfill_all_candidates


async def backfill_embeddings() -> tuple[int, int]:
    """Embed every non-deleted candidate that has no embedding yet.

    Returns (embedded, skipped_no_text).
    """
    llm = get_llm_client()
    embedded = 0
    skipped = 0

    async with async_session_factory() as db:
        result = await db.execute(
            select(Candidate).where(
                Candidate.deleted_at.is_(None),
                Candidate.embedding.is_(None),
            )
        )
        candidates = result.scalars().all()
        total = len(candidates)
        print(f"[embeddings] {total} candidate(s) missing an embedding")

        for i, candidate in enumerate(candidates, start=1):
            text = (
                (candidate.summary or "") + " " + " ".join(candidate.skills or [])
            ).strip()
            if not text:
                skipped += 1
                continue
            try:
                candidate.embedding = await llm.embed(text)
                embedded += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[embeddings] FAILED {candidate.id}: {exc}")
                continue
            if i % 25 == 0:
                await db.commit()
                print(f"[embeddings] {i}/{total} processed")

        await db.commit()

    print(f"[embeddings] done — embedded={embedded} skipped_no_text={skipped}")
    return embedded, skipped


async def backfill_es() -> int:
    """Index every non-deleted candidate into Elasticsearch."""
    async with async_session_factory() as db:
        indexed = await backfill_all_candidates(db)
    print(f"[elasticsearch] done — indexed={indexed}")
    return indexed


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings-only", action="store_true")
    parser.add_argument("--es-only", action="store_true")
    args = parser.parse_args()

    do_embeddings = not args.es_only
    do_es = not args.embeddings_only

    if do_embeddings:
        await backfill_embeddings()
    if do_es:
        indexed = await backfill_es()
        if indexed == 0:
            print(
                "[elasticsearch] WARNING: indexed 0 — is ELASTICSEARCH_URL set and the"
                " server reachable? Search will fall back to Postgres."
            )

    print("\nBackfill complete.")


if __name__ == "__main__":
    asyncio.run(main())
