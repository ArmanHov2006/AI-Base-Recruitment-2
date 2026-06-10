"""Add threshold_score and candidates_for_next_stage to jobs

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-02

Adds pipeline analytics config to the jobs table:
- threshold_score: float 0-10, qualifying bar for candidates
- candidates_for_next_stage: int, interview target count
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("threshold_score", sa.Float(), nullable=True))
    op.add_column("jobs", sa.Column("candidates_for_next_stage", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "candidates_for_next_stage")
    op.drop_column("jobs", "threshold_score")
