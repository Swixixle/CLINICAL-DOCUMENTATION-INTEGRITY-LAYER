"""
Migration-only SQLAlchemy engine for Alembic.

This module is intentionally kept separate from the runtime database code so
that introducing Alembic does not require refactoring the existing sqlite3/
psycopg2 connection layer.

Usage (in alembic/env.py):
    from gateway.app.db.alembic_engine import get_engine
    connectable = get_engine()
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def get_database_url() -> str:
    """Return the database URL from the environment.

    Reads DATABASE_URL (e.g. ``postgresql+psycopg2://...`` or
    ``sqlite:///path/to/db.sqlite``).  Raises if not set so that
    misconfigured deployments fail loudly.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is required for Alembic migrations. "
            "Example: DATABASE_URL=postgresql+psycopg2://cdil:cdil@localhost:5432/cdil"
        )
    return url


def get_engine() -> Engine:
    """Create a SQLAlchemy engine from DATABASE_URL (migration use only)."""
    return create_engine(get_database_url())
