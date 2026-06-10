import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    required_technical_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    required_soft_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    required_seniority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    threshold_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    candidates_for_next_stage: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    creator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sla_days: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
