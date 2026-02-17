#!/usr/bin/env python3
"""
ELI Sentinel Offline Verifier

Verifies accountability packets without contacting the Sentinel service.
Can be used for audit, compliance, legal discovery, and dispute resolution.

Exit Codes:
    0  - Verification passed
    2  - HALO chain invalid
    3  - Signature invalid
    4  - Key unavailable
    10 - Schema invalid
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from gateway.app.services.halo import verify_halo_chain
from gateway.app.services.signer import verify_signature


def load_json_file(path: str) -> Dict[str, Any]:
    """Load and parse a JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def fetch_jwk(keys_url: Optional[str] = None, jwk_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Fetch JWK from file or URL.
    
    Args:
        keys_url: URL to fetch JWK from (not implemented yet)
        jwk_path: Path to local JWK file
        
    Returns:
        JWK dictionary or None if unavailable
    """
    if jwk_path:
        try:
            return load_json_file(jwk_path)
        except Exception as e:
            print(f"Error loading JWK from {jwk_path}: {e}", file=sys.stderr)
            return None
    
    if keys_url:
        # URL fetching not implemented yet
        print(f"URL fetching not yet implemented: {keys_url}", file=sys.stderr)
        return None
    
    return None


def validate_schema(packet: Dict[str, Any]) -> tuple[bool, List[str]]:
    """
    Validate that packet has required fields.
    
    Args:
        packet: Packet to validate
        
    Returns:
        Tuple of (is_valid, errors)
    """
    errors = []
    
    # Check for halo chain
    if "halo" not in packet:
        errors.append("Missing 'halo' field")
    else:
        halo = packet["halo"]
        if "halo_version" not in halo:
            errors.append("Missing 'halo.halo_version'")
        if "blocks" not in halo:
            errors.append("Missing 'halo.blocks'")
        if "block_hashes" not in halo:
            errors.append("Missing 'halo.block_hashes'")
        if "final_hash" not in halo:
            errors.append("Missing 'halo.final_hash'")
    
    # Check for signature bundle
    if "signature" not in packet:
        errors.append("Missing 'signature' field")
    else:
        sig = packet["signature"]
        if "message" not in sig:
            errors.append("Missing 'signature.message'")
        if "signature_b64" not in sig:
            errors.append("Missing 'signature.signature_b64'")
    
    return len(errors) == 0, errors


def verify_packet(
    packet: Dict[str, Any],
    jwk: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Verify an accountability packet.
    
    Args:
        packet: Full packet dictionary
        jwk: Optional JWK for signature verification
        
    Returns:
        Verification report dictionary
    """
    report = {
        "schema_valid": False,
        "halo_valid": False,
        "signature_valid": False,
        "overall_valid": False,
        "errors": [],
        "warnings": []
    }
    
    # 1. Schema validation
    schema_valid, schema_errors = validate_schema(packet)
    report["schema_valid"] = schema_valid
    if not schema_valid:
        report["errors"].extend(schema_errors)
        return report
    
    # 2. HALO chain verification
    halo = packet.get("halo", {})
    halo_result = verify_halo_chain(halo)
    report["halo_valid"] = halo_result["valid"]
    
    if not halo_result["valid"]:
        report["errors"].append("HALO chain verification failed")
        for disc in halo_result["discrepancies"]:
            report["errors"].append(
                f"  Block {disc['block_index']} {disc['field']}: "
                f"expected {disc['expected']}, got {disc['actual']}"
            )
    
    # 3. Signature verification
    signature_bundle = packet.get("signature", {})
    
    if jwk:
        sig_valid = verify_signature(signature_bundle, jwk)
        report["signature_valid"] = sig_valid
        
        if not sig_valid:
            report["errors"].append("Signature verification failed")
    else:
        report["warnings"].append("No JWK provided - signature not verified")
        report["signature_valid"] = None
    
    # Overall validity
    report["overall_valid"] = (
        report["schema_valid"] and
        report["halo_valid"] and
        (report["signature_valid"] is True or report["signature_valid"] is None)
    )
    
    return report


def format_human_report(report: Dict[str, Any], packet: Dict[str, Any]) -> str:
    """Format verification report for human reading."""
    lines = []
    lines.append("=" * 70)
    lines.append("ELI SENTINEL OFFLINE VERIFICATION REPORT")
    lines.append("=" * 70)
    lines.append("")
    
    # Transaction info
    halo = packet.get("halo", {})
    if halo.get("blocks"):
        block1 = halo["blocks"][0]
        lines.append(f"Transaction ID:  {block1.get('transaction_id', 'N/A')}")
        lines.append(f"Timestamp:       {block1.get('gateway_timestamp_utc', 'N/A')}")
        lines.append(f"Environment:     {block1.get('environment', 'N/A')}")
        lines.append("")
    
    # Results
    lines.append("VERIFICATION RESULTS:")
    lines.append(f"  Schema:     {'✓ PASS' if report['schema_valid'] else '✗ FAIL'}")
    lines.append(f"  HALO Chain: {'✓ PASS' if report['halo_valid'] else '✗ FAIL'}")
    
    if report['signature_valid'] is True:
        lines.append(f"  Signature:  ✓ PASS")
    elif report['signature_valid'] is False:
        lines.append(f"  Signature:  ✗ FAIL")
    else:
        lines.append(f"  Signature:  ⚠ SKIPPED (no key provided)")
    
    lines.append("")
    lines.append(f"OVERALL: {'✓ VALID' if report['overall_valid'] else '✗ INVALID'}")
    
    # Errors
    if report["errors"]:
        lines.append("")
        lines.append("ERRORS:")
        for error in report["errors"]:
            lines.append(f"  • {error}")
    
    # Warnings
    if report["warnings"]:
        lines.append("")
        lines.append("WARNINGS:")
        for warning in report["warnings"]:
            lines.append(f"  • {warning}")
    
    lines.append("")
    lines.append("=" * 70)
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Verify ELI Sentinel accountability packets offline"
    )
    parser.add_argument(
        "--packet",
        required=True,
        help="Path to packet JSON file"
    )
    parser.add_argument(
        "--jwk",
        help="Path to JWK public key file"
    )
    parser.add_argument(
        "--keys-url",
        help="URL to fetch public keys from (not yet implemented)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON report"
    )
    
    args = parser.parse_args()
    
    # Load packet
    try:
        packet = load_json_file(args.packet)
    except Exception as e:
        print(f"Error loading packet: {e}", file=sys.stderr)
        sys.exit(10)
    
    # Load JWK if provided
    jwk = None
    if args.jwk or args.keys_url:
        jwk = fetch_jwk(args.keys_url, args.jwk)
        if not jwk and (args.jwk or args.keys_url):
            print("Error: Could not load JWK", file=sys.stderr)
            sys.exit(4)
    
    # Verify packet
    report = verify_packet(packet, jwk)
    
    # Output report
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_human_report(report, packet))
    
    # Determine exit code
    if not report["schema_valid"]:
        sys.exit(10)
    elif not report["halo_valid"]:
        sys.exit(2)
    elif report["signature_valid"] is False:
        sys.exit(3)
    elif report["overall_valid"]:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
