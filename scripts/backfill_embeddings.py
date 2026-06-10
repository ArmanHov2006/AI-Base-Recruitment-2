"""Backfill embeddings for candidates where embedding IS NULL.

Usage: uv run python scripts/backfill_embeddings.py
"""
import asyncio
import sys

from sqlalchemy import select

from app.candidates.models import Candidate
from app.config import settings  # noqa: F401 — triggers settings validation
from app.database import async_session_factory
from app.llm.ollama import OllamaClient

BATCH_SIZE = 100
COMMIT_EVERY = 20


async def main() -> None:
    ollama = OllamaClient()
    total_embedded = 0
    batch_num = 0

    while True:
        async with async_session_factory() as db:
            result = await db.execute(
                select(Candidate)
                .where(
                    Candidate.embedding.is_(None),
                    Candidate.deleted_at.is_(None),
                )
                .order_by(Candidate.created_at)
                .limit(BATCH_SIZE)
            )
            candidates = list(result.scalars().all())
            if not candidates:
                break
            batch_num += 1
            print(f"Batch {batch_num}: {len(candidates)} candidates")
            batch_embedded = 0
            pending = 0
            for candidate in candidates:
                text = ((candidate.summary or "") + " " + " ".join(candidate.skills or [])).strip()
                if not text:
                    print(f"  {candidate.id} — skipped (no text)")
                    continue
                try:
                    candidate.embedding = await ollama.embed(text)
                    total_embedded += 1
                    batch_embedded += 1
                    pending += 1
                    print(f"  {candidate.id} — embedded")
                except Exception as exc:
                    print(f"  {candidate.id} — FAILED: {exc}", file=sys.stderr)
                if pending >= COMMIT_EVERY:
                    await db.commit()
                    pending = 0
            if pending:
                await db.commit()
            if batch_embedded == 0:
                break

    print(f"Done. Total embedded: {total_embedded}")


if __name__ == "__main__":
    asyncio.run(main())
