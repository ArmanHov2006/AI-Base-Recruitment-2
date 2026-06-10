"""Jobs & applications: jobs, comparisons, comparison_results, job_applications

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Valid statuses for job_applications — keep in sync with app/applications/schemas.py
_APPLICATION_STATUSES = (
    "parsing", "parse_failed", "applied", "reviewing", "shortlisted",
    "screening", "interview", "offer", "hired", "rejected", "withdrawn",
)


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required_skills", JSONB(), nullable=False, server_default="[]"),
        sa.Column("required_technical_skills", JSONB(), nullable=False, server_default="[]"),
        sa.Column("required_soft_skills", JSONB(), nullable=False, server_default="[]"),
        sa.Column("required_seniority", sa.String(20), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("decision_tags", JSONB(), nullable=True),
        sa.Column("creator_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["creator_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_jobs_creator_id", "jobs", ["creator_id"])

    op.create_table(
        "comparisons",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("head_to_head_analysis", sa.Text(), nullable=True),
        sa.Column("verdict", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
    )
    op.create_index("ix_comparisons_job_id", "comparisons", ["job_id"])

    op.create_table(
        "comparison_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("comparison_id", UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", UUID(as_uuid=True), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=True),
        sa.Column("dimension_scores", JSONB(), nullable=False, server_default="{}"),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("skill_breakdown", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["comparison_id"], ["comparisons.id"]),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
    )
    op.create_index("ix_comparison_results_comparison_id", "comparison_results", ["comparison_id"])

    statuses_sql = ", ".join(f"'{s}'" for s in _APPLICATION_STATUSES)
    op.create_table(
        "job_applications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", UUID(as_uuid=True), nullable=True),
        sa.Column("resume_file_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="applied"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("allow_duplicate", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
        sa.UniqueConstraint("candidate_id", "job_id", name="uq_job_applications_candidate_job"),
        sa.CheckConstraint(f"status IN ({statuses_sql})", name="ck_job_applications_status_valid"),
    )
    op.create_index("ix_job_applications_job_id", "job_applications", ["job_id"])
    op.create_index("ix_job_applications_candidate_id", "job_applications", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_job_applications_candidate_id", table_name="job_applications")
    op.drop_index("ix_job_applications_job_id", table_name="job_applications")
    op.drop_table("job_applications")
    op.drop_index("ix_comparison_results_comparison_id", table_name="comparison_results")
    op.drop_table("comparison_results")
    op.drop_index("ix_comparisons_job_id", table_name="comparisons")
    op.drop_table("comparisons")
    op.drop_index("ix_jobs_creator_id", table_name="jobs")
    op.drop_table("jobs")
