#!/usr/bin/env bash
set -euo pipefail

################################################################################
# verify-ledger-integrity.sh
#
# Cryptographically verifies the integrity of the audit event ledger.
# This script validates:
#   1. Each audit event's hash matches its recomputed value
#   2. The hash chain is intact (prev_event_hash linkage)
#   3. No events have been tampered with or deleted
#
# This is a CRITICAL compliance tool for FDA 21 CFR Part 11 audit requirements.
#
# Usage:
#   ./tools/verify-ledger-integrity.sh [OPTIONS]
#
# Options:
#   --engine sqlite|postgres  Database engine (default: sqlite)
#   --db PATH                 Path to SQLite database (default: gateway/app/data/part11.db)
#   --pg-url URL              PostgreSQL connection URL (e.g. postgresql://user:pass@host/db)
#                             Alternatively set PGURL env var.
#   --tenant ID               Verify only specific tenant (default: all tenants)
#   --verbose                 Show detailed event-by-event verification
#   --json                    Output results as JSON
#
# Exit Codes:
#   0  - Ledger integrity verified (PASS)
#   1  - Ledger integrity FAILED (tampering/chain mismatch detected)
#   2  - ERROR (misconfiguration, missing DB, query error)
#   3  - Invalid arguments
#
# Examples:
#   # SQLite (default):
#   ./tools/verify-ledger-integrity.sh --db production.db --tenant tenant_12345
#
#   # Postgres:
#   ./tools/verify-ledger-integrity.sh --engine postgres \
#       --pg-url postgresql://cdil:cdil@localhost/cdil --tenant tenant_12345
#
################################################################################

# Default values
ENGINE="sqlite"
DB_PATH="${DB_PATH:-gateway/app/data/part11.db}"
PG_URL="${PGURL:-}"
TENANT_ID=""
VERBOSE=0
JSON_OUTPUT=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --engine)
            ENGINE="$2"
            if [[ "$ENGINE" != "sqlite" && "$ENGINE" != "postgres" ]]; then
                echo "ERROR: --engine must be 'sqlite' or 'postgres'" >&2
                exit 3
            fi
            shift 2
            ;;
        --db)
            DB_PATH="$2"
            shift 2
            ;;
        --pg-url)
            PG_URL="$2"
            shift 2
            ;;
        --tenant)
            TENANT_ID="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=1
            shift
            ;;
        --json)
            JSON_OUTPUT=1
            shift
            ;;
        -h|--help)
            grep '^#' "$0" | grep -v '#!/usr/bin/env' | sed 's/^# *//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Use --help for usage information" >&2
            exit 3
            ;;
    esac
done

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ERROR: python3 not found. This script requires Python 3.${NC}" >&2
    exit 2
fi

# Validate engine-specific requirements
if [[ "$ENGINE" == "sqlite" ]]; then
    if [[ ! -f "$DB_PATH" ]]; then
        echo -e "${RED}ERROR: Database not found at: $DB_PATH${NC}" >&2
        echo "Use --db to specify the correct path" >&2
        exit 2
    fi
elif [[ "$ENGINE" == "postgres" ]]; then
    if [[ -z "$PG_URL" ]]; then
        echo -e "${RED}ERROR: Postgres engine requires --pg-url or PGURL env var.${NC}" >&2
        exit 2
    fi
fi

# Python verification script — handles both SQLite and Postgres.
# Hash canonicalization is identical to gateway/app/db/part11_operations.py:
#   hash_input = f"{prev_hash or ''}{timestamp}{obj_type}{obj_id}{action}{payload_json}"
#   event_hash = SHA-256(hash_input.encode("utf-8")).hexdigest()
PYTHON_SCRIPT=$(cat <<'EOFPYTHON'
import hashlib
import json
import sys


def hash_content(content: str) -> str:
    """Hash content using SHA-256. Must match part11_operations.py:hash_content()."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def fetch_events(engine, db_path, pg_url, tenant_id):
    """Fetch audit events in strict chronological + stable order."""
    if engine == "sqlite":
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        if tenant_id:
            rows = conn.execute(
                """
                SELECT event_id, tenant_id, occurred_at_utc, object_type, object_id,
                       action, event_payload_json, prev_event_hash, event_hash
                FROM audit_events
                WHERE tenant_id = ?
                ORDER BY occurred_at_utc, event_id
                """,
                (tenant_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT event_id, tenant_id, occurred_at_utc, object_type, object_id,
                       action, event_payload_json, prev_event_hash, event_hash
                FROM audit_events
                ORDER BY tenant_id, occurred_at_utc, event_id
                """,
            ).fetchall()
        events = [dict(r) for r in rows]
        conn.close()
        return events
    elif engine == "postgres":
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError:
            raise RuntimeError(
                "psycopg2 is required for Postgres engine. "
                "Install it: pip install psycopg2-binary"
            )
        conn = psycopg2.connect(pg_url)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if tenant_id:
            cur.execute(
                """
                SELECT event_id, tenant_id, occurred_at_utc, object_type, object_id,
                       action, event_payload_json, prev_event_hash, event_hash
                FROM audit_events
                WHERE tenant_id = %s
                ORDER BY occurred_at_utc, event_id
                """,
                (tenant_id,),
            )
        else:
            cur.execute(
                """
                SELECT event_id, tenant_id, occurred_at_utc, object_type, object_id,
                       action, event_payload_json, prev_event_hash, event_hash
                FROM audit_events
                ORDER BY tenant_id, occurred_at_utc, event_id
                """,
            )
        events = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return events
    else:
        raise RuntimeError(f"Unknown engine: {engine}")


def verify_audit_chain(engine, db_path, pg_url, tenant_id=None, verbose=False):
    """Verify audit event hash chain integrity for SQLite or Postgres."""
    try:
        events = fetch_events(engine, db_path, pg_url, tenant_id)
    except Exception as e:
        return {
            "valid": False,
            "error": f"Query error: {str(e)}",
            "total_events": 0,
            "verified_events": 0,
            "tenant_count": 0,
            "errors": [],
        }

    if not events:
        return {
            "valid": True,
            "total_events": 0,
            "verified_events": 0,
            "tenant_count": 0,
            "errors": [],
            "message": "No audit events found",
        }

    # Per-tenant chain tracking
    tenant_chains = {}
    errors = []
    verified_count = 0

    for i, event in enumerate(events):
        event_id = event["event_id"]
        tenant = event["tenant_id"]
        timestamp = event["occurred_at_utc"]
        obj_type = event["object_type"]
        obj_id = event["object_id"]
        action = event["action"]
        payload_json = event["event_payload_json"]
        prev_hash = event["prev_event_hash"]
        stored_hash = event["event_hash"]

        # Recompute hash — must match part11_operations.py canonicalization
        hash_input = f"{prev_hash or ''}{timestamp}{obj_type}{obj_id}{action}{payload_json}"
        computed_hash = hash_content(hash_input)

        # Verify event hash integrity
        if computed_hash != stored_hash:
            errors.append({
                "event_id": event_id,
                "tenant_id": tenant,
                "index": i,
                "error": "Hash mismatch - event has been tampered with",
                "expected": stored_hash,
                "computed": computed_hash,
                "timestamp": str(timestamp),
            })
        else:
            verified_count += 1
            if verbose:
                print(
                    f"  \u2713 Event {i+1}/{len(events)}: "
                    f"{event_id[:8]}... (tenant: {str(tenant)[:8]}...)",
                    file=sys.stderr,
                )

        # Verify chain linkage within tenant
        if tenant not in tenant_chains:
            tenant_chains[tenant] = []
        if tenant_chains[tenant]:
            prev_event = tenant_chains[tenant][-1]
            if prev_hash != prev_event["event_hash"]:
                errors.append({
                    "event_id": event_id,
                    "tenant_id": tenant,
                    "index": i,
                    "error": "Chain break - previous hash does not match",
                    "prev_hash": str(prev_hash) if prev_hash is not None else None,
                    "expected": prev_event["event_hash"],
                    "timestamp": str(timestamp),
                })
        tenant_chains[tenant].append({
            "event_id": event_id,
            "event_hash": stored_hash,
            "timestamp": str(timestamp),
        })

    return {
        "valid": len(errors) == 0,
        "total_events": len(events),
        "verified_events": verified_count,
        "tenant_count": len(tenant_chains),
        "errors": errors,
    }


if __name__ == "__main__":
    engine = sys.argv[1]
    db_path = sys.argv[2] if len(sys.argv) > 2 else ""
    pg_url = sys.argv[3] if len(sys.argv) > 3 else ""
    tenant_id = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != "" else None
    verbose = sys.argv[5] == "1" if len(sys.argv) > 5 else False
    json_output = sys.argv[6] == "1" if len(sys.argv) > 6 else False

    result = verify_audit_chain(engine, db_path, pg_url, tenant_id, verbose)

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result))
EOFPYTHON
)

# Verbose header (non-JSON mode only)
if [[ $VERBOSE -eq 1 ]] && [[ $JSON_OUTPUT -eq 0 ]]; then
    echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}   AUDIT LEDGER INTEGRITY VERIFICATION${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
    echo -e "Engine:   ${ENGINE}"
    if [[ "$ENGINE" == "sqlite" ]]; then
        echo -e "Database: ${DB_PATH}"
    else
        echo -e "Database: ${PG_URL}"
    fi
    if [[ -n "$TENANT_ID" ]]; then
        echo -e "Tenant:   ${TENANT_ID}"
    else
        echo -e "Tenant:   All tenants"
    fi
    echo -e "${BLUE}────────────────────────────────────────────────────────────────${NC}"
    echo ""
    echo "Verifying audit event chain..."
    echo ""
fi

# Execute Python verification
RESULT=$(python3 -c "$PYTHON_SCRIPT" "$ENGINE" "$DB_PATH" "$PG_URL" "$TENANT_ID" "$VERBOSE" "$JSON_OUTPUT")
PY_EXIT=$?

if [[ $PY_EXIT -ne 0 ]]; then
    echo -e "${RED}ERROR: Verification script exited with code ${PY_EXIT}${NC}" >&2
    exit 2
fi

if [[ $JSON_OUTPUT -eq 1 ]]; then
    echo "$RESULT"
    VALID=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['valid'])")
    if [[ "$VALID" == "True" ]]; then
        exit 0
    else
        exit 1
    fi
else
    # Human-readable output
    VALID=$(echo "$RESULT" | python3 -c "import sys, json; r=json.load(sys.stdin); print(r['valid'])")
    TOTAL=$(echo "$RESULT" | python3 -c "import sys, json; r=json.load(sys.stdin); print(r.get('total_events', 0))")
    VERIFIED=$(echo "$RESULT" | python3 -c "import sys, json; r=json.load(sys.stdin); print(r.get('verified_events', 0))")
    TENANT_COUNT=$(echo "$RESULT" | python3 -c "import sys, json; r=json.load(sys.stdin); print(r.get('tenant_count', 0))")
    ERROR_COUNT=$(echo "$RESULT" | python3 -c "import sys, json; r=json.load(sys.stdin); print(len(r.get('errors', [])))")
    GENERAL_ERROR=$(echo "$RESULT" | python3 -c "import sys, json; r=json.load(sys.stdin); print(r.get('error', ''))")

    if [[ -n "$GENERAL_ERROR" && "$GENERAL_ERROR" != "None" ]]; then
        echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
        echo -e "${RED}   ✗ VERIFICATION FAILED${NC}"
        echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
        echo -e "Error: ${GENERAL_ERROR}"
        echo ""
        exit 2
    fi

    if [[ "$VALID" == "True" ]]; then
        echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
        echo -e "${GREEN}   ✓ LEDGER INTEGRITY VERIFIED${NC}"
        echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
        echo ""
        echo -e "Total Events:     ${GREEN}${TOTAL}${NC}"
        echo -e "Verified Events:  ${GREEN}${VERIFIED}${NC}"
        echo -e "Tenants:          ${GREEN}${TENANT_COUNT}${NC}"
        echo -e "Integrity Status: ${GREEN}INTACT${NC}"
        echo ""
        echo -e "${GREEN}No tampering detected. All audit events are cryptographically valid.${NC}"
        echo ""
        echo -e "This ledger is defensible for regulatory audit."
        echo ""
        exit 0
    else
        echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
        echo -e "${RED}   ✗ LEDGER INTEGRITY VIOLATION DETECTED${NC}"
        echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
        echo ""
        echo -e "Total Events:     ${TOTAL}"
        echo -e "Verified Events:  ${VERIFIED}"
        echo -e "Tenants:          ${TENANT_COUNT}"
        echo -e "Errors Found:     ${RED}${ERROR_COUNT}${NC}"
        echo ""
        echo -e "${RED}⚠ WARNING: The audit ledger has been compromised.${NC}"
        echo ""
        echo "Errors:"
        echo "$RESULT" | python3 -c "
import sys, json
r = json.load(sys.stdin)
for i, err in enumerate(r.get('errors', []), 1):
    print(f\"  {i}. Event: {err.get('event_id', 'unknown')[:16]}...\")
    print(f\"     Error: {err.get('error', 'unknown error')}\")
    if 'timestamp' in err:
        print(f\"     Time: {err['timestamp']}\")
    print()
"
        echo ""
        echo -e "${YELLOW}RECOMMENDED ACTIONS:${NC}"
        echo "  1. Immediately secure the database and investigate unauthorized access"
        echo "  2. Review system access logs for the timeframes of compromised events"
        echo "  3. Notify your compliance officer and security team"
        echo "  4. Restore from the last verified backup if available"
        echo "  5. Document this incident per your breach response procedures"
        echo ""
        exit 1
    fi
fi
