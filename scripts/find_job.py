
import asyncio

from sqlalchemy import select

from app.database import async_session_factory
from app.jobs.models import Job


async def main():
    async with async_session_factory() as db:
        result = await db.execute(select(Job.id, Job.title).limit(5))
        jobs = result.all()
        for job in jobs:
            print(f"ID: {job.id}, Title: {job.title}")

if __name__ == "__main__":
    asyncio.run(main())
