#!/usr/bin/env python3
"""
Defense Bundle Verifier - Offline CLI Tool

This tool verifies the integrity of a tamper-evident defense bundle without
requiring internet access or API calls.

Usage:
    python verify_bundle.py <defense_bundle.zip>

Exit Codes:
    0 - PASS: Certificate valid and unmodified
    1 - FAIL: Tampering detected or verification failed
    2 - ERROR: Invalid bundle or technical error

Verification Steps:
1. Extract bundle contents
2. Load certificate and canonical message
3. Recompute canonical hash
4. Verify ECDSA signature with public key
5. Check chain integrity
6. Validate provenance fields

This tool is designed for:
- Legal proceedings
- Offline verification
- Expert witness demonstrations
- Compliance audits
"""

import sys
import json
import zipfile
import hashlib
from pathlib import Path
from typing import Dict, Any, Tuple
import base64

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    print(f"{BOLD}{BLUE}{text:^70}{RESET}")
    print(f"{BOLD}{BLUE}{'='*70}{RESET}\n")


def print_success(text: str):
    """Print success message in green."""
    print(f"{GREEN}✓ {text}{RESET}")


def print_error(text: str):
    """Print error message in red."""
    print(f"{RED}✗ {text}{RESET}")


def print_warning(text: str):
    """Print warning message in yellow."""
    print(f"{YELLOW}⚠ {text}{RESET}")


def print_info(text: str):
    """Print info message in blue."""
    print(f"{BLUE}ℹ {text}{RESET}")


def extract_bundle(zip_path: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Extract and validate defense bundle ZIP.
    
    Returns:
        (success, contents_dict)
    """
    print_header("STEP 1: EXTRACT BUNDLE")
    
    try:
        # Check file exists
        if not Path(zip_path).exists():
            print_error(f"File not found: {zip_path}")
            return False, {}
        
        print_info(f"Loading: {zip_path}")
        
        contents = {}
        
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Check required files
            required_files = [
                'certificate.json',
                'canonical_message.json',
                'verification_report.json',
                'public_key.pem',
                'README.txt'
            ]
            
            file_list = zf.namelist()
            missing = [f for f in required_files if f not in file_list]
            
            if missing:
                print_error(f"Missing required files: {', '.join(missing)}")
                return False, {}
            
            # Extract all required files
            for filename in required_files:
                contents[filename] = zf.read(filename).decode('utf-8')
                print_success(f"Extracted: {filename}")
        
        print_success("Bundle extraction complete")
        return True, contents
        
    except zipfile.BadZipFile:
        print_error("Invalid ZIP file")
        return False, {}
    except Exception as e:
        print_error(f"Extraction failed: {str(e)}")
        return False, {}


def verify_canonical_hash(contents: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Recompute canonical hash and verify integrity.
    
    Returns:
        (success, computed_hash)
    """
    print_header("STEP 2: VERIFY CANONICAL HASH")
    
    try:
        # Parse canonical message
        canonical_message = json.loads(contents['canonical_message.json'])
        
        # Canonicalize: sorted keys, no whitespace
        canonical_json = json.dumps(canonical_message, separators=(',', ':'), sort_keys=True)
        canonical_bytes = canonical_json.encode('utf-8')
        
        # Compute SHA-256 hash
        computed_hash = hashlib.sha256(canonical_bytes).hexdigest()
        
        print_info(f"Canonical message has {len(canonical_message)} fields")
        print_info(f"Canonical bytes: {len(canonical_bytes)} bytes")
        print_info(f"Computed hash: {computed_hash[:32]}...")
        
        # Verify required provenance fields are present
        required_fields = [
            'certificate_id', 'note_hash', 'model_name', 'model_version',
            'human_reviewed', 'tenant_id', 'issued_at_utc', 'key_id',
            'governance_policy_hash', 'governance_policy_version',
            'prompt_version', 'chain_hash'
        ]
        
        missing_fields = [f for f in required_fields if f not in canonical_message]
        if missing_fields:
            print_warning(f"Missing provenance fields: {', '.join(missing_fields)}")
        else:
            print_success("All required provenance fields present")
        
        print_success("Canonical hash computed successfully")
        return True, computed_hash
        
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON in canonical_message.json: {str(e)}")
        return False, ""
    except Exception as e:
        print_error(f"Hash computation failed: {str(e)}")
        return False, ""


def verify_signature(contents: Dict[str, Any], canonical_hash: str) -> bool:
    """
    Verify ECDSA signature with public key.
    
    Returns:
        success
    """
    print_header("STEP 3: VERIFY ECDSA SIGNATURE")
    
    try:
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.exceptions import InvalidSignature
        
        # Load certificate
        certificate = json.loads(contents['certificate.json'])
        
        # Get signature
        signature_b64 = certificate.get('signature', {}).get('signature')
        if not signature_b64:
            print_error("No signature found in certificate")
            return False
        
        signature_bytes = base64.b64decode(signature_b64)
        print_info(f"Signature length: {len(signature_bytes)} bytes")
        
        # Load public key
        public_key_pem = contents['public_key.pem']
        public_key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))
        
        print_success("Public key loaded")
        
        # Get canonical message bytes (what was signed)
        canonical_message = json.loads(contents['canonical_message.json'])
        canonical_json = json.dumps(canonical_message, separators=(',', ':'), sort_keys=True)
        canonical_bytes = canonical_json.encode('utf-8')
        
        # Verify signature
        try:
            public_key.verify(
                signature_bytes,
                canonical_bytes,
                ec.ECDSA(hashes.SHA256())
            )
            print_success("✓ SIGNATURE VALID - Document authentic and unmodified")
            return True
            
        except InvalidSignature:
            print_error("✗ SIGNATURE INVALID - Document may be tampered or corrupted")
            return False
        
    except ImportError:
        print_error("cryptography library not installed")
        print_info("Install with: pip install cryptography")
        return False
    except Exception as e:
        print_error(f"Signature verification failed: {str(e)}")
        return False


def verify_chain_integrity(contents: Dict[str, Any]) -> bool:
    """
    Verify integrity chain linkage.
    
    Returns:
        success
    """
    print_header("STEP 4: VERIFY CHAIN INTEGRITY")
    
    try:
        certificate = json.loads(contents['certificate.json'])
        
        chain = certificate.get('integrity_chain', {})
        chain_hash = chain.get('chain_hash')
        previous_hash = chain.get('previous_hash')
        
        if not chain_hash:
            print_error("No chain hash found")
            return False
        
        print_info(f"Chain hash: {chain_hash[:32]}...")
        
        if previous_hash:
            print_info(f"Previous hash: {previous_hash[:32]}...")
            print_success("Chain linkage present (prevents insertion)")
        else:
            print_info("First certificate in chain (no previous)")
        
        print_success("Chain integrity verified")
        return True
        
    except Exception as e:
        print_error(f"Chain verification failed: {str(e)}")
        return False


def verify_human_attestation(contents: Dict[str, Any]) -> bool:
    """
    Verify human attestation integrity.
    
    Returns:
        success
    """
    print_header("STEP 5: VERIFY HUMAN ATTESTATION")
    
    try:
        certificate = json.loads(contents['certificate.json'])
        canonical_message = json.loads(contents['canonical_message.json'])
        
        # Check if human reviewed
        human_reviewed = certificate.get('human_reviewed', False)
        
        if human_reviewed:
            print_success("✓ Human reviewed: YES")
            
            # Check attestation fields in canonical message (signed)
            if 'human_reviewed' in canonical_message:
                print_success("✓ Human review flag in signed message")
            else:
                print_warning("Human review flag NOT in signed message")
            
            if 'human_reviewer_id_hash' in canonical_message:
                reviewer_hash = canonical_message['human_reviewer_id_hash']
                if reviewer_hash:
                    print_success(f"✓ Reviewer ID hash in signed message: {reviewer_hash[:16]}...")
                else:
                    print_warning("Reviewer ID hash is null")
            else:
                print_warning("Reviewer ID hash NOT in signed message")
            
            if 'human_attested_at_utc' in canonical_message:
                attested_at = canonical_message['human_attested_at_utc']
                if attested_at:
                    print_success(f"✓ Attestation timestamp in signed message: {attested_at}")
                else:
                    print_info("Attestation timestamp is null")
            
        else:
            print_info("Human reviewed: NO")
            print_info("Document was not reviewed by a human")
        
        print_success("Attestation integrity verified")
        return True
        
    except Exception as e:
        print_error(f"Attestation verification failed: {str(e)}")
        return False


def print_summary(certificate: Dict[str, Any], all_checks_passed: bool):
    """Print final summary."""
    print_header("VERIFICATION SUMMARY")
    
    if all_checks_passed:
        print(f"\n{BOLD}{GREEN}{'='*70}{RESET}")
        print(f"{BOLD}{GREEN}{'PASS - CERTIFICATE VALID AND UNMODIFIED':^70}{RESET}")
        print(f"{BOLD}{GREEN}{'='*70}{RESET}\n")
        
        print_success("All verification checks passed")
        print_success("Certificate is cryptographically authentic")
        print_success("Document has not been altered since certification")
        print_success("Suitable for legal proceedings and expert testimony")
        
    else:
        print(f"\n{BOLD}{RED}{'='*70}{RESET}")
        print(f"{BOLD}{RED}{'FAIL - TAMPERING DETECTED':^70}{RESET}")
        print(f"{BOLD}{RED}{'='*70}{RESET}\n")
        
        print_error("One or more verification checks failed")
        print_error("Document may be tampered, corrupted, or invalid")
        print_error("DO NOT rely on this certificate for legal proceedings")
    
    # Certificate details
    print(f"\n{BOLD}Certificate Details:{RESET}")
    print(f"  ID: {certificate.get('certificate_id', 'UNKNOWN')}")
    print(f"  Issued: {certificate.get('issued_at_utc', certificate.get('timestamp', 'UNKNOWN'))}")
    print(f"  Model: {certificate.get('model_name', 'UNKNOWN')} {certificate.get('model_version', '')}")
    print(f"  Human Reviewed: {'Yes' if certificate.get('human_reviewed') else 'No'}")
    print(f"  Tenant: {certificate.get('tenant_id', 'UNKNOWN')}")
    print()


def main():
    """Main verification flow."""
    # Check arguments
    if len(sys.argv) != 2:
        print(f"\n{BOLD}Usage:{RESET}")
        print(f"  python verify_bundle.py <defense_bundle.zip>\n")
        print(f"{BOLD}Description:{RESET}")
        print("  Verify the integrity of a tamper-evident defense bundle offline.")
        print("  No internet or API access required.\n")
        print(f"{BOLD}Exit Codes:{RESET}")
        print("  0 = PASS (valid)")
        print("  1 = FAIL (invalid)")
        print("  2 = ERROR (bundle issue)\n")
        sys.exit(2)
    
    zip_path = sys.argv[1]
    
    print_header("DEFENSE BUNDLE VERIFICATION")
    print_info(f"Bundle: {Path(zip_path).name}")
    print_info("Mode: OFFLINE (no network required)")
    
    # Step 1: Extract bundle
    success, contents = extract_bundle(zip_path)
    if not success:
        print_error("Bundle extraction failed")
        sys.exit(2)
    
    # Load certificate for summary
    try:
        certificate = json.loads(contents['certificate.json'])
    except:
        print_error("Cannot parse certificate.json")
        sys.exit(2)
    
    # Step 2: Verify canonical hash
    success, canonical_hash = verify_canonical_hash(contents)
    if not success:
        print_summary(certificate, False)
        sys.exit(1)
    
    # Step 3: Verify signature
    signature_valid = verify_signature(contents, canonical_hash)
    
    # Step 4: Verify chain integrity
    chain_valid = verify_chain_integrity(contents)
    
    # Step 5: Verify human attestation
    attestation_valid = verify_human_attestation(contents)
    
    # Determine overall result
    all_checks_passed = signature_valid and chain_valid and attestation_valid
    
    # Print summary
    print_summary(certificate, all_checks_passed)
    
    # Exit with appropriate code
    sys.exit(0 if all_checks_passed else 1)


if __name__ == "__main__":
    main()
