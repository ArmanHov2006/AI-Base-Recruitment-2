"""Create the first ADMIN user — bypasses email verification.

Usage:
    uv run python scripts/create_admin.py --email admin@ardshinbank.am --password <pass>
"""
import argparse
import asyncio
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, ".")

from app.config import settings
from app.security import hash_password
from app.users.models import User, UserRole


async def main(email: str, password: str, full_name: str) -> None:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        existing = await db.execute(
            select(User).where(User.email == email)
        )
        if existing.scalar_one_or_none():
            print(f"User {email} already exists.")
            return

        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name or "Admin",
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        await db.commit()
        print(f"Admin user created: {email} (id={user.id})")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create admin user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--full-name", default="")
    args = parser.parse_args()
    asyncio.run(main(args.email, args.password, args.full_name))
