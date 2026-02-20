"""
Alembic migration environment for CDIL.

Supports both SQLite (dev/test) and PostgreSQL (production) via
the DATABASE_URL environment variable or CDIL_DB_PATH for SQLite.

DATABASE_URL takes precedence:
  - postgresql://...  -> Postgres
  - sqlite:///...     -> SQLite (path-explicit)

If DATABASE_URL is not set, falls back to CDIL_DB_PATH env var
(as a SQLite file path), then defaults to /tmp/cdil.db.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Alembic Config object provides access to alembic.ini values.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _get_database_url() -> str:
    """Resolve database URL from Alembic config or environment.

    Priority:
    1. sqlalchemy.url already set in the Alembic Config object
       (injected programmatically by ensure_schema())
    2. DATABASE_URL environment variable (full SQLAlchemy URL)
    3. CDIL_DB_PATH environment variable (SQLite file path)
    4. Default /tmp/cdil.db (SQLite)
    """
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        return configured_url

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    cdil_db_path = os.getenv("CDIL_DB_PATH")
    if cdil_db_path:
        return f"sqlite:///{cdil_db_path}"

    return "sqlite:////tmp/cdil.db"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a live connection)."""
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (with a live DB connection)."""
    url = _get_database_url()

    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=None,
            # SQLite does not support transactional DDL natively;
            # render_as_batch allows ALTER TABLE emulation.
            render_as_batch=url.startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
