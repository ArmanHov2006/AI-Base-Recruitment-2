"""AI scoring: candidate_job_scores — per-candidate AI scores for each job

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_job_scores",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("dimension_scores", JSONB(), nullable=False, server_default="{}"),
        sa.Column("skill_breakdown", JSONB(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("model_tag", sa.String(100), nullable=False),
        # SHA-256 hash of scoring inputs — used to skip re-scoring unchanged candidates
        sa.Column("score_input_hash", sa.String(64), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
        sa.UniqueConstraint("job_id", "candidate_id", name="uq_candidate_job_scores_job_candidate"),
    )
    # Composite index supports leaderboard query: ORDER BY overall_score DESC for a given job
    op.create_index(
        "ix_cjs_job_score",
        "candidate_job_scores",
        ["job_id", sa.text("overall_score DESC NULLS LAST")],
    )


def downgrade() -> None:
    op.drop_index("ix_cjs_job_score", table_name="candidate_job_scores")
    op.drop_table("candidate_job_scores")
