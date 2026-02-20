"""
Database migration utilities.

Uses Alembic as the authoritative schema manager for both SQLite (dev/test)
and PostgreSQL (production).  The raw schema.sql / part11_schema.sql files
are retained as human-readable references only; the Alembic baseline migration
is the single source of truth.

DB path resolution:
  1. DATABASE_URL env var  (full SQLAlchemy URL — used for Postgres)
  2. CDIL_DB_PATH env var  (SQLite file path)
  3. Default: /tmp/cdil.db (SQLite)
"""

import sqlite3
import os
import stat
from pathlib import Path


def get_db_path() -> Path:
    """
    Get the path to the SQLite database file.

    Returns the path from CDIL_DB_PATH env var, or /tmp/cdil.db by default.
    When DATABASE_URL is set (Postgres), this function is not used for
    connections — use get_database_url() instead.
    """
    db_path_env = os.getenv("CDIL_DB_PATH")
    if db_path_env:
        return Path(db_path_env)

    # Default to /tmp so the DB is never written inside the source tree.
    return Path("/tmp/cdil.db")


def get_database_url() -> str:
    """
    Return the SQLAlchemy database URL for Alembic / SQLAlchemy usage.

    Priority:
    1. DATABASE_URL environment variable (full URL, supports Postgres)
    2. CDIL_DB_PATH as a SQLite file path
    3. Default SQLite at /tmp/cdil.db
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    return f"sqlite:///{get_db_path()}"


def ensure_db_permissions_secure(db_path: Path):
    """
    Ensure database file has secure permissions (not world-readable).

    Sets permissions to 0600 (owner read/write only).

    Args:
        db_path: Path to database file

    Raises:
        PermissionError: If unable to set secure permissions
    """
    if not db_path.exists():
        return  # File doesn't exist yet

    try:
        # Set to owner read/write only (0600)
        os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception as e:
        raise PermissionError(f"Failed to set secure permissions on database: {e}")


def enable_wal_mode(conn: sqlite3.Connection):
    """
    Enable Write-Ahead Logging (WAL) mode for better concurrency.

    WAL mode provides:
    - Better concurrent read/write performance
    - Atomic commits
    - Better crash recovery

    Args:
        conn: SQLite connection
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.commit()


def ensure_schema():
    """
    Ensure the database schema is at the latest Alembic revision.

    Runs ``alembic upgrade head`` programmatically so that both SQLite
    (dev/test) and PostgreSQL (production) go through the same migration
    path.  This replaces the old executescript(schema.sql) approach and
    eliminates schema drift between environments.

    For SQLite, WAL mode and secure file permissions are applied after
    migrations run.

    Idempotent — safe to call multiple times.
    """
    database_url = get_database_url()

    # Locate alembic.ini relative to the repo root.
    # __file__ is gateway/app/db/migrate.py → repo root is 3 levels up.
    repo_root = Path(__file__).parent.parent.parent.parent
    alembic_ini = repo_root / "alembic.ini"

    from alembic.config import Config
    from alembic import command as alembic_command

    alembic_cfg = Config(str(alembic_ini))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)

    alembic_command.upgrade(alembic_cfg, "head")

    # Apply SQLite-specific hardening after migrations.
    if database_url.startswith("sqlite"):
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        try:
            enable_wal_mode(conn)
        finally:
            conn.close()
        ensure_db_permissions_secure(db_path)


def get_connection() -> sqlite3.Connection:
    """
    Get a SQLite database connection.

    Returns:
        SQLite connection with Row factory enabled.
        Only valid when running against a SQLite backend.
    """
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    return conn


def check_db_security() -> dict:
    """
    Check database security configuration.

    Returns:
        Dictionary with security check results
    """
    db_path = get_db_path()

    results = {
        "db_exists": db_path.exists(),
        "permissions_secure": False,
        "wal_enabled": False,
        "outside_repo": False,
    }

    if not db_path.exists():
        return results

    # Check permissions
    try:
        file_stat = os.stat(db_path)
        mode = stat.S_IMODE(file_stat.st_mode)
        # Check if world-readable or group-readable
        results["permissions_secure"] = (mode & (stat.S_IRGRP | stat.S_IROTH)) == 0
    except Exception:
        pass

    # Check WAL mode
    try:
        conn = get_connection()
        cursor = conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        results["wal_enabled"] = mode.upper() == "WAL"
        conn.close()
    except Exception:
        pass

    # Check if outside repo
    try:
        repo_root = Path(__file__).parent.parent.parent.parent
        results["outside_repo"] = not db_path.is_relative_to(repo_root)
    except Exception:
        pass

    return results
