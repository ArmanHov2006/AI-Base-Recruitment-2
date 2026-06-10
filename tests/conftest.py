import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from jose import jwt as _jose_jwt

from app.config import settings
from app.security import create_access_token
from app.users.models import User, UserRole


def make_user(role: UserRole) -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = f"{role.value}@test.example"
    user.role = role
    user.is_active = True
    user.deleted_at = None
    return user


def make_mock_db() -> AsyncMock:
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalars.return_value.all.return_value = []
    result.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    return db


def make_valid_token(role: UserRole) -> str:
    return create_access_token(
        user_id=str(uuid.uuid4()),
        email=f"{role.value}@test.example",
        role=role.value,
    )


def make_expired_token(role: UserRole) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid.uuid4()),
        "email": f"{role.value}@expired.example",
        "role": role.value,
        "iat": now - timedelta(hours=1),
        "exp": now - timedelta(minutes=1),
    }
    return _jose_jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def make_bad_sig_token(role: UserRole) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid.uuid4()),
        "email": f"{role.value}@badsig.example",
        "role": role.value,
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return _jose_jwt.encode(
        payload, "wrong-secret-completely-different-x!", algorithm="HS256"
    )
