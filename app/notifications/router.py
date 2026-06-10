import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import async_session_factory, get_db
from app.notifications.models import Notification
from app.notifications.schemas import NotificationListResponse, NotificationResponse
from app.security import decode_access_token
from app.users.models import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    db: DbDep,
    current_user: Annotated[User, Depends(get_current_user)],
    unread: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
) -> NotificationListResponse:
    q = select(Notification).where(Notification.user_id == current_user.id)
    if unread:
        q = q.where(Notification.read_at.is_(None))
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()

    unread_count_result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
        )
    )
    unread_count = unread_count_result.scalar_one()

    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in rows],
        unread_count=unread_count,
    )


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(get_current_user)],
) -> NotificationResponse:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found"
        )
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(notification)
    return NotificationResponse.model_validate(notification)


@router.get("/stream")
async def notification_stream(
    token: str = Query(...),
) -> StreamingResponse:
    try:
        payload = decode_access_token(token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    async def event_generator():
        last_count = -1
        tick = 0
        while True:
            try:
                async with async_session_factory() as db:
                    result = await db.execute(
                        select(func.count())
                        .select_from(Notification)
                        .where(
                            Notification.user_id == user_id,
                            Notification.read_at.is_(None),
                        )
                    )
                    count = result.scalar_one()

                if count != last_count:
                    last_count = count
                    yield f"data: {count}\n\n"
                elif tick % 6 == 0:
                    yield ": keep-alive\n\n"

                tick += 1
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception:
                log.warning("sse.poll_failed", extra={"user_id": str(user_id)}, exc_info=True)
                await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    db: DbDep,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc))
    )
    await db.commit()
