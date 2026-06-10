"""Add resume_language to candidates

Revision ID: 0032
Revises: 0031
Create Date: 2026-06-03

Stores the detected language of the candidate's resume as an ISO 639-1 code
("hy", "ru", "en", or "unknown").  Used for filtering, debugging, and
choosing appropriate search analyzers (F5 multi-language support).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0032"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column("resume_language", sa.String(10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidates", "resume_language")
