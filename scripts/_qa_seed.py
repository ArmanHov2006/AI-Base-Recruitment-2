"""QA-only throwaway seed: 4 role users on a DELIVERABLE domain so the API
login schema (EmailStr) actually accepts them. Idempotent. Not for commit."""
import asyncio
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, ".")

from app.config import settings
from app.security import hash_password
from app.users.models import User, UserRole

# QA seed users removed to prevent recreation of QA accounts that should be deleted.
USERS = []


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        for email, pw, name, role in USERS:
            r = await db.execute(select(User).where(User.email == email))
            ex = r.scalar_one_or_none()
            if ex:
                ex.hashed_password = hash_password(pw)
                ex.role = role
                ex.is_active = True
                ex.is_verified = True
                ex.deleted_at = None
                act = "updated"
            else:
                db.add(User(id=uuid.uuid4(), email=email, hashed_password=hash_password(pw),
                            full_name=name, role=role, is_active=True, is_verified=True))
                act = "created"
            print(f"[{act}] {role.value:12} {email}  pw: {pw}")
        await db.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
