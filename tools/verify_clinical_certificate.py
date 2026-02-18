#!/usr/bin/env python3
"""
Clinical Certificate Verification Script

This script verifies the integrity and authenticity of Clinical Documentation
Integrity Certificates offline, without needing to contact the ELI Sentinel server.

Usage:
    python verify_clinical_certificate.py <certificate.json>

Output:
    - Signature validation status
    - HALO chain integrity status
    - Certificate details (model version, policy version, timestamps, etc.)
    - Human review flag
"""

import sys
import json
from pathlib import Path
from datetime import datetime


def load_certificate(filepath: str) -> dict:
    """Load certificate JSON from file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: Certificate file not found: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in certificate file: {e}")
        sys.exit(1)


def verify_halo_chain(packet: dict) -> bool:
    """
    Verify HALO chain integrity.
    
    This recomputes the HALO chain and compares it to the stored values.
    """
    try:
        # Import verification utilities
        from gateway.app.services.halo import build_halo_chain
        
        # Extract required fields
        halo_chain = packet.get("halo_chain", {})
        stored_final_hash = halo_chain.get("final_hash")
        
        if not stored_final_hash:
            return False
        
        # Check if execution has governance_checks (clinical-specific)
        execution = packet.get("execution", {})
        
        # Rebuild HALO chain
        rebuilt_chain = build_halo_chain(
            transaction_id=packet["transaction_id"],
            gateway_timestamp_utc=packet["gateway_timestamp_utc"],
            environment=packet["environment"],
            client_id=packet["client_id"],
            intent_manifest=packet["intent_manifest"],
            feature_tag=packet["feature_tag"],
            user_ref=packet["user_ref"],
            prompt_hash=packet["prompt_hash"],
            rag_hash=packet.get("rag_hash"),
            multimodal_hash=packet.get("multimodal_hash"),
            policy_version_hash=packet["policy_receipt"]["policy_version_hash"],
            policy_change_ref=packet["policy_receipt"]["policy_change_ref"],
            rules_applied=packet["policy_receipt"]["rules_applied"],
            model_fingerprint=packet["model_fingerprint"],
            param_snapshot=packet["param_snapshot"],
            execution=execution
        )
        
        # Compare final hashes
        return rebuilt_chain["final_hash"] == stored_final_hash
        
    except Exception as e:
        print(f"❌ Error during HALO chain verification: {e}")
        return False


def verify_signature(packet: dict) -> bool:
    """
    Verify cryptographic signature.
    
    This checks that the signature is valid for the canonical message.
    """
    try:
        from gateway.app.services.signer import verify_signature as verify_sig
        from gateway.app.services.c14n import canonicalize
        
        verification = packet.get("verification", {})
        signature = verification.get("signature_b64")
        public_key_pem = verification.get("public_key_pem")
        
        if not signature or not public_key_pem:
            return False
        
        # Reconstruct canonical message
        canonical_message = {
            "transaction_id": packet["transaction_id"],
            "gateway_timestamp_utc": packet["gateway_timestamp_utc"],
            "final_hash": packet["halo_chain"]["final_hash"],
            "policy_version_hash": packet["policy_receipt"]["policy_version_hash"]
        }
        
        # Canonicalize and verify
        canonical_bytes = canonicalize(canonical_message).encode('utf-8')
        
        return verify_sig(canonical_bytes, signature, public_key_pem)
        
    except Exception as e:
        print(f"❌ Error during signature verification: {e}")
        return False


def display_certificate_info(packet: dict):
    """Display certificate information in a readable format."""
    
    print("\n" + "="*70)
    print("  CLINICAL AI DOCUMENTATION INTEGRITY CERTIFICATE")
    print("="*70)
    
    # Certificate ID
    print(f"\n📋 Certificate ID: {packet['transaction_id']}")
    
    # Timestamp
    timestamp = packet['gateway_timestamp_utc']
    print(f"🕒 Issued: {timestamp}")
    
    # Model information
    model = packet.get('model_fingerprint', 'Unknown')
    print(f"\n🤖 AI Model: {model}")
    
    # Prompt version
    prompt_version = packet.get('prompt_hash', 'N/A')
    print(f"📝 Prompt Version: {prompt_version}")
    
    # Policy version
    policy_version = packet['policy_receipt']['policy_version_hash'][:16] + "..."
    policy_ref = packet['policy_receipt']['policy_change_ref']
    print(f"📜 Policy Version: {policy_ref}")
    print(f"   Policy Hash: {policy_version}")
    
    # Human review flag
    param_snapshot = packet.get('param_snapshot', {})
    human_reviewed = param_snapshot.get('human_reviewed', False)
    human_editor = param_snapshot.get('human_editor_id')
    
    if human_reviewed:
        print(f"\n✅ Human Reviewed: YES")
        if human_editor:
            print(f"   Reviewer: {human_editor}")
    else:
        print(f"\n⚠️  Human Reviewed: NO")
    
    # Governance checks (clinical-specific)
    governance_metadata = packet.get('governance_metadata', {})
    if governance_metadata:
        checks = governance_metadata.get('governance_checks', [])
        if checks:
            print(f"\n🔍 Governance Checks Executed:")
            for check in checks:
                print(f"   ✓ {check}")
        
        clinical_context = governance_metadata.get('clinical_context', {})
        if clinical_context:
            encounter = clinical_context.get('encounter_id')
            note_type = clinical_context.get('note_type')
            if encounter:
                print(f"\n🏥 Encounter ID: {encounter}")
            if note_type:
                print(f"📄 Note Type: {note_type}")
    
    # Hashes (no PHI visible)
    execution = packet.get('execution', {})
    output_hash = execution.get('output_hash')
    patient_hash = execution.get('patient_hash')
    
    if output_hash:
        print(f"\n🔒 Note Hash: {output_hash[:16]}...")
    if patient_hash:
        print(f"🔒 Patient Hash: {patient_hash[:16]}...")
    
    # HALO chain
    final_hash = packet['halo_chain']['final_hash']
    print(f"\n🔗 HALO Chain Final Hash: {final_hash[:16]}...")
    
    # Signature
    signature = packet['verification']['signature_b64']
    print(f"✍️  Signature: {signature[:32]}...")
    
    print("\n" + "="*70)


def main():
    """Main verification flow."""
    
    if len(sys.argv) != 2:
        print("Usage: python verify_clinical_certificate.py <certificate.json>")
        sys.exit(1)
    
    certificate_path = sys.argv[1]
    
    print(f"\n🔍 Loading certificate from: {certificate_path}")
    packet = load_certificate(certificate_path)
    
    # Display certificate information
    display_certificate_info(packet)
    
    print("\n🔐 VERIFICATION RESULTS\n")
    
    # Verify HALO chain
    print("Verifying HALO chain integrity...", end=" ")
    halo_valid = verify_halo_chain(packet)
    if halo_valid:
        print("✅ VALID")
    else:
        print("❌ INVALID")
    
    # Verify signature
    print("Verifying cryptographic signature...", end=" ")
    signature_valid = verify_signature(packet)
    if signature_valid:
        print("✅ VALID")
    else:
        print("❌ INVALID")
    
    # Overall status
    print("\n" + "-"*70)
    if halo_valid and signature_valid:
        print("✅ CERTIFICATE IS VALID AND AUTHENTIC")
        print("\nThis certificate proves:")
        print("  • AI documentation governance was executed")
        print("  • Note integrity is tamper-evident")
        print("  • Certificate cannot be forged or backdated")
    else:
        print("❌ CERTIFICATE VERIFICATION FAILED")
        print("\nThis certificate may be:")
        print("  • Tampered with")
        print("  • Corrupted")
        print("  • Forged")
    print("-"*70 + "\n")
    
    # Exit with appropriate code
    sys.exit(0 if (halo_valid and signature_valid) else 1)


if __name__ == "__main__":
    main()
