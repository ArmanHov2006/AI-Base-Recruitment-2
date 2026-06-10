"""Candidates: full profile table with all fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("file_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="parsed"),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("skills", JSONB(), nullable=False, server_default="[]"),
        sa.Column("years_experience", sa.Float(), nullable=True),
        sa.Column("education", JSONB(), nullable=False, server_default="[]"),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("seniority", sa.String(20), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("work_experiences", JSONB(), nullable=False, server_default="[]"),
        sa.Column("desired_position", sa.Text(), nullable=True),
        sa.Column("certifications", JSONB(), nullable=False, server_default="[]"),
        sa.Column("languages", JSONB(), nullable=False, server_default="[]"),
        sa.Column("linkedin_url", sa.Text(), nullable=True),
        sa.Column("github_url", sa.Text(), nullable=True),
        sa.Column("desired_salary", sa.Integer(), nullable=True),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_candidates_file_id", "candidates", ["file_id"])
    op.create_index("ix_candidates_email", "candidates", ["email"])

    # Unique email among active (non-deleted) candidates only
    op.execute(
        """
        CREATE UNIQUE INDEX uq_candidates_email_active
        ON candidates (email)
        WHERE email IS NOT NULL AND deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("uq_candidates_email_active", table_name="candidates")
    op.drop_index("ix_candidates_email", table_name="candidates")
    op.drop_index("ix_candidates_file_id", table_name="candidates")
    op.drop_table("candidates")
