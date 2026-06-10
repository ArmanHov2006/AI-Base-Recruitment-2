"""Observability: audit_log (HTTP-level) and business_events (semantic-level)

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-01

Two complementary audit tables:
  - audit_log     — every write request (method, path, status_code, ip)
  - business_events — semantic actions (what changed, before/after JSONB)
  Linked by request_id so an HTTP entry can be correlated to its semantic effect.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_created_at", "audit_log", [sa.text("created_at DESC")])

    op.create_table(
        "business_events",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=False),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
        sa.Column("request_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_bev_created_at", "business_events", ["created_at"])
    op.create_index("ix_bev_resource", "business_events", ["resource_type", "resource_id"])
    op.create_index("ix_bev_actor_time", "business_events", ["actor_id", "created_at"])
    op.create_index("ix_bev_action_time", "business_events", ["action", "created_at"])
    op.create_index("ix_bev_request_id", "business_events", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_bev_request_id", table_name="business_events")
    op.drop_index("ix_bev_action_time", table_name="business_events")
    op.drop_index("ix_bev_actor_time", table_name="business_events")
    op.drop_index("ix_bev_resource", table_name="business_events")
    op.drop_index("ix_bev_created_at", table_name="business_events")
    op.drop_table("business_events")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index("ix_audit_log_user_id", table_name="audit_log")
    op.drop_table("audit_log")
