import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.actions import BusinessEventAction
from app.database import Base


class BusinessEvent(Base):
    __tablename__ = "business_events"

    __table_args__ = (
        Index("ix_bev_resource", "resource_type", "resource_id"),
        Index("ix_bev_actor_time", "actor_id", "created_at"),
        Index("ix_bev_action_time", "action", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


async def record(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: BusinessEventAction,
    resource_type: str,
    resource_id: uuid.UUID,
    request_id: uuid.UUID | None = None,
    before: dict | None = None,
    after: dict | None = None,
    meta: dict | None = None,
) -> None:
    # NOTE: runs in the caller's session — if the handler's transaction rolls
    # back, this event is correctly suppressed (no phantom events for failed ops).
    db.add(
        BusinessEvent(
            actor_id=actor_id,
            action=action.value,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id,
            before=before,
            after=after,
            meta=meta,
        )
    )
