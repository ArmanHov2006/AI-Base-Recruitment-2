"""Interview session and answer models — Lane C foundation.

InterviewSession  : one video interview attempt per candidate+job.
InterviewAnswer   : one recording per question within a session.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "pending" | "transcribing" | "scored" | "failed"
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    answers: Mapped[list[InterviewAnswer]] = relationship(
        "InterviewAnswer", back_populates="session", lazy="selectin"
    )


class InterviewAnswer(Base):
    __tablename__ = "interview_answers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # MinIO object key for the raw video/audio recording
    recording_file_id: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # The question prompt shown to the candidate
    question_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Filled by the STT pipeline
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_lang: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Failure tracking
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    session: Mapped[InterviewSession] = relationship(
        "InterviewSession", back_populates="answers"
    )
