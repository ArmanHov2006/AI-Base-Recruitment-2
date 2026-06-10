"""Create one test account per role — bypasses email verification.

Idempotent: re-running resets password and re-activates the account.

Usage:
    uv run python scripts/seed_test_users.py
"""
import asyncio
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, ".")

from app.config import settings
from app.security import hash_password
from app.users.models import User, UserRole

# Previously included test users removed to avoid recreating accounts that should be deleted.
TEST_USERS = []


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        for u in TEST_USERS:
            result = await db.execute(
                select(User).where(User.email == u["email"])
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.hashed_password = hash_password(u["password"])
                existing.role = u["role"]
                existing.is_active = True
                existing.is_verified = True
                existing.deleted_at = None
                action = "updated"
            else:
                db.add(User(
                    id=uuid.uuid4(),
                    email=u["email"],
                    hashed_password=hash_password(u["password"]),
                    full_name=u["full_name"],
                    role=u["role"],
                    is_active=True,
                    is_verified=True,
                ))
                action = "created"

            print(f"[{action:7}]  {u['role'].value:12}  {u['email']:30}  password: {u['password']}")

        await db.commit()

    await engine.dispose()
    print("\nDone. Login at http://localhost:8000/auth/login")


if __name__ == "__main__":
    asyncio.run(main())
