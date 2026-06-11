"""Delete specific user accounts from the database permanently.

Usage:
    python scripts/delete_users.py

This connects to the same DB used by the app (settings.database_url) — ensure your
local .env is set up. This will permanently remove the users with the listed
emails.
"""
import asyncio
import sys

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, ".")

from app.config import settings
from app.users.models import User

EMAILS_TO_DELETE = [
    "admin@test.local",
    "hrmanager@test.local",
    "recruiter@test.local",
    "viewer@test.local",
    "admin@airecruitment.com",
    "viewer@example.com",
    "recruiter@example.com",
    "admin@example.com",
    "hrmanager@example.com",
    "qa-admin@example.com",
    "qa.viewer@airecruitment.com",
    "qa.hr@airecruitment.com",
    "qa.recruiter@airecruitment.com",
    "qa.admin@airecruitment.com",
]


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, expire_on_commit=False)

    async with sf() as db:
        stmt = delete(User).where(User.email.in_(EMAILS_TO_DELETE))
        result = await db.execute(stmt)
        # rowcount may be available depending on DB driver
        try:
            deleted = result.rowcount
        except Exception:
            deleted = None
        await db.commit()

    await engine.dispose()
    print(f"Deleted users (rowcount): {deleted}")


if __name__ == "__main__":
    asyncio.run(main())
