#!/usr/bin/env python3
"""
CDIL Audit Ledger Integrity Verifier

Cryptographically verifies that the audit_events ledger has not been tampered
with by recomputing each event hash and checking hash-chain linkage.

Exit codes
----------
  0  PASS  – all events verified, chain intact
  1  FAIL  – tampering or chain break detected
  2  ERROR – configuration error, missing DB, missing columns, query error

Output
------
  JSON to stdout (always).  Pass --pretty for indented output.
  Verbose event-by-event progress is written to stderr (--verbose).

Required columns
----------------
  audit_events must have: event_id, occurred_at_utc, object_type, object_id,
  action, event_payload_json, prev_event_hash, event_hash.
  If any are missing the tool exits with code 2.

Ordering
--------
  Events are fetched ORDER BY occurred_at_utc ASC, event_id ASC.
  This ordering is stable, deterministic, and printed in JSON output.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional, Set

# ---------------------------------------------------------------------------
# Import canonical hashing from shared module.
# sys.path is extended so the tool works when run directly from the repo root.
# ---------------------------------------------------------------------------
_repo_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

try:
    from gateway.app.db.ledger_hashing import (
        HASH_POLICY,
        ORDERING,
        compute_event_hash,
        hash_content,  # noqa: F401 – re-exported for tests
    )
except ImportError as _import_err:
    print(
        json.dumps(
            {
                "status": "ERROR",
                "engine": "unknown",
                "ordering": "N/A",
                "hash_policy": "N/A",
                "total_events": 0,
                "verified_events": 0,
                "failure": None,
                "valid": False,
                "errors": [],
                "error": (
                    f"Cannot import gateway.app.db.ledger_hashing: {_import_err}. "
                    "Ensure PYTHONPATH includes the repo root."
                ),
            }
        )
    )
    sys.exit(2)

# Columns the verifier requires from audit_events.
_REQUIRED_COLUMNS: Set[str] = {
    "event_id",
    "occurred_at_utc",
    "object_type",
    "object_id",
    "action",
    "event_payload_json",
    "prev_event_hash",
    "event_hash",
}


# ---------------------------------------------------------------------------
# Column introspection helpers
# ---------------------------------------------------------------------------


def _columns_sqlite(conn: Any, table: str) -> Set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _columns_postgres(cur: Any, table: str) -> Set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (table,),
    )
    return {row[0] for row in cur.fetchall()}


# ---------------------------------------------------------------------------
# Core verifier
# ---------------------------------------------------------------------------


def verify_ledger(
    engine: str,
    db_path: str = "",
    pg_url: str = "",
    tenant_id: Optional[str] = None,
    verbose: bool = False,
) -> tuple[int, Dict[str, Any]]:
    """
    Verify the audit_events ledger.

    Returns (exit_code, result_dict) where exit_code is 0/1/2.
    """
    result: Dict[str, Any] = {
        "status": "ERROR",
        "engine": engine,
        "ordering": ORDERING,
        "hash_policy": HASH_POLICY,
        "total_events": 0,
        "verified_events": 0,
        "failure": None,
        # Backward-compatible fields
        "valid": False,
        "tenant_count": 0,
        "errors": [],
    }

    # ------------------------------------------------------------------
    # 1. Connect and fetch events
    # ------------------------------------------------------------------
    try:
        if engine == "sqlite":
            import sqlite3

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            missing = _REQUIRED_COLUMNS - _columns_sqlite(conn, "audit_events")
            if missing:
                conn.close()
                result["error"] = (
                    f"Missing columns in audit_events (inspected via PRAGMA table_info): "
                    f"{sorted(missing)}"
                )
                return 2, result

            if tenant_id:
                rows = conn.execute(
                    """
                    SELECT event_id, tenant_id, occurred_at_utc, object_type,
                           object_id, action, event_payload_json,
                           prev_event_hash, event_hash
                    FROM audit_events
                    WHERE tenant_id = ?
                    ORDER BY occurred_at_utc ASC, event_id ASC
                    """,
                    (tenant_id,),
                ).fetchall()
            else:
                rows = conn.execute("""
                    SELECT event_id, tenant_id, occurred_at_utc, object_type,
                           object_id, action, event_payload_json,
                           prev_event_hash, event_hash
                    FROM audit_events
                    ORDER BY tenant_id ASC, occurred_at_utc ASC, event_id ASC
                    """).fetchall()
            events = [dict(r) for r in rows]
            conn.close()

        elif engine == "postgres":
            try:
                import psycopg2
                import psycopg2.extras
            except ImportError:
                result["error"] = (
                    "psycopg2 is not installed. "
                    "Install it: pip install psycopg2-binary"
                )
                return 2, result

            conn = psycopg2.connect(pg_url)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            missing = _REQUIRED_COLUMNS - _columns_postgres(cur, "audit_events")
            if missing:
                cur.close()
                conn.close()
                result["error"] = (
                    f"Missing columns in audit_events "
                    f"(inspected via information_schema.columns): "
                    f"{sorted(missing)}"
                )
                return 2, result

            if tenant_id:
                cur.execute(
                    """
                    SELECT event_id, tenant_id, occurred_at_utc, object_type,
                           object_id, action, event_payload_json,
                           prev_event_hash, event_hash
                    FROM audit_events
                    WHERE tenant_id = %s
                    ORDER BY occurred_at_utc ASC, event_id ASC
                    """,
                    (tenant_id,),
                )
            else:
                cur.execute("""
                    SELECT event_id, tenant_id, occurred_at_utc, object_type,
                           object_id, action, event_payload_json,
                           prev_event_hash, event_hash
                    FROM audit_events
                    ORDER BY tenant_id ASC, occurred_at_utc ASC, event_id ASC
                    """)
            events = [dict(r) for r in cur.fetchall()]
            cur.close()
            conn.close()

        else:
            result["error"] = f"Unknown engine: {engine!r}"
            return 2, result

    except Exception as exc:
        result["error"] = f"Query error: {exc}"
        return 2, result

    # ------------------------------------------------------------------
    # 2. Empty ledger is valid
    # ------------------------------------------------------------------
    if not events:
        result.update(
            {
                "status": "PASS",
                "valid": True,
                "total_events": 0,
                "verified_events": 0,
                "tenant_count": 0,
                "errors": [],
                "failure": None,
                "message": "No audit events found",
            }
        )
        return 0, result

    # ------------------------------------------------------------------
    # 3. Verify each event
    # ------------------------------------------------------------------
    tenant_chains: Dict[str, list] = {}
    errors: list = []
    verified_count = 0
    first_failure: Optional[Dict[str, Any]] = None

    for i, event in enumerate(events):
        event_id = event["event_id"]
        tenant = event["tenant_id"]
        timestamp = str(event["occurred_at_utc"])
        obj_type = event["object_type"]
        obj_id = event["object_id"]
        action = event["action"]
        payload_json = event["event_payload_json"]
        prev_hash = event["prev_event_hash"]
        stored_hash = event["event_hash"]

        # Recompute using the shared canonical function
        computed_hash = compute_event_hash(
            prev_hash, timestamp, obj_type, obj_id, action, payload_json
        )

        if computed_hash != stored_hash:
            err: Dict[str, Any] = {
                "event_id": event_id,
                "tenant_id": tenant,
                "index": i,
                "error": "Hash mismatch - event has been tampered with",
                "expected": stored_hash,
                "computed": computed_hash,
                "timestamp": timestamp,
            }
            errors.append(err)
            if first_failure is None:
                first_failure = {
                    "index": i,
                    "event_id": event_id,
                    "reason": "Hash mismatch",
                }
        else:
            verified_count += 1
            if verbose:
                print(
                    f"  \u2713 Event {i + 1}/{len(events)}: "
                    f"{event_id[:8]}... (tenant: {str(tenant)[:8]}...)",
                    file=sys.stderr,
                )

        # Check chain linkage within tenant
        if tenant not in tenant_chains:
            tenant_chains[tenant] = []
        if tenant_chains[tenant]:
            prev_event = tenant_chains[tenant][-1]
            if prev_hash != prev_event["event_hash"]:
                chain_err: Dict[str, Any] = {
                    "event_id": event_id,
                    "tenant_id": tenant,
                    "index": i,
                    "error": "Chain break - previous hash does not match",
                    "prev_hash": str(prev_hash) if prev_hash is not None else None,
                    "expected": prev_event["event_hash"],
                    "timestamp": timestamp,
                }
                errors.append(chain_err)
                if first_failure is None:
                    first_failure = {
                        "index": i,
                        "event_id": event_id,
                        "reason": "Chain break",
                    }
        tenant_chains[tenant].append(
            {
                "event_id": event_id,
                "event_hash": stored_hash,
                "timestamp": timestamp,
            }
        )

    is_valid = len(errors) == 0
    result.update(
        {
            "status": "PASS" if is_valid else "FAIL",
            "valid": is_valid,
            "total_events": len(events),
            "verified_events": verified_count,
            "tenant_count": len(tenant_chains),
            "errors": errors,
            "failure": first_failure,
        }
    )
    return (0 if is_valid else 1), result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CDIL Audit Ledger Integrity Verifier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0  PASS  – ledger intact
  1  FAIL  – tampering or chain break detected
  2  ERROR – configuration / schema / query error
""",
    )
    parser.add_argument(
        "--engine",
        choices=["sqlite", "postgres"],
        default="sqlite",
        help="Database engine (default: sqlite)",
    )
    parser.add_argument(
        "--db",
        default="gateway/app/data/part11.db",
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--pg-url",
        dest="pg_url",
        default="",
        help="PostgreSQL connection URL (or set PGURL env var)",
    )
    parser.add_argument(
        "--tenant",
        default="",
        help="Verify only this tenant ID (default: all tenants)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print event-by-event progress to stderr",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Indent JSON output",
    )
    args = parser.parse_args()

    tenant_id = args.tenant if args.tenant else None
    pg_url = args.pg_url or os.environ.get("PGURL", "")

    exit_code, result = verify_ledger(
        engine=args.engine,
        db_path=args.db,
        pg_url=pg_url,
        tenant_id=tenant_id,
        verbose=args.verbose,
    )

    print(json.dumps(result, indent=2 if args.pretty else None))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
