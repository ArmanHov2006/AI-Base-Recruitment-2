"""Delete all users and create one test account per role.

Usage:
    uv run python scripts/reset_users.py
"""
import asyncio
import sys
import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, ".")

from app.config import settings
from app.security import hash_password
from app.users.models import User, UserRole

NEW_USERS = [
    {
        "email": "armanhov.c@gmail.com",
        "password": "Password1234!",
        "full_name": "Admin",
        "role": UserRole.ADMIN,
    },
]


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        # 1. Delete all existing users
        # Note: Foreign keys in notifications and user_invites are CASCADE.
        # Others like audit_log and candidate_notes are SET NULL.
        print("Deleting all current users...")
        await db.execute(delete(User))
        
        # 2. Create new users
        for u in NEW_USERS:
            db.add(User(
                id=uuid.uuid4(),
                email=u["email"],
                hashed_password=hash_password(u["password"]),
                full_name=u["full_name"],
                role=u["role"],
                is_active=True,
                is_verified=True,
            ))
            print(f"[CREATED]  {u['role'].value:12}  {u['email']:30}  password: {u['password']}")

        await db.commit()

    await engine.dispose()
    print("\nDone. Users reset successfully.")


if __name__ == "__main__":
    asyncio.run(main())
