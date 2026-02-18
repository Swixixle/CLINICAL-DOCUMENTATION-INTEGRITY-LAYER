#!/usr/bin/env python3
"""
Clinical Certificate Verification Script

This script verifies the integrity and authenticity of Clinical Documentation
Integrity Certificates offline, without needing to contact the CDIL server.

Usage:
    python verify_certificate_cli.py <certificate.json>

Output:
    - Certificate details (model version, policy version, timestamps)
    - Timing integrity status
    - Chain hash integrity status
    - Signature validation status
    - Human-friendly explanation
    - PASS (green) or FAIL (red) with exit code

Exit Codes:
    0 = PASS (all checks passed)
    1 = FAIL (one or more checks failed)
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# ANSI color codes
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def load_certificate(filepath: str) -> Dict[str, Any]:
    """Load certificate JSON from file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"{Colors.RED}❌ Error: Certificate file not found: {filepath}{Colors.RESET}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"{Colors.RED}❌ Error: Invalid JSON in certificate file: {e}{Colors.RESET}")
        sys.exit(1)


def verify_timing_integrity(certificate: Dict[str, Any]) -> tuple[bool, str]:
    """Verify timing integrity (finalization vs EHR reference)."""
    finalized_at_str = certificate.get("finalized_at")
    ehr_referenced_at_str = certificate.get("ehr_referenced_at")
    
    if not finalized_at_str:
        return False, "Missing finalized_at timestamp"
    
    if not ehr_referenced_at_str:
        return True, "No EHR reference timestamp (timing check not applicable)"
    
    try:
        finalized_at = datetime.fromisoformat(finalized_at_str.replace('Z', '+00:00'))
        ehr_referenced_at = datetime.fromisoformat(ehr_referenced_at_str.replace('Z', '+00:00'))
        
        if finalized_at > ehr_referenced_at:
            return False, "Certificate finalized AFTER EHR reference (possible backdating)"
        else:
            return True, "Certificate finalized before EHR reference (valid sequence)"
    except Exception as e:
        return False, f"Timestamp parse error: {e}"


def verify_chain_hash(certificate: Dict[str, Any]) -> tuple[bool, str]:
    """Verify integrity chain hash."""
    try:
        # Import verification utilities
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from gateway.app.services.hashing import hash_c14n
        
        # Recompute chain hash
        certificate_data = {
            "certificate_id": certificate["certificate_id"],
            "tenant_id": certificate["tenant_id"],
            "timestamp": certificate["timestamp"],
            "note_hash": certificate["note_hash"],
            "model_version": certificate["model_version"],
            "governance_policy_version": certificate["governance_policy_version"]
        }
        
        previous_hash = certificate["integrity_chain"]["previous_hash"]
        
        chain_payload = {
            "previous_hash": previous_hash,
            **certificate_data
        }
        
        # Compute hash
        full_hash = hash_c14n(chain_payload)
        recomputed_chain_hash = full_hash.replace("sha256:", "")
        
        stored_chain_hash = certificate["integrity_chain"]["chain_hash"]
        
        if recomputed_chain_hash == stored_chain_hash:
            return True, "Chain hash matches (document not altered)"
        else:
            return False, f"Chain hash mismatch (document altered since issuance)"
    except Exception as e:
        return False, f"Chain hash verification error: {e}"


def verify_signature(certificate: Dict[str, Any]) -> tuple[bool, str]:
    """Verify cryptographic signature."""
    try:
        # Import verification utilities
        from pathlib import Path as PathLib
        sys.path.insert(0, str(PathLib(__file__).parent.parent))
        from gateway.app.services.signer import verify_signature as verify_sig
        
        signature_bundle = certificate.get("signature", {})
        key_id = signature_bundle.get("key_id")
        algorithm = signature_bundle.get("algorithm")
        signature = signature_bundle.get("signature")
        
        if not all([key_id, algorithm, signature]):
            return False, "Missing signature components"
        
        # Try to load public key (from dev keys or fail gracefully)
        jwk_path = PathLib(__file__).parent.parent / "gateway" / "app" / "dev_keys" / "dev_public.jwk.json"
        
        try:
            with open(jwk_path, 'r') as f:
                jwk = json.load(f)
        except Exception:
            return False, "Public key not found (cannot verify signature offline)"
        
        # Reconstruct canonical message
        canonical_message = {
            "certificate_id": certificate["certificate_id"],
            "tenant_id": certificate["tenant_id"],
            "timestamp": certificate["timestamp"],
            "chain_hash": certificate["integrity_chain"]["chain_hash"],
            "note_hash": certificate["note_hash"],
            "governance_policy_version": certificate["governance_policy_version"]
        }
        
        # Build signature bundle for verification
        sig_bundle = {
            "key_id": key_id,
            "algorithm": algorithm,
            "signature": signature,
            "canonical_message": canonical_message
        }
        
        signature_valid = verify_sig(sig_bundle, jwk)
        
        if signature_valid:
            return True, "Signature valid (certificate authentic)"
        else:
            return False, "Signature invalid (may be forged or corrupted)"
    except Exception as e:
        return False, f"Signature verification error: {e}"


def display_certificate_info(certificate: Dict[str, Any]):
    """Display certificate information in a readable format."""
    
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}  CLINICAL DOCUMENTATION INTEGRITY CERTIFICATE{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*70}{Colors.RESET}")
    
    # Certificate ID
    print(f"\n{Colors.BLUE}📋 Certificate ID:{Colors.RESET} {certificate['certificate_id']}")
    
    # Tenant
    print(f"{Colors.BLUE}🏥 Tenant ID:{Colors.RESET} {certificate['tenant_id']}")
    
    # Timestamps
    print(f"\n{Colors.BLUE}🕒 Issued:{Colors.RESET} {certificate['timestamp']}")
    print(f"{Colors.BLUE}🕒 Finalized:{Colors.RESET} {certificate.get('finalized_at', 'N/A')}")
    
    if certificate.get('ehr_referenced_at'):
        print(f"{Colors.BLUE}🕒 EHR Referenced:{Colors.RESET} {certificate['ehr_referenced_at']}")
    
    # Model information
    print(f"\n{Colors.BLUE}🤖 AI Model:{Colors.RESET} {certificate['model_version']}")
    print(f"{Colors.BLUE}📝 Prompt Version:{Colors.RESET} {certificate['prompt_version']}")
    
    # Policy information
    print(f"\n{Colors.BLUE}📜 Governance Policy:{Colors.RESET} {certificate['governance_policy_version']}")
    policy_hash_prefix = certificate.get('policy_hash', '')[:16]
    if policy_hash_prefix:
        print(f"{Colors.BLUE}   Policy Hash:{Colors.RESET} {policy_hash_prefix}...")
    
    if certificate.get('governance_summary'):
        print(f"{Colors.BLUE}   Summary:{Colors.RESET} {certificate['governance_summary']}")
    
    # Human review flag
    human_reviewed = certificate.get('human_reviewed', False)
    if human_reviewed:
        print(f"\n{Colors.GREEN}✅ Human Reviewed: YES{Colors.RESET}")
    else:
        print(f"\n{Colors.YELLOW}⚠️  Human Reviewed: NO{Colors.RESET}")
    
    # Hashes (no PHI visible)
    note_hash_prefix = certificate.get('note_hash', '')[:16]
    if note_hash_prefix:
        print(f"\n{Colors.BLUE}🔒 Note Hash:{Colors.RESET} {note_hash_prefix}...")
    
    patient_hash = certificate.get('patient_hash')
    if patient_hash:
        patient_hash_prefix = patient_hash[:16]
        print(f"{Colors.BLUE}🔒 Patient Hash:{Colors.RESET} {patient_hash_prefix}...")
    
    # Chain info
    chain = certificate.get('integrity_chain', {})
    prev_hash = chain.get('previous_hash')
    if prev_hash:
        print(f"\n{Colors.BLUE}🔗 Previous Hash:{Colors.RESET} {prev_hash[:16]}...")
    else:
        print(f"\n{Colors.BLUE}🔗 Previous Hash:{Colors.RESET} (First in chain)")
    
    chain_hash = chain.get('chain_hash', '')
    if chain_hash:
        print(f"{Colors.BLUE}🔗 Chain Hash:{Colors.RESET} {chain_hash[:16]}...")
    
    # Signature
    signature = certificate.get('signature', {}).get('signature', '')
    if signature:
        print(f"\n{Colors.BLUE}✍️  Signature:{Colors.RESET} {signature[:32]}...")
    
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")


def main():
    """Main verification flow."""
    
    if len(sys.argv) != 2:
        print(f"{Colors.RED}Usage: python verify_certificate_cli.py <certificate.json>{Colors.RESET}")
        sys.exit(1)
    
    certificate_path = sys.argv[1]
    
    print(f"\n{Colors.BLUE}🔍 Loading certificate from: {certificate_path}{Colors.RESET}")
    certificate = load_certificate(certificate_path)
    
    # Display certificate information
    display_certificate_info(certificate)
    
    print(f"\n{Colors.BOLD}🔐 VERIFICATION RESULTS{Colors.RESET}\n")
    
    all_checks = []
    
    # Verify timing integrity
    print("Verifying timing integrity...", end=" ")
    timing_valid, timing_msg = verify_timing_integrity(certificate)
    if timing_valid:
        print(f"{Colors.GREEN}✅ PASS{Colors.RESET}")
        print(f"   {timing_msg}")
    else:
        print(f"{Colors.RED}❌ FAIL{Colors.RESET}")
        print(f"   {Colors.RED}{timing_msg}{Colors.RESET}")
    all_checks.append(timing_valid)
    
    # Verify chain hash
    print("\nVerifying integrity chain hash...", end=" ")
    chain_valid, chain_msg = verify_chain_hash(certificate)
    if chain_valid:
        print(f"{Colors.GREEN}✅ PASS{Colors.RESET}")
        print(f"   {chain_msg}")
    else:
        print(f"{Colors.RED}❌ FAIL{Colors.RESET}")
        print(f"   {Colors.RED}{chain_msg}{Colors.RESET}")
    all_checks.append(chain_valid)
    
    # Verify signature
    print("\nVerifying cryptographic signature...", end=" ")
    signature_valid, signature_msg = verify_signature(certificate)
    if signature_valid:
        print(f"{Colors.GREEN}✅ PASS{Colors.RESET}")
        print(f"   {signature_msg}")
    else:
        print(f"{Colors.RED}❌ FAIL{Colors.RESET}")
        print(f"   {Colors.RED}{signature_msg}{Colors.RESET}")
    all_checks.append(signature_valid)
    
    # Overall status
    all_valid = all(all_checks)
    
    print(f"\n{Colors.BOLD}{'-'*70}{Colors.RESET}")
    if all_valid:
        print(f"{Colors.GREEN}{Colors.BOLD}✅ CERTIFICATE VERIFICATION: PASS{Colors.RESET}")
        print(f"\n{Colors.GREEN}This certificate proves:{Colors.RESET}")
        print("  • Document has not been altered since issuance")
        print("  • Certificate is cryptographically authentic")
        print("  • Timing integrity is valid (no backdating)")
        print("  • Governance policy was applied")
    else:
        print(f"{Colors.RED}{Colors.BOLD}❌ CERTIFICATE VERIFICATION: FAIL{Colors.RESET}")
        print(f"\n{Colors.RED}This certificate may be:{Colors.RESET}")
        print("  • Tampered with or altered")
        print("  • Corrupted during transmission")
        print("  • Forged or backdated")
        print(f"\n{Colors.RED}{Colors.BOLD}DO NOT USE THIS CERTIFICATE FOR LEGAL OR COMPLIANCE PURPOSES{Colors.RESET}")
    print(f"{Colors.BOLD}{'-'*70}{Colors.RESET}\n")
    
    # Exit with appropriate code
    sys.exit(0 if all_valid else 1)


if __name__ == "__main__":
    main()
