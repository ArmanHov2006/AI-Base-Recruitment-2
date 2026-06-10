"""
Hard-delete ALL applications, candidates, and their MinIO files.
Clears: applications, candidates, candidate_job_scores, comparisons,
        comparison_results, candidate_resumes, candidate_evaluations,
        candidate_notes, audit_log rows for these resources.

Usage:
  python scripts/nuke_candidates.py          # dry-run: shows counts
  python scripts/nuke_candidates.py --go     # actually deletes
"""
import asyncio
import sys

from sqlalchemy import text

from app.config import settings
from app.database import async_session_factory
from app.storage.client import minio_client


async def count_all(db) -> dict:
    tables = [
        "job_applications", "candidates", "candidate_job_scores",
        "comparisons", "comparison_results", "candidate_resumes",
        "candidate_evaluations", "candidate_notes",
    ]
    counts = {}
    for t in tables:
        r = await db.execute(text(f"SELECT COUNT(*) FROM {t}"))
        counts[t] = r.scalar()
    return counts


async def nuke(go: bool) -> None:
    async with async_session_factory() as db:
        counts = await count_all(db)
        print("Current counts:")
        for t, c in counts.items():
            print(f"  {t}: {c}")

        total = sum(counts.values())
        if total == 0:
            print("\nNothing to delete.")
            return

        if not go:
            print(f"\nDry-run — {total} rows would be deleted.")
            print("Run with --go to actually delete.")
            return

        print(f"\nDeleting {total} rows…")

        # Collect all file_ids before deleting
        r = await db.execute(text("SELECT resume_file_id FROM job_applications WHERE resume_file_id IS NOT NULL"))
        file_ids = [row[0] for row in r.fetchall()]

        r = await db.execute(text("SELECT file_id FROM candidates WHERE file_id IS NOT NULL"))
        file_ids += [row[0] for row in r.fetchall()]

        r = await db.execute(text("SELECT file_id FROM candidate_resumes WHERE file_id IS NOT NULL"))
        file_ids += [row[0] for row in r.fetchall()]

        file_ids = list(set(file_ids))

        # Delete in FK-safe order
        await db.execute(text("DELETE FROM comparison_results"))
        await db.execute(text("DELETE FROM comparisons"))
        await db.execute(text("DELETE FROM candidate_job_scores"))
        await db.execute(text("DELETE FROM candidate_evaluations"))
        await db.execute(text("DELETE FROM candidate_notes"))
        await db.execute(text("DELETE FROM candidate_resumes"))
        await db.execute(text("DELETE FROM job_applications"))
        await db.execute(text("DELETE FROM candidates"))
        await db.commit()

        print(f"DB cleared. Removing {len(file_ids)} MinIO files…")
        removed = 0
        errors = 0
        for fid in file_ids:
            try:
                minio_client.remove_object(settings.minio_bucket, fid)
                removed += 1
            except Exception as exc:
                errors += 1
                print(f"  MinIO remove failed for {fid}: {exc}")

        print(f"\nDone. DB wiped. MinIO: {removed} removed, {errors} errors.")


if __name__ == "__main__":
    asyncio.run(nuke(go="--go" in sys.argv))
