from typing import Annotated

import structlog
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import BusinessEventAction
from app.audit.events import record
from app.audit.snapshots import snapshot_user
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.limiter import limiter
from app.security import create_access_token, hash_token
from app.users import service
from app.users.models import User, UserInvite
from app.users.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    InvitePreviewResponse,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
log = structlog.get_logger()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

_COOKIE_MAX_AGE = settings.refresh_token_expire_days * 86400


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=raw_token,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        max_age=_COOKIE_MAX_AGE,
        path="/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key="refresh_token", path="/auth")


@router.get("/invite-preview", response_model=InvitePreviewResponse)
@limiter.limit("10/minute")
async def invite_preview(request: Request, token: str, db: DbDep) -> InvitePreviewResponse:
    from datetime import datetime, timezone

    from sqlalchemy import select
    result = await db.execute(
        select(UserInvite).where(UserInvite.token_hash == hash_token(token))
    )
    invite = result.scalar_one_or_none()
    if not invite or invite.used_at is not None or invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found or expired")
    return InvitePreviewResponse(email=invite.email, role=invite.role)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(request: Request, body: RegisterRequest, db: DbDep) -> UserResponse:
    peer_ip = request.client.host if request.client else None
    xff = request.headers.get("x-forwarded-for", "")
    trusted = set(settings.trusted_proxies)
    client_ip = xff.split(",")[0].strip() if xff and peer_ip in trusted else peer_ip
    user = await service.register_user(db, body.email, body.password, body.full_name, body.invite_token)
    await record(
        db,
        actor_id=None,
        action=BusinessEventAction.USER_REGISTERED,
        resource_type="user",
        resource_id=user.id,
        request_id=getattr(request.state, "request_id", None),
        after=snapshot_user(user),
        meta={"ip": client_ip, "invite_email": body.email},
    )
    await db.commit()
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest, response: Response, db: DbDep) -> TokenResponse:
    user, raw_refresh = await service.login_user(db, body.email, body.password)
    access_token = create_access_token(str(user.id), user.email, user.role.value)
    _set_refresh_cookie(response, raw_refresh)
    return TokenResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: DbDep,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> None:
    if refresh_token:
        await service.logout_user(db, refresh_token)
    _clear_refresh_cookie(response)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_endpoint(
    response: Response,
    db: DbDep,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
        )
    user, new_raw = await service.rotate_refresh_token(db, refresh_token)
    access_token = create_access_token(str(user.id), user.email, user.role.value)
    _set_refresh_cookie(response, new_raw)
    return TokenResponse(access_token=access_token)


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(
    request: Request, body: ForgotPasswordRequest, db: DbDep
) -> dict[str, str]:
    await service.forgot_password(db, body.email)
    return {"message": "If an account with that email exists, a reset link has been sent"}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: DbDep) -> dict[str, str]:
    await service.reset_password(db, body.token, body.new_password)
    return {"message": "Password reset successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.patch("/me/password")
async def change_password(
    request: Request, body: ChangePasswordRequest, user: CurrentUser, db: DbDep
) -> dict[str, str]:
    from datetime import datetime, timezone
    await service.change_password(db, user, body.current_password, body.new_password)
    await record(
        db,
        actor_id=user.id,
        action=BusinessEventAction.USER_PASSWORD_CHANGED,
        resource_type="user",
        resource_id=user.id,
        request_id=getattr(request.state, "request_id", None),
        after=None,
        meta={"changed_at": datetime.now(timezone.utc).isoformat()},
    )
    await db.commit()
    return {"message": "Password changed successfully"}
