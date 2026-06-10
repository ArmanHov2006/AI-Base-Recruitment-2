import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.applications.models  # noqa: F401 — registers JobApplication
import app.audit.models  # noqa: F401 — registers AuditLog
import app.candidates.models  # noqa: F401 — registers Candidate with Base.metadata
import app.comparisons.models  # noqa: F401 — registers Comparison, ComparisonResult with Base.metadata
import app.evaluations.models  # noqa: F401 — registers CandidateEvaluation
import app.jobs.models  # noqa: F401 — registers Job with Base.metadata
import app.notes.models  # noqa: F401 — registers CandidateNote
import app.notifications.models  # noqa: F401 — registers Notification
import app.users.models  # noqa: F401 — registers User, RefreshToken, etc.
from alembic import context
from app.config import settings
from app.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
