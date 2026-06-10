import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import Notification

log = structlog.get_logger()


async def create_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    type_: str,
    payload: dict,
) -> None:
    notification = Notification(user_id=user_id, type=type_, payload=payload)
    db.add(notification)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        log.warning("notification.create_failed", user_id=str(user_id), type=type_, exc=str(exc))
        raise
