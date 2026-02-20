#!/usr/bin/env python3
"""
CDIL Audit Ledger Integrity Verifier

Cryptographically verifies that the audit_events ledger has not been tampered
with by recomputing each event hash and checking hash-chain linkage.

Usage:
    python tools/verify_ledger_integrity.py --engine sqlite --db PATH [OPTIONS]
    python tools/verify_ledger_integrity.py --engine postgres --pg-url URL [OPTIONS]

Options:
    --engine sqlite|postgres   Database engine (default: sqlite)
    --db PATH                  Path to SQLite database
    --pg-url URL               PostgreSQL connection URL (or set PGURL env var)
    --tenant ID                Verify only a specific tenant (default: all)
    --verbose                  Print event-by-event verification to stderr
    --json                     Output indented JSON to stdout

Exit codes:
    0  PASS  - ledger is intact
    1  FAIL  - tampering or chain break detected
    2  ERROR - configuration error, missing columns, or query error
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional, Set

# Allow running as `python tools/verify_ledger_integrity.py` without setting
# PYTHONPATH manually: insert the repo root so gateway imports resolve.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from gateway.app.db.ledger_hashing import (
        HASH_POLICY,
        ORDERING,
        compute_event_hash,
        hash_content,  # noqa: F401 - re-exported for tests
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
                "tenant_count": 0,
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
# Database access helpers
# ---------------------------------------------------------------------------


def _fetch_events_sqlite(
    db_path: str, tenant_id: Optional[str]
) -> list[Dict[str, Any]]:
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    missing = _REQUIRED_COLUMNS - _columns_sqlite(conn, "audit_events")
    if missing:
        conn.close()
        raise ValueError(
            f"Missing columns in audit_events (inspected via PRAGMA table_info): "
            f"{sorted(missing)}"
        )

    if tenant_id:
        rows = conn.execute(
            """
            SELECT event_id, tenant_id, occurred_at_utc, object_type, object_id,
                   action, event_payload_json, prev_event_hash, event_hash
            FROM audit_events
            WHERE tenant_id = ?
            ORDER BY occurred_at_utc ASC, event_id ASC
            """,
            (tenant_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT event_id, tenant_id, occurred_at_utc, object_type, object_id,
                   action, event_payload_json, prev_event_hash, event_hash
            FROM audit_events
            ORDER BY tenant_id ASC, occurred_at_utc ASC, event_id ASC
            """,
        ).fetchall()
    events = [dict(r) for r in rows]
    conn.close()
    return events


def _fetch_events_postgres(
    pg_url: str, tenant_id: Optional[str]
) -> list[Dict[str, Any]]:
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as exc:
        raise RuntimeError(
            f"psycopg2 is required for Postgres engine ({exc}). "
            "It is listed in requirements.txt; run: pip install psycopg2-binary"
        ) from exc

    conn = psycopg2.connect(pg_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    missing = _REQUIRED_COLUMNS - _columns_postgres(cur, "audit_events")
    if missing:
        cur.close()
        conn.close()
        raise ValueError(
            f"Missing columns in audit_events "
            f"(inspected via information_schema.columns): "
            f"{sorted(missing)}"
        )

    if tenant_id:
        cur.execute(
            """
            SELECT event_id, tenant_id, occurred_at_utc, object_type, object_id,
                   action, event_payload_json, prev_event_hash, event_hash
            FROM audit_events
            WHERE tenant_id = %s
            ORDER BY occurred_at_utc ASC, event_id ASC
            """,
            (tenant_id,),
        )
    else:
        cur.execute(
            """
            SELECT event_id, tenant_id, occurred_at_utc, object_type, object_id,
                   action, event_payload_json, prev_event_hash, event_hash
            FROM audit_events
            ORDER BY tenant_id ASC, occurred_at_utc ASC, event_id ASC
            """,
        )
    events = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return events


def fetch_events(
    engine: str, db_path: str, pg_url: str, tenant_id: Optional[str]
) -> list[Dict[str, Any]]:
    if engine == "sqlite":
        return _fetch_events_sqlite(db_path, tenant_id)
    elif engine == "postgres":
        return _fetch_events_postgres(pg_url, tenant_id)
    raise RuntimeError(f"Unknown engine: {engine}")


# ---------------------------------------------------------------------------
# Core verification logic
# ---------------------------------------------------------------------------


def verify(
    engine: str,
    db_path: str,
    pg_url: str,
    tenant_id: Optional[str] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Verify audit event hash chain integrity.

    Returns a result dict with keys:
        status          "PASS" | "FAIL" | "ERROR"
        valid           bool (backward-compatible alias for status=="PASS")
        engine          str
        ordering        str
        hash_policy     str
        total_events    int
        verified_events int
        tenant_count    int
        failure         None | {index, reason, event_id}   (first failure only)
        errors          list of all failures
    """
    base: Dict[str, Any] = {
        "engine": engine,
        "ordering": ORDERING,
        "hash_policy": HASH_POLICY,
        "total_events": 0,
        "verified_events": 0,
        "tenant_count": 0,
        "failure": None,
        "valid": False,
        "errors": [],
    }

    try:
        events = fetch_events(engine, db_path, pg_url, tenant_id)
    except ValueError as exc:
        # Missing columns or schema error -> ERROR (exit 2)
        return {**base, "status": "ERROR", "error": str(exc)}
    except Exception as exc:
        return {
            **base,
            "status": "FAIL",
            "errors": [{"error": f"Query error: {exc}"}],
            "failure": {"index": -1, "reason": f"Query error: {exc}", "event_id": None},
        }

    if not events:
        return {
            **base,
            "status": "PASS",
            "valid": True,
            "total_events": 0,
            "verified_events": 0,
            "tenant_count": 0,
        }

    tenant_chains: Dict[str, list[Dict[str, Any]]] = {}
    errors: list[Dict[str, Any]] = []
    verified_count = 0

    for i, event in enumerate(events):
        event_id = str(event["event_id"])
        tenant = str(event["tenant_id"])
        timestamp = str(event["occurred_at_utc"])
        obj_type = str(event["object_type"])
        obj_id = str(event["object_id"])
        action = str(event["action"])
        payload_json = str(event["event_payload_json"])
        prev_hash = event["prev_event_hash"]
        stored_hash = str(event["event_hash"])

        # Recompute using the canonical function from ledger_hashing.py
        computed_hash = compute_event_hash(
            prev_hash, timestamp, obj_type, obj_id, action, payload_json
        )

        if computed_hash != stored_hash:
            errors.append(
                {
                    "event_id": event_id,
                    "tenant_id": tenant,
                    "index": i,
                    "error": "Hash mismatch - event has been tampered with",
                    "expected": stored_hash,
                    "computed": computed_hash,
                    "timestamp": timestamp,
                }
            )
        else:
            verified_count += 1
            if verbose:
                sys.stderr.write(
                    f"  \u2713 Event {i + 1}/{len(events)}: "
                    f"{event_id[:8]}... (tenant: {tenant[:8]}...)\n"
                )

        # Verify chain linkage within this tenant
        if tenant not in tenant_chains:
            tenant_chains[tenant] = []
        chain = tenant_chains[tenant]
        if chain:
            prev_stored = chain[-1]["event_hash"]
            prev_hash_val = prev_hash if prev_hash is not None else None
            if prev_hash_val != prev_stored:
                errors.append(
                    {
                        "event_id": event_id,
                        "tenant_id": tenant,
                        "index": i,
                        "error": "Chain break - previous hash does not match",
                        "prev_hash": str(prev_hash_val) if prev_hash_val else None,
                        "expected": prev_stored,
                        "timestamp": timestamp,
                    }
                )
        chain.append({"event_id": event_id, "event_hash": stored_hash})

    passed = len(errors) == 0
    first_failure = None
    if errors:
        e = errors[0]
        first_failure = {
            "index": e["index"],
            "reason": e["error"],
            "event_id": e["event_id"],
        }

    return {
        **base,
        "status": "PASS" if passed else "FAIL",
        "valid": passed,
        "total_events": len(events),
        "verified_events": verified_count,
        "tenant_count": len(tenant_chains),
        "failure": first_failure,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify CDIL audit ledger integrity (FDA 21 CFR Part 11)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0  PASS  - ledger intact
  1  FAIL  - tampering or chain break detected
  2  ERROR - configuration / schema / query error
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
        help="Verify only this tenant (default: all tenants)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print event-by-event verification to stderr",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output indented JSON to stdout",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    engine = args.engine
    db_path = args.db
    pg_url = args.pg_url or os.environ.get("PGURL", "")
    tenant_id = args.tenant or None

    # Validate configuration
    if engine == "sqlite":
        if not os.path.isfile(db_path):
            sys.stderr.write(f"ERROR: Database not found: {db_path}\n")
            return 2
    elif engine == "postgres":
        if not pg_url:
            sys.stderr.write(
                "ERROR: Postgres engine requires --pg-url or PGURL env var.\n"
            )
            return 2

    result = verify(engine, db_path, pg_url, tenant_id, verbose=args.verbose)

    print(json.dumps(result, indent=2 if args.json_output else None))

    status = result.get("status", "FAIL")
    if status == "PASS":
        return 0
    if status == "ERROR":
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
