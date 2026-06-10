
import asyncio

from sqlalchemy import func, select

from app.applications.models import JobApplication
from app.database import async_session_factory


async def main():
    async with async_session_factory() as db:
        result = await db.execute(
            select(JobApplication.status, func.count(JobApplication.id))
            .group_by(JobApplication.status)
        )
        stats = result.all()
        for status, count in stats:
            print(f"Status: {status}, Count: {count}")

if __name__ == "__main__":
    asyncio.run(main())
