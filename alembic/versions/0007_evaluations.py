"""Evaluations: candidate_evaluations — recruiter scores per candidate/job/stage

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-01
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_evaluations",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("evaluator_id", sa.UUID(), nullable=True),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("overall_rating", sa.Integer(), nullable=True),
        sa.Column("technical_score", sa.Integer(), nullable=True),
        sa.Column("communication_score", sa.Integer(), nullable=True),
        sa.Column("leadership_score", sa.Integer(), nullable=True),
        sa.Column("cultural_fit_score", sa.Integer(), nullable=True),
        sa.Column("english_score", sa.Integer(), nullable=True),
        sa.Column("domain_score", sa.Integer(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("ai_suggested_rating", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evaluator_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "candidate_id", "job_id", "evaluator_id", "stage",
            name="uq_ce_candidate_job_evaluator_stage",
        ),
    )
    op.create_index("ix_ce_candidate_id", "candidate_evaluations", ["candidate_id"])
    op.create_index("ix_ce_job_id", "candidate_evaluations", ["job_id"])
    op.create_index("ix_ce_evaluator_id", "candidate_evaluations", ["evaluator_id"])
    op.create_index("ix_ce_candidate_job", "candidate_evaluations", ["candidate_id", "job_id"])


def downgrade() -> None:
    op.drop_index("ix_ce_candidate_job", table_name="candidate_evaluations")
    op.drop_index("ix_ce_evaluator_id", table_name="candidate_evaluations")
    op.drop_index("ix_ce_job_id", table_name="candidate_evaluations")
    op.drop_index("ix_ce_candidate_id", table_name="candidate_evaluations")
    op.drop_table("candidate_evaluations")
