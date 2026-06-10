"""Add job/candidate watchers, SLA days, digest preference, emailed_at

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_watchers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "user_id", name="uq_job_watcher"),
    )
    op.create_index("ix_job_watcher_job", "job_watchers", ["job_id"])
    op.create_index("ix_job_watcher_user", "job_watchers", ["user_id"])

    op.create_table(
        "candidate_watchers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "user_id", name="uq_candidate_watcher"),
    )
    op.create_index("ix_candidate_watcher_candidate", "candidate_watchers", ["candidate_id"])
    op.create_index("ix_candidate_watcher_user", "candidate_watchers", ["user_id"])

    op.add_column(
        "users",
        sa.Column("digest_preference", sa.String(10), nullable=False, server_default="instant"),
    )
    op.add_column("jobs", sa.Column("sla_days", sa.Integer(), nullable=True))
    op.add_column(
        "notifications",
        sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notifications", "emailed_at")
    op.drop_column("jobs", "sla_days")
    op.drop_column("users", "digest_preference")
    op.drop_index("ix_candidate_watcher_user", table_name="candidate_watchers")
    op.drop_index("ix_candidate_watcher_candidate", table_name="candidate_watchers")
    op.drop_table("candidate_watchers")
    op.drop_index("ix_job_watcher_user", table_name="job_watchers")
    op.drop_index("ix_job_watcher_job", table_name="job_watchers")
    op.drop_table("job_watchers")
