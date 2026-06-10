"""Reparse all active candidates: delete them, re-parse their MinIO files, recreate."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.candidates.models import Candidate
from app.config import settings
from scripts._auth import login

API_BASE = "http://localhost:8000"
HEADERS = login(API_BASE)


async def fetch_active_candidates(session) -> list[Candidate]:
    result = await session.execute(
        select(Candidate).where(Candidate.deleted_at.is_(None))
    )
    return list(result.scalars().all())


async def reparse_one(client: httpx.AsyncClient, file_id: str) -> dict | None:
    resp = await client.post(
        f"{API_BASE}/parse",
        json={"file_id": file_id},
        headers=HEADERS,
        timeout=120.0,
    )
    if resp.status_code != 200:
        print(f"  PARSE FAILED ({resp.status_code}): {resp.text}")
        return None
    return resp.json()


async def create_candidate(client: httpx.AsyncClient, file_id: str, data: dict) -> bool:
    payload = {
        "file_id": file_id,
        "name": data.get("name"),
        "email": data.get("email"),
        "phone": data.get("phone"),
        "skills": data.get("skills", []),
        "years_experience": data.get("years_experience"),
        "education": data.get("education", []),
        "work_experiences": data.get("work_experiences", []),
        "location": data.get("location"),
        "seniority": data.get("seniority"),
        "summary": data.get("summary"),
        "desired_position": data.get("desired_position"),
    }
    resp = await client.post(
        f"{API_BASE}/candidates",
        json=payload,
        headers=HEADERS,
        timeout=10.0,
    )
    if resp.status_code not in (200, 201):
        print(f"  CREATE FAILED ({resp.status_code}): {resp.text}")
        return False
    return True


async def soft_delete(session, candidate_id) -> None:
    from datetime import datetime, timezone
    await session.execute(
        update(Candidate)
        .where(Candidate.id == candidate_id)
        .values(deleted_at=datetime.now(timezone.utc))
    )


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        candidates = await fetch_active_candidates(session)

    if not candidates:
        print("No active candidates found.")
        return

    print(f"Found {len(candidates)} active candidate(s) to reparse.\n")

    async with httpx.AsyncClient() as client:
        for c in candidates:
            name = c.name or "(no name)"
            print(f"Processing: {name}  [file_id={c.file_id}]")

            parsed = await reparse_one(client, c.file_id)
            if parsed is None:
                print("  Skipping — parse failed, original record kept.\n")
                continue

            print(f"  Parsed OK — years_experience={parsed.get('years_experience')}, "
                  f"desired_position={parsed.get('desired_position')!r}")

            async with Session() as session:
                await soft_delete(session, c.id)
                await session.commit()

            created = await create_candidate(client, c.file_id, parsed)
            if created:
                print("  Recreated OK.\n")
            else:
                print(f"  Recreate failed — old record was already soft-deleted, "
                      f"check manually for file_id={c.file_id}\n")

    await engine.dispose()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
