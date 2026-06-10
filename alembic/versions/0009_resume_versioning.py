"""Resume versioning: candidate_resumes table + current_resume_version on candidates

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-01

Tracks every resume file uploaded per candidate. Each row is an immutable
snapshot (file_id + version number). The candidates.current_resume_version
pointer identifies which version is active.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_resumes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("candidate_id", "version", name="uq_candidate_resumes_candidate_version"),
    )
    op.create_index("ix_candidate_resumes_candidate_id", "candidate_resumes", ["candidate_id"])

    op.add_column(
        "candidates",
        sa.Column("current_resume_version", sa.Integer(), nullable=True, server_default="1"),
    )

    # Backfill: seed version-1 row from each existing candidate's file_id
    op.execute(
        """
        INSERT INTO candidate_resumes (candidate_id, file_id, version, parsed_at, created_at)
        SELECT id, file_id, 1, created_at, created_at
        FROM candidates
        WHERE deleted_at IS NULL
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_column("candidates", "current_resume_version")
    op.drop_index("ix_candidate_resumes_candidate_id", table_name="candidate_resumes")
    op.drop_table("candidate_resumes")
