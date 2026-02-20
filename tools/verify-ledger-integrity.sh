#!/usr/bin/env bash
set -euo pipefail

################################################################################
# verify-ledger-integrity.sh
#
# Cryptographically verifies the integrity of the audit event ledger.
# This script is a thin wrapper around tools/verify_ledger_integrity.py, which
# imports the canonical hash logic from gateway/app/db/ledger_hashing.py.
# There is exactly ONE place in the codebase where event_hash canonicalization
# is defined.
#
# Usage:
#   ./tools/verify-ledger-integrity.sh [OPTIONS]
#
# Options:
#   --engine sqlite|postgres  Database engine (default: sqlite)
#   --db PATH                 Path to SQLite database (default: gateway/app/data/part11.db)
#   --pg-url URL              PostgreSQL connection URL
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
# FDA 21 CFR Part 11 compliance verification tool.
################################################################################

# Locate the repository root so Python imports resolve regardless of cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

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

# Locate the standalone Python verifier
VERIFIER="${SCRIPT_DIR}/verify_ledger_integrity.py"
if [[ ! -f "$VERIFIER" ]]; then
    echo -e "${RED}ERROR: Verifier not found: ${VERIFIER}${NC}" >&2
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

# Build Python verifier arguments
PY_ARGS=("--engine" "$ENGINE" "--db" "$DB_PATH")
[[ -n "$PG_URL" ]]    && PY_ARGS+=("--pg-url" "$PG_URL")
[[ -n "$TENANT_ID" ]] && PY_ARGS+=("--tenant" "$TENANT_ID")
[[ $VERBOSE -eq 1 ]]  && PY_ARGS+=("--verbose")

# Verbose header (non-JSON mode only)
if [[ $VERBOSE -eq 1 ]] && [[ $JSON_OUTPUT -eq 0 ]]; then
    echo -e "${BLUE}================================================================${NC}"
    echo -e "${BLUE}   AUDIT LEDGER INTEGRITY VERIFICATION${NC}"
    echo -e "${BLUE}================================================================${NC}"
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
    echo -e "${BLUE}----------------------------------------------------------------${NC}"
    echo ""
    echo "Verifying audit event chain..."
    echo ""
fi

# Execute Python verifier -- always outputs JSON to stdout; verbose goes to stderr.
# Disable set -e temporarily so non-zero exit from verifier does not kill the script.
set +e
RESULT=$(python3 "${VERIFIER}" "${PY_ARGS[@]}")
PY_EXIT=$?
set -e

if [[ $JSON_OUTPUT -eq 1 ]]; then
    echo "$RESULT"
    exit "$PY_EXIT"
fi

# Exit code 2 = ERROR from the verifier
if [[ $PY_EXIT -eq 2 ]]; then
    GENERAL_ERROR=$(echo "$RESULT" | python3 -c "import sys, json; r=json.load(sys.stdin); print(r.get('error', 'Unknown error'))" 2>/dev/null || echo "$RESULT")
    echo -e "${RED}================================================================${NC}"
    echo -e "${RED}   ERROR: VERIFICATION FAILED${NC}"
    echo -e "${RED}================================================================${NC}"
    echo -e "Error: ${GENERAL_ERROR}"
    echo ""
    exit 2
fi

# Parse JSON for human-readable output
VALID=$(echo "$RESULT"        | python3 -c "import sys, json; r=json.load(sys.stdin); print(r['valid'])")
TOTAL=$(echo "$RESULT"        | python3 -c "import sys, json; r=json.load(sys.stdin); print(r.get('total_events', 0))")
VERIFIED=$(echo "$RESULT"     | python3 -c "import sys, json; r=json.load(sys.stdin); print(r.get('verified_events', 0))")
TENANT_COUNT=$(echo "$RESULT" | python3 -c "import sys, json; r=json.load(sys.stdin); print(r.get('tenant_count', 0))")
ERROR_COUNT=$(echo "$RESULT"  | python3 -c "import sys, json; r=json.load(sys.stdin); print(len(r.get('errors', [])))")

if [[ "$VALID" == "True" ]]; then
    echo -e "${GREEN}================================================================${NC}"
    echo -e "${GREEN}   LEDGER INTEGRITY VERIFIED${NC}"
    echo -e "${GREEN}================================================================${NC}"
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
    echo -e "${RED}================================================================${NC}"
    echo -e "${RED}   LEDGER INTEGRITY VIOLATION DETECTED${NC}"
    echo -e "${RED}================================================================${NC}"
    echo ""
    echo -e "Total Events:     ${TOTAL}"
    echo -e "Verified Events:  ${VERIFIED}"
    echo -e "Tenants:          ${TENANT_COUNT}"
    echo -e "Errors Found:     ${RED}${ERROR_COUNT}${NC}"
    echo ""
    echo -e "${RED}WARNING: The audit ledger has been compromised.${NC}"
    echo ""
    echo "Errors:"
    echo "$RESULT" | python3 -c "
import sys, json
r = json.load(sys.stdin)
for i, err in enumerate(r.get('errors', []), 1):
    print(f'  {i}. Event: {err.get(\"event_id\", \"unknown\")[:16]}...')
    print(f'     Error: {err.get(\"error\", \"unknown error\")}')
    if 'timestamp' in err:
        print(f'     Time: {err[\"timestamp\"]}')
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
