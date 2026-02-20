#!/usr/bin/env python3
"""
OpenAPI Drift Detector

Compares the live OpenAPI endpoint list from the running application against
the authoritative endpoint table documented in docs/CONTRACT_SNAPSHOT.md.

Usage:
    python tools/check_openapi_drift.py

Exit Codes:
    0 - No drift detected (OpenAPI matches docs)
    1 - Drift detected (endpoints missing from docs or code)
    2 - Error (could not load app or parse docs)

This script is intended to run in CI to prevent docs from drifting out of
sync with the actual implementation.
"""

import sys
import re
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_openapi_endpoints() -> list[tuple[str, str]]:
    """
    Load the FastAPI app and extract all registered endpoints from OpenAPI.

    Returns:
        Sorted list of (METHOD, path) tuples
    """
    import os
    os.environ.setdefault("ENV", "TEST")
    os.environ.setdefault("DISABLE_RATE_LIMITS", "1")

    from gateway.app.db.migrate import ensure_schema
    from gateway.app.main import app

    ensure_schema()

    # FastAPI's openapi() method generates the schema without a running server
    schema = app.openapi()

    endpoints = []
    for path, methods in schema.get("paths", {}).items():
        for method in methods:
            endpoints.append((method.upper(), path))

    return sorted(endpoints)


def get_docs_endpoints(docs_path: Path) -> list[tuple[str, str]]:
    """
    Parse endpoint table from docs/CONTRACT_SNAPSHOT.md.

    Looks for Markdown table rows of the form:
        | METHOD | /path/to/endpoint | ...

    Returns:
        Sorted list of (METHOD, path) tuples
    """
    content = docs_path.read_text()

    endpoints = []
    # Match table rows with HTTP method and path
    # Pattern: | GET | /v1/something | ...
    row_pattern = re.compile(
        r"^\|\s*(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s*\|\s*(`[^`]+`|[^\|]+)\s*\|",
        re.MULTILINE,
    )

    for match in row_pattern.finditer(content):
        method = match.group(1).upper().strip()
        raw_path = match.group(2).strip().strip("`")
        # Normalize path (strip trailing spaces, backticks)
        path = raw_path.strip()
        if path.startswith("/"):
            endpoints.append((method, path))

    return sorted(set(endpoints))


def main() -> int:
    """Run drift detection and return exit code."""
    docs_path = project_root / "docs" / "CONTRACT_SNAPSHOT.md"

    print("=" * 60)
    print("CDIL OpenAPI Drift Detector")
    print("=" * 60)

    # Load docs endpoints
    if not docs_path.exists():
        print(f"ERROR: {docs_path} not found", file=sys.stderr)
        return 2

    try:
        docs_endpoints = get_docs_endpoints(docs_path)
    except Exception as e:
        print(f"ERROR parsing docs: {e}", file=sys.stderr)
        return 2

    # Load live OpenAPI endpoints
    try:
        live_endpoints = get_openapi_endpoints()
    except Exception as e:
        print(f"ERROR loading app: {e}", file=sys.stderr)
        return 2

    docs_set = set(docs_endpoints)
    live_set = set(live_endpoints)

    in_code_not_docs = live_set - docs_set
    in_docs_not_code = docs_set - live_set

    print(f"\nLive endpoints (from OpenAPI): {len(live_set)}")
    print(f"Documented endpoints (from CONTRACT_SNAPSHOT.md): {len(docs_set)}")

    drift_found = False

    if in_code_not_docs:
        drift_found = True
        print(f"\n[DRIFT] Endpoints in code but NOT in docs ({len(in_code_not_docs)}):")
        for method, path in sorted(in_code_not_docs):
            print(f"  + {method} {path}")

    if in_docs_not_code:
        drift_found = True
        print(f"\n[DRIFT] Endpoints in docs but NOT in code ({len(in_docs_not_code)}):")
        for method, path in sorted(in_docs_not_code):
            print(f"  - {method} {path}")

    if drift_found:
        print(
            "\nDRIFT DETECTED. Update docs/CONTRACT_SNAPSHOT.md to match implementation."
        )
        return 1
    else:
        print("\nNo drift detected. OpenAPI matches CONTRACT_SNAPSHOT.md.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
