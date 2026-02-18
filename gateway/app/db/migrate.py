"""
Database migration utilities.

Simple schema initialization for SQLite MVP with security hardening.
"""

import sqlite3
import os
import stat
from pathlib import Path


def get_db_path() -> Path:
    """
    Get the path to the SQLite database file.
    
    In production, this should be outside the repo and mounted from secure storage.
    For MVP, we store in a data directory with restricted permissions.
    """
    # Check for environment variable first (production)
    db_path_env = os.getenv("CDIL_DB_PATH")
    if db_path_env:
        return Path(db_path_env)
    
    # Default: store in gateway/app/db directory
    db_dir = Path(__file__).parent
    db_path = db_dir / "eli_sentinel.db"
    return db_path


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
    Ensure database schema exists with security hardening.
    
    Creates tables if they don't exist.
    Enables WAL mode for better concurrency.
    Sets secure file permissions.
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
        # Enable WAL mode
        enable_wal_mode(conn)
        
        # Execute schema
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()
    
    # Set secure file permissions
    ensure_db_permissions_secure(db_path)


def get_connection() -> sqlite3.Connection:
    """
    Get a database connection.
    
    Returns:
        SQLite connection with Row factory enabled
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
        "outside_repo": False
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
