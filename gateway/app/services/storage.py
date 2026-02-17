"""
Storage service for ELI Sentinel Gateway.

Provides abstraction over SQLite database for storing transactions and keys.
Cleanly designed for future migration to PostgreSQL.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path

from gateway.app.db.migrate import get_connection


def store_transaction(packet: Dict[str, Any]) -> None:
    """
    Store a transaction packet in the database.
    
    Args:
        packet: Complete accountability packet dictionary
    """
    # Extract top-level fields for indexing
    transaction_id = packet["transaction_id"]
    gateway_timestamp_utc = packet["gateway_timestamp_utc"]
    environment = packet["environment"]
    client_id = packet["client_id"]
    feature_tag = packet["feature_tag"]
    policy_version_hash = packet["policy_receipt"]["policy_version_hash"]
    final_hash = packet["halo_chain"]["final_hash"]
    
    # Serialize full packet as JSON (canonical ordering for determinism)
    packet_json = json.dumps(packet, sort_keys=True)
    
    # Current timestamp for created_at
    created_at_utc = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    # Insert into database
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO transactions (
                transaction_id,
                gateway_timestamp_utc,
                environment,
                client_id,
                feature_tag,
                policy_version_hash,
                final_hash,
                packet_json,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            transaction_id,
            gateway_timestamp_utc,
            environment,
            client_id,
            feature_tag,
            policy_version_hash,
            final_hash,
            packet_json,
            created_at_utc
        ))
        conn.commit()
    finally:
        conn.close()


def get_transaction(transaction_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a transaction packet by its ID.
    
    Args:
        transaction_id: Transaction identifier
        
    Returns:
        Complete accountability packet dictionary, or None if not found
    """
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT packet_json
            FROM transactions
            WHERE transaction_id = ?
        """, (transaction_id,))
        
        row = cursor.fetchone()
        if row:
            return json.loads(row["packet_json"])
        return None
    finally:
        conn.close()


def list_keys() -> List[Dict[str, Any]]:
    """
    List all available keys.
    
    Returns:
        List of key dictionaries with key_id, jwk, and status
    """
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT key_id, jwk_json, status
            FROM keys
            ORDER BY created_at_utc DESC
        """)
        
        keys = []
        for row in cursor:
            keys.append({
                "key_id": row["key_id"],
                "jwk": json.loads(row["jwk_json"]),
                "status": row["status"]
            })
        return keys
    finally:
        conn.close()


def get_key(key_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific key by key_id.
    
    Args:
        key_id: Key identifier
        
    Returns:
        Dictionary with key_id, jwk, and status, or None if not found
    """
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT key_id, jwk_json, status
            FROM keys
            WHERE key_id = ?
        """, (key_id,))
        
        row = cursor.fetchone()
        if row:
            return {
                "key_id": row["key_id"],
                "jwk": json.loads(row["jwk_json"]),
                "status": row["status"]
            }
        return None
    finally:
        conn.close()


def store_key(key_id: str, jwk: Dict[str, Any], status: str = "active") -> None:
    """
    Store a public key in the database.
    
    Args:
        key_id: Key identifier
        jwk: JWK public key dictionary
        status: Key status (active/retired)
    """
    jwk_json = json.dumps(jwk, sort_keys=True)
    created_at_utc = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    conn = get_connection()
    try:
        # Use INSERT OR REPLACE to handle re-initialization
        conn.execute("""
            INSERT OR REPLACE INTO keys (
                key_id,
                jwk_json,
                status,
                created_at_utc
            ) VALUES (?, ?, ?, ?)
        """, (key_id, jwk_json, status, created_at_utc))
        conn.commit()
    finally:
        conn.close()


def bootstrap_dev_keys() -> None:
    """
    Bootstrap development keys into the database.
    
    Loads dev_public.jwk.json and inserts it if not already present.
    """
    # Check if dev key already exists
    existing_key = get_key("dev-key-01")
    if existing_key:
        # Already bootstrapped
        return
    
    # Load dev public key
    jwk_path = Path(__file__).parent.parent / "dev_keys" / "dev_public.jwk.json"
    with open(jwk_path, 'r') as f:
        jwk = json.load(f)
    
    # Store in database
    store_key("dev-key-01", jwk, "active")
