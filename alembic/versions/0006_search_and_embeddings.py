"""Search & embeddings: pg_trgm fuzzy search indexes + pgvector semantic search

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-01

Installs two PostgreSQL extensions and adds all candidate search indexes:
  - pg_trgm  — fuzzy text search on name and location; GIN on skills array
  - vector   — 768-dim embedding column with IVFFlat cosine index (lists=100,
               suitable for up to ~1M candidates)
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Fuzzy text search ---
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidates_name_trgm ON candidates USING gin (name gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidates_location_trgm ON candidates USING gin (location gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidates_skills_gin ON candidates USING gin (skills)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidates_seniority ON candidates (seniority)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidates_years_exp ON candidates (years_experience)")

    # --- Semantic / vector search ---
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS embedding vector(768)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_candidates_embedding_ivfflat "
        "ON candidates USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_candidates_embedding_ivfflat")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS embedding")
    # NOTE: dropping the vector extension affects all databases on this PostgreSQL
    # instance. Remove the line below and drop manually if other consumers exist.
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute("DROP INDEX IF EXISTS ix_candidates_years_exp")
    op.execute("DROP INDEX IF EXISTS ix_candidates_seniority")
    op.execute("DROP INDEX IF EXISTS ix_candidates_skills_gin")
    op.execute("DROP INDEX IF EXISTS ix_candidates_location_trgm")
    op.execute("DROP INDEX IF EXISTS ix_candidates_name_trgm")
