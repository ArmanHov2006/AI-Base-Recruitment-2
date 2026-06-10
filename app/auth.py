"""FastAPI security dependencies — imported by all routers."""
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.security import decode_access_token
from app.users.models import User, UserRole

_bearer = HTTPBearer(auto_error=False)

_UNAUTH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing token",
    headers={"WWW-Authenticate": "Bearer"},
)

_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Insufficient permissions",
)

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
    db: DbDep,
) -> User:
    if credentials is None:
        raise _UNAUTH
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError:
        raise _UNAUTH

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise _UNAUTH

    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise _UNAUTH
    request.state.user = user
    return user


def require_role(*roles: UserRole):
    """Returns a FastAPI dependency that checks the current user has one of the given roles."""

    async def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise _FORBIDDEN
        return user

    return _dep


# Convenience shortcuts used by routers
require_admin = require_role(UserRole.ADMIN)
require_write = require_role(UserRole.ADMIN, UserRole.RECRUITER, UserRole.HR_MANAGER)


async def require_job_owner_or_elevated(
    job_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: DbDep,
) -> User:
    """Admin/Recruiter may manage any job; HR_MANAGER only jobs they created."""
    from app.jobs.models import Job  # local import avoids circular dependency
    if user.role not in (UserRole.ADMIN, UserRole.RECRUITER, UserRole.HR_MANAGER):
        raise _FORBIDDEN
    job = await db.get(Job, job_id)
    if job is None or job.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if user.role == UserRole.HR_MANAGER and job.creator_id != user.id:
        raise _FORBIDDEN
    return user
