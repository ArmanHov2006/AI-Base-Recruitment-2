import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import BusinessEventAction
from app.audit.events import record
from app.audit.snapshots import snapshot_invite, snapshot_user
from app.auth import require_admin
from app.database import get_db
from app.users import service as user_service
from app.users.models import User, UserInvite
from app.users.schemas import (
    InviteRequest,
    InviteResponse,
    UpdateActiveRequest,
    UpdateRoleRequest,
    UserAdminResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminUser = Annotated[User, Depends(require_admin)]


@router.get("", response_model=list[UserAdminResponse])
async def list_users(
    _: AdminUser,
    db: DbDep,
) -> list[UserAdminResponse]:
    result = await db.execute(
        select(User).where(User.deleted_at.is_(None)).order_by(User.created_at)
    )
    return [UserAdminResponse.model_validate(u) for u in result.scalars().all()]


@router.patch("/{user_id}/role", response_model=UserAdminResponse)
async def update_user_role(
    request: Request,
    user_id: uuid.UUID,
    body: UpdateRoleRequest,
    current_user: AdminUser,
    db: DbDep,
) -> UserAdminResponse:
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change your own role",
        )
    user = await db.get(User, user_id)
    if not user or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    _before = snapshot_user(user)
    old_role: str = _before.get("role", "unknown")
    user.role = body.role
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.USER_ROLE_CHANGED,
        resource_type="user",
        resource_id=user_id,
        request_id=getattr(request.state, "request_id", None),
        before=_before,
        after=snapshot_user(user),
    )
    await db.commit()
    await db.refresh(user)
    try:
        from app.notifications.service import create_notification
        await create_notification(
            db,
            user.id,
            "role_changed",
            {
                "old_role": old_role,
                "new_role": user.role.value,
                "changed_by": current_user.email,
            },
        )
    except Exception:
        logger.warning(
            "notification.role_changed.failed",
            extra={"user_id": str(user.id), "old_role": old_role, "new_role": user.role.value},
            exc_info=True,
        )
    return UserAdminResponse.model_validate(user)


@router.post("/invites", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
async def create_invite(
    request: Request,
    body: InviteRequest,
    current_user: AdminUser,
    db: DbDep,
) -> InviteResponse:
    invite = await user_service.create_invite(db, body.email, body.role, current_user.id)
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.INVITE_CREATED,
        resource_type="invite",
        resource_id=invite.id,
        request_id=getattr(request.state, "request_id", None),
        after=snapshot_invite(invite),
    )
    await db.commit()
    return InviteResponse.model_validate(invite)


@router.get("/invites", response_model=list[InviteResponse])
async def list_invites(
    _: AdminUser,
    db: DbDep,
) -> list[InviteResponse]:
    invites = await user_service.list_invites(db)
    return [InviteResponse.model_validate(i) for i in invites]


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(
    request: Request,
    invite_id: uuid.UUID,
    current_user: AdminUser,
    db: DbDep,
) -> None:
    invite = await db.get(UserInvite, invite_id)
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    _before = snapshot_invite(invite)
    await user_service.revoke_invite(db, invite_id)
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.INVITE_REVOKED,
        resource_type="invite",
        resource_id=invite_id,
        request_id=getattr(request.state, "request_id", None),
        before=_before,
    )
    await db.commit()


@router.patch("/{user_id}/active", response_model=UserAdminResponse)
async def update_user_active(
    request: Request,
    user_id: uuid.UUID,
    body: UpdateActiveRequest,
    current_user: AdminUser,
    db: DbDep,
) -> UserAdminResponse:
    user = await db.get(User, user_id)
    if not user or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    _before = snapshot_user(user)
    user.is_active = body.is_active
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.USER_ACTIVE_CHANGED,
        resource_type="user",
        resource_id=user_id,
        request_id=getattr(request.state, "request_id", None),
        before=_before,
        after=snapshot_user(user),
    )
    await db.commit()
    await db.refresh(user)
    try:
        from app.notifications.service import create_notification
        await create_notification(
            db,
            user.id,
            "account_status_changed",
            {
                "is_active": user.is_active,
                "changed_by": current_user.email,
            },
        )
    except Exception:
        logger.warning(
            "notification.account_status_changed.failed",
            extra={"user_id": str(user.id), "is_active": user.is_active},
            exc_info=True,
        )
    return UserAdminResponse.model_validate(user)
