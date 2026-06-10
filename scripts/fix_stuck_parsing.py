"""
Find applications stuck in 'parsing' status and either report or reset them.

Usage:
  python scripts/fix_stuck_parsing.py          # list stuck applications
  python scripts/fix_stuck_parsing.py --fix    # reset stuck → parse_failed + requeue
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.applications.models import JobApplication
from app.database import async_session_factory


async def main(fix: bool = False) -> None:
    # Anything stuck in 'parsing' for more than 10 minutes is abandoned
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)

    async with async_session_factory() as db:
        result = await db.execute(
            select(JobApplication).where(
                JobApplication.status == "parsing",
                JobApplication.updated_at < cutoff,
                JobApplication.deleted_at.is_(None),
            )
        )
        stuck = result.scalars().all()

        if not stuck:
            print("No stuck applications found.")
            return

        print(f"Found {len(stuck)} stuck application(s):\n")
        for app in stuck:
            print(f"  id={app.id}  job_id={app.job_id}  file_id={app.resume_file_id}  updated={app.updated_at}")

        if not fix:
            print("\nRun with --fix to reset these to parse_failed and requeue.")
            return

        print("\nResetting and requeueing…")
        from app.worker.tasks import apply_pipeline_task

        for app in stuck:
            app.status = "parsing"
            app.error_message = None
            app.updated_at = datetime.now(timezone.utc)

        await db.commit()

        for app in stuck:
            apply_pipeline_task.delay(str(app.id))
            print(f"  Requeued {app.id}")

        print("Done.")


if __name__ == "__main__":
    asyncio.run(main(fix="--fix" in sys.argv))
