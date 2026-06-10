"""Notes & notifications: candidate_notes, notifications, analytics status index

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_notes",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_cn_candidate_id", "candidate_notes", ["candidate_id"])
    op.create_index("ix_cn_author_id", "candidate_notes", ["author_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_notif_user_unread", "notifications", ["user_id", "read_at"])

    # Index for analytics GROUP BY queries on application funnel
    op.execute("CREATE INDEX IF NOT EXISTS ix_job_applications_status ON job_applications (status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_job_applications_status")
    op.drop_index("ix_notif_user_unread", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_cn_author_id", table_name="candidate_notes")
    op.drop_index("ix_cn_candidate_id", table_name="candidate_notes")
    op.drop_table("candidate_notes")
