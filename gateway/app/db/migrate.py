"""
Database migration utilities.

Simple schema initialization for SQLite MVP.
"""

import sqlite3
from pathlib import Path


def get_db_path() -> Path:
    """Get the path to the SQLite database file."""
    # Store in gateway/app/db directory
    db_dir = Path(__file__).parent
    db_path = db_dir / "eli_sentinel.db"
    return db_path


def ensure_schema():
    """
    Ensure database schema exists.
    
    Creates tables if they don't exist.
    Idempotent - safe to call multiple times.
    """
    db_path = get_db_path()
    schema_path = Path(__file__).parent / "schema.sql"
    
    # Read schema
    with open(schema_path, 'r') as f:
        schema_sql = f.read()
    
    # Execute schema
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()


def get_connection() -> sqlite3.Connection:
    """Get a database connection."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    return conn
