"""Create interview_sessions and interview_answers tables, add interview_session_id to candidate_evaluations

Revision ID: 0034
Revises: 0033
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interview_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="created"),
        sa.Column(
            "questions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("access_token", sa.String(512), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_text_version", sa.String(20), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["job_applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("access_token"),
    )
    op.create_index("ix_interview_sessions_application_id", "interview_sessions", ["application_id"])
    op.create_index("ix_interview_sessions_candidate_id", "interview_sessions", ["candidate_id"])
    op.create_index("ix_interview_sessions_job_id", "interview_sessions", ["job_id"])

    op.create_table(
        "interview_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("recording_file_id", sa.String(512), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("mime", sa.String(50), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("transcript_lang", sa.String(10), nullable=True, server_default="en"),
        sa.Column("video_purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["interview_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_answers_session_id", "interview_answers", ["session_id"])

    op.add_column(
        "candidate_evaluations",
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_ce_interview_session_id",
        "candidate_evaluations",
        "interview_sessions",
        ["interview_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ce_interview_session_id",
        "candidate_evaluations",
        ["interview_session_id"],
    )
    op.create_index(
        "ix_ce_ai_interview_unique",
        "candidate_evaluations",
        ["candidate_id", "job_id", "stage"],
        unique=True,
        postgresql_where=sa.text("stage = 'ai_interview' AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_ce_ai_interview_unique", table_name="candidate_evaluations")
    op.drop_index("ix_ce_interview_session_id", table_name="candidate_evaluations")
    op.drop_constraint("fk_ce_interview_session_id", "candidate_evaluations", type_="foreignkey")
    op.drop_column("candidate_evaluations", "interview_session_id")
    op.drop_index("ix_interview_answers_session_id", table_name="interview_answers")
    op.drop_table("interview_answers")
    op.drop_index("ix_interview_sessions_job_id", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_candidate_id", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_application_id", table_name="interview_sessions")
    op.drop_table("interview_sessions")
