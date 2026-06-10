import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.security import (
    generate_secure_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.users.email import send_invite_email, send_password_reset_email
from app.users.models import PasswordResetToken, RefreshToken, User, UserInvite, UserRole

log = structlog.get_logger()


async def register_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str | None,
    invite_token: str | None = None,
) -> User:
    existing = await db.execute(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account with this email already exists",
        )

    if not invite_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration requires a valid invite",
        )

    invite_result = await db.execute(
        select(UserInvite).where(UserInvite.token_hash == hash_token(invite_token)).with_for_update()
    )
    invite = invite_result.scalar_one_or_none()
    if invite is None or invite.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or already used invite",
        )
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite has expired",
        )
    if invite.email.lower() != email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite was issued for a different email address",
        )

    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=invite.role,
        is_verified=True,
    )
    db.add(user)
    await db.flush()

    invite.used_at = datetime.now(timezone.utc)

    log.info("auth.register", user_id=str(user.id), email=email, via_invite=bool(invite))
    return user


async def login_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> tuple[User, str]:
    log.info("auth.login_attempt", email=email)
    result = await db.execute(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    # Always verify (even if user not found) to prevent timing-based enumeration
    dummy_hash = "$2b$12$invalidhashpaddingtomakeconsistenttiming000000000000000000"
    candidate_hash = user.hashed_password if user else dummy_hash
    if not verify_password(password, candidate_hash) or user is None:
        log.warning("auth.login_failed", email=email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in",
        )

    raw_token = await _create_refresh_token(db, user)
    await db.commit()
    log.info("auth.login_success", user_id=str(user.id))
    return user, raw_token


async def logout_user(db: AsyncSession, raw_token: str) -> None:
    token_hash = hash_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()
    if rt:
        rt.revoked_at = datetime.now(timezone.utc)
        await db.commit()


async def rotate_refresh_token(
    db: AsyncSession,
    raw_token: str,
) -> tuple[User, str]:
    token_hash = hash_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()

    if rt is None or rt.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked refresh token",
        )
    if rt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    user_result = await db.execute(
        select(User).where(User.id == rt.user_id, User.deleted_at.is_(None))
    )
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )

    # Revoke old token (rotation)
    rt.revoked_at = datetime.now(timezone.utc)
    new_raw = await _create_refresh_token(db, user)
    await db.commit()
    return user, new_raw


async def forgot_password(db: AsyncSession, email: str) -> None:
    result = await db.execute(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    # Always take the same amount of time regardless of whether the user exists
    if user:
        raw_token = generate_secure_token()
        pr_token = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(pr_token)
        await db.commit()
        await send_password_reset_email(email, raw_token)
    else:
        # Constant-time padding so timing doesn't reveal email existence
        await asyncio.sleep(0.1)

    log.info("auth.password_reset_request", email=email)


async def reset_password(
    db: AsyncSession,
    raw_token: str,
    new_password: str,
) -> None:
    token_hash = hash_token(raw_token)
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    pr = result.scalar_one_or_none()
    if pr is None or pr.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or already used reset token",
        )
    if pr.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token expired",
        )

    user_result = await db.execute(select(User).where(User.id == pr.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    pr.used_at = datetime.now(timezone.utc)
    user.hashed_password = hash_password(new_password)
    await db.commit()
    log.info("auth.password_reset", user_id=str(user.id))


async def change_password(
    db: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    user.hashed_password = hash_password(new_password)
    log.info("auth.password_changed", user_id=str(user.id))


async def create_invite(
    db: AsyncSession,
    email: str,
    role: UserRole,
    created_by_id: uuid.UUID,
) -> UserInvite:
    raw_token = generate_secure_token()
    invite = UserInvite(
        email=email.lower(),
        role=role,
        token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.invite_token_expire_hours),
        created_by=created_by_id,
    )
    db.add(invite)
    await db.flush()
    await send_invite_email(email, raw_token, role.value)
    log.info("auth.invite_created", email=email, role=role.value)
    return invite


async def list_invites(db: AsyncSession) -> list[UserInvite]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(UserInvite)
        .where(UserInvite.used_at.is_(None), UserInvite.expires_at > now)
        .order_by(UserInvite.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_invite(db: AsyncSession, invite_id: uuid.UUID) -> None:
    invite = await db.get(UserInvite, invite_id)
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    invite.used_at = datetime.now(timezone.utc)
    log.info("auth.invite_revoked", invite_id=str(invite_id))


async def _create_refresh_token(db: AsyncSession, user: User) -> str:
    raw_token = generate_secure_token()
    rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(rt)
    # Caller is responsible for commit
    return raw_token
