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
#   ./tools/verify-ledger-integrity.sh [--db PATH] [--tenant TENANT_ID]
#
# Options:
#   --db PATH         Path to SQLite database (default: gateway/app/data/part11.db)
#   --tenant ID       Verify only specific tenant (default: all tenants)
#   --verbose         Show detailed event-by-event verification
#   --json            Output results as JSON
#
# Exit Codes:
#   0  - Ledger integrity verified (no tampering detected)
#   1  - Ledger integrity FAILED (tampering detected)
#   2  - Database not found or inaccessible
#   3  - Invalid arguments
#
# Example:
#   ./tools/verify-ledger-integrity.sh --db production.db --tenant tenant_12345
#
################################################################################

# Default values
DB_PATH="${DB_PATH:-gateway/app/data/part11.db}"
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
        --db)
            DB_PATH="$2"
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

# Check if database exists
if [[ ! -f "$DB_PATH" ]]; then
    echo -e "${RED}ERROR: Database not found at: $DB_PATH${NC}" >&2
    echo "Use --db to specify the correct path" >&2
    exit 2
fi

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ERROR: python3 not found. This script requires Python 3.${NC}" >&2
    exit 2
fi

# Create Python script for verification
PYTHON_SCRIPT=$(cat <<'EOFPYTHON'
import sqlite3
import hashlib
import json
import sys

def hash_content(content: str) -> str:
    """Hash content using SHA-256."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def verify_audit_chain(db_path: str, tenant_id: str = None, verbose: bool = False):
    """Verify audit event hash chain integrity."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Build query
        if tenant_id:
            query = """
                SELECT event_id, tenant_id, occurred_at_utc, object_type, object_id, action,
                       event_payload_json, prev_event_hash, event_hash
                FROM audit_events
                WHERE tenant_id = ?
                ORDER BY occurred_at_utc
            """
            cursor.execute(query, (tenant_id,))
        else:
            query = """
                SELECT event_id, tenant_id, occurred_at_utc, object_type, object_id, action,
                       event_payload_json, prev_event_hash, event_hash
                FROM audit_events
                ORDER BY tenant_id, occurred_at_utc
            """
            cursor.execute(query)
        
        events = cursor.fetchall()
        
        if not events:
            return {
                "valid": True,
                "total_events": 0,
                "errors": [],
                "message": "No audit events found"
            }
        
        # Track events per tenant for chain verification
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
            event_hash = event["event_hash"]
            
            # Recompute hash
            hash_input = f"{prev_hash or ''}{timestamp}{obj_type}{obj_id}{action}{payload_json}"
            computed_hash = hash_content(hash_input)
            
            # Check hash integrity
            if computed_hash != event_hash:
                errors.append({
                    "event_id": event_id,
                    "tenant_id": tenant,
                    "index": i,
                    "error": "Hash mismatch - event has been tampered with",
                    "expected": event_hash,
                    "computed": computed_hash,
                    "timestamp": timestamp
                })
            else:
                verified_count += 1
                
                if verbose:
                    print(f"  ✓ Event {i+1}/{len(events)}: {event_id[:8]}... (tenant: {tenant[:8]}...)", file=sys.stderr)
            
            # Initialize tenant chain tracking
            if tenant not in tenant_chains:
                tenant_chains[tenant] = []
            
            # Verify chain linkage for tenant
            if len(tenant_chains[tenant]) > 0:
                prev_event = tenant_chains[tenant][-1]
                if prev_hash != prev_event["event_hash"]:
                    errors.append({
                        "event_id": event_id,
                        "tenant_id": tenant,
                        "index": i,
                        "error": "Chain break - previous hash does not match",
                        "prev_hash": prev_hash,
                        "expected": prev_event["event_hash"],
                        "timestamp": timestamp
                    })
            
            tenant_chains[tenant].append({
                "event_id": event_id,
                "event_hash": event_hash,
                "timestamp": timestamp
            })
        
        conn.close()
        
        return {
            "valid": len(errors) == 0,
            "total_events": len(events),
            "verified_events": verified_count,
            "tenant_count": len(tenant_chains),
            "errors": errors
        }
        
    except sqlite3.Error as e:
        return {
            "valid": False,
            "error": f"Database error: {str(e)}",
            "total_events": 0,
            "errors": []
        }
    except Exception as e:
        return {
            "valid": False,
            "error": f"Unexpected error: {str(e)}",
            "total_events": 0,
            "errors": []
        }

if __name__ == "__main__":
    import sys
    db_path = sys.argv[1]
    tenant_id = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "" else None
    verbose = sys.argv[3] == "1" if len(sys.argv) > 3 else False
    json_output = sys.argv[4] == "1" if len(sys.argv) > 4 else False
    
    result = verify_audit_chain(db_path, tenant_id, verbose)
    
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result))
EOFPYTHON
)

# Run verification
if [[ $VERBOSE -eq 1 ]] && [[ $JSON_OUTPUT -eq 0 ]]; then
    echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}   AUDIT LEDGER INTEGRITY VERIFICATION${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
    echo -e "Database: ${DB_PATH}"
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
RESULT=$(python3 -c "$PYTHON_SCRIPT" "$DB_PATH" "$TENANT_ID" "$VERBOSE" "$JSON_OUTPUT")

if [[ $JSON_OUTPUT -eq 1 ]]; then
    # JSON output mode
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
    
    if [[ -n "$GENERAL_ERROR" ]]; then
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
