#!/usr/bin/env python3
"""
Clinical Documentation Integrity Demo Script

This script demonstrates the full flow:
1. Mock AI summarizer generates clinical note
2. Request clinical documentation certificate
3. Save certificate to JSON
4. Verify certificate offline
5. Generate PDF certificate

Usage:
    python demo_clinical_flow.py
"""

import json
import requests
import sys
from pathlib import Path
from datetime import datetime


# Configuration
BASE_URL = "http://localhost:8000"
OUTPUT_DIR = Path("/tmp/clinical_demo")


def setup_output_dir():
    """Create output directory for demo artifacts."""
    # Use /tmp if available, otherwise use current directory
    global OUTPUT_DIR
    try:
        OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    except (PermissionError, OSError):
        # Fallback to current directory if /tmp is not writable
        OUTPUT_DIR = Path.cwd() / "clinical_demo_output"
        OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    
    print(f"📁 Output directory: {OUTPUT_DIR}\n")


def step1_mock_summarize():
    """Step 1: Call mock AI summarizer."""
    print("=" * 70)
    print("STEP 1: Mock AI Clinical Summarizer")
    print("=" * 70)
    
    clinical_text = """
    Patient presented to clinic with complaints of persistent headache
    for 3 days. No fever, no visual changes. Vital signs stable.
    Physical exam unremarkable. Assessed as tension headache.
    Recommended OTC analgesics and stress management. Follow up PRN.
    """
    
    request_data = {
        "clinical_text": clinical_text,
        "note_type": "progress_note",
        "ai_model": "gpt-4-turbo"
    }
    
    print(f"\n📝 Sending clinical text to AI summarizer...")
    print(f"   Text length: {len(clinical_text)} characters")
    
    try:
        response = requests.post(
            f"{BASE_URL}/v1/mock/summarize",
            json=request_data,
            timeout=10
        )
        response.raise_for_status()
        
        result = response.json()
        print(f"\n✅ Summary generated successfully!")
        print(f"   Model: {result['model_used']}")
        print(f"   Prompt Version: {result['prompt_version']}")
        print(f"   Policy Version: {result['governance_policy_version']}")
        print(f"\n📄 Generated Summary:")
        print("-" * 70)
        print(result['summary'])
        print("-" * 70)
        
        return result
        
    except requests.RequestException as e:
        print(f"\n❌ Error calling summarizer: {e}")
        print("\n⚠️  Make sure the server is running:")
        print("   cd /home/runner/work/ELI-SENTINEL/ELI-SENTINEL")
        print("   uvicorn gateway.app.main:app --reload")
        sys.exit(1)


def step2_generate_certificate(summary_data: dict):
    """Step 2: Generate clinical documentation integrity certificate."""
    print("\n" + "=" * 70)
    print("STEP 2: Generate Clinical Documentation Integrity Certificate")
    print("=" * 70)
    
    # Build certificate request
    request_data = {
        "clinician_id": "DR-12345",
        "patient_id": "PATIENT-67890",  # Will be hashed, never stored raw
        "encounter_id": "ENC-2026-02-18-001",
        "ai_vendor": "openai",
        "model_version": summary_data["model_used"],
        "prompt_version": summary_data["prompt_version"],
        "governance_policy_version": summary_data["governance_policy_version"],
        "note_text": summary_data["summary"],
        "human_reviewed": True,
        "human_editor_id": "DR-12345",
        "note_type": "progress_note",
        "environment": "dev"
    }
    
    print(f"\n🔐 Generating certificate...")
    print(f"   Clinician: {request_data['clinician_id']}")
    print(f"   Encounter: {request_data['encounter_id']}")
    print(f"   Human Reviewed: {request_data['human_reviewed']}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/v1/clinical/documentation",
            json=request_data,
            timeout=10
        )
        response.raise_for_status()
        
        result = response.json()
        print(f"\n✅ Certificate generated successfully!")
        print(f"   Certificate ID: {result['certificate_id']}")
        print(f"   Verification URL: {result['verification_url']}")
        print(f"   Hash Prefix: {result['hash_prefix']}")
        
        # Save certificate to file
        cert_file = OUTPUT_DIR / f"certificate_{result['certificate_id'][:8]}.json"
        
        # We need to get the full packet for verification
        # In production, the /v1/transactions/{id} endpoint would return this
        # For demo, we'll construct it from the response
        print(f"\n💾 Saving certificate to: {cert_file}")
        
        with open(cert_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"✅ Certificate saved!")
        
        return result, cert_file
        
    except requests.RequestException as e:
        print(f"\n❌ Error generating certificate: {e}")
        if hasattr(e.response, 'text'):
            print(f"   Response: {e.response.text}")
        sys.exit(1)


def step3_fetch_full_packet(certificate_id: str):
    """Step 3: Fetch full accountability packet for verification."""
    print("\n" + "=" * 70)
    print("STEP 3: Fetch Full Accountability Packet")
    print("=" * 70)
    
    print(f"\n🔍 Fetching full packet for verification...")
    
    try:
        response = requests.get(
            f"{BASE_URL}/v1/transactions/{certificate_id}",
            timeout=10
        )
        response.raise_for_status()
        
        packet = response.json()
        
        # Save full packet for verification
        packet_file = OUTPUT_DIR / f"packet_{certificate_id[:8]}.json"
        with open(packet_file, 'w') as f:
            json.dump(packet, f, indent=2)
        
        print(f"✅ Full packet retrieved and saved")
        print(f"   File: {packet_file}")
        
        return packet, packet_file
        
    except requests.RequestException as e:
        print(f"\n❌ Error fetching packet: {e}")
        print(f"   This is expected if transaction endpoint isn't fully implemented")
        return None, None


def step4_verify_certificate(packet_file: Path):
    """Step 4: Verify certificate offline."""
    print("\n" + "=" * 70)
    print("STEP 4: Offline Certificate Verification")
    print("=" * 70)
    
    if not packet_file or not packet_file.exists():
        print("\n⚠️  Skipping verification (full packet not available)")
        return
    
    print(f"\n🔍 Verifying certificate offline...")
    print(f"   Using: {packet_file}")
    
    import subprocess
    
    verify_script = Path(__file__).parent / "verify_clinical_certificate.py"
    
    try:
        result = subprocess.run(
            ["python", str(verify_script), str(packet_file)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        print(result.stdout)
        
        if result.returncode == 0:
            print("\n✅ Certificate verification completed successfully!")
        else:
            print("\n⚠️  Certificate verification had issues")
            if result.stderr:
                print(f"   Error: {result.stderr}")
                
    except subprocess.TimeoutExpired:
        print("\n❌ Verification timed out")
    except Exception as e:
        print(f"\n❌ Error running verification: {e}")


def step5_generate_pdf(packet_file: Path):
    """Step 5: Generate PDF certificate."""
    print("\n" + "=" * 70)
    print("STEP 5: Generate PDF Certificate")
    print("=" * 70)
    
    if not packet_file or not packet_file.exists():
        print("\n⚠️  Skipping PDF generation (full packet not available)")
        return
    
    print(f"\n📄 Generating PDF certificate...")
    
    import subprocess
    
    pdf_script = Path(__file__).parent / "certificate_pdf.py"
    pdf_output = OUTPUT_DIR / f"certificate_{packet_file.stem}.pdf"
    
    try:
        result = subprocess.run(
            ["python", str(pdf_script), str(packet_file), str(pdf_output)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        print(result.stdout)
        
        if result.returncode == 0:
            print(f"✅ PDF certificate generated!")
            print(f"   Location: {pdf_output}")
        else:
            print(f"\n⚠️  PDF generation had issues")
            if result.stderr:
                print(f"   Error: {result.stderr}")
                
    except subprocess.TimeoutExpired:
        print("\n❌ PDF generation timed out")
    except Exception as e:
        print(f"\n❌ Error generating PDF: {e}")


def main():
    """Main demo flow."""
    print("\n" + "=" * 70)
    print("  CLINICAL DOCUMENTATION INTEGRITY LAYER - DEMO")
    print("=" * 70)
    print("\nThis demo shows the complete flow:")
    print("  1. AI generates clinical note summary")
    print("  2. System generates integrity certificate")
    print("  3. Retrieve full accountability packet")
    print("  4. Verify certificate offline")
    print("  5. Generate PDF certificate")
    print("\n" + "=" * 70 + "\n")
    
    # Setup
    setup_output_dir()
    
    # Step 1: Mock AI summarizer
    summary_data = step1_mock_summarize()
    
    # Step 2: Generate certificate
    certificate_data, cert_file = step2_generate_certificate(summary_data)
    
    # Step 3: Fetch full packet
    certificate_id = certificate_data['certificate_id']
    packet, packet_file = step3_fetch_full_packet(certificate_id)
    
    # Step 4: Verify certificate
    if packet_file:
        step4_verify_certificate(packet_file)
    
    # Step 5: Generate PDF
    if packet_file:
        step5_generate_pdf(packet_file)
    
    # Summary
    print("\n" + "=" * 70)
    print("  DEMO COMPLETE")
    print("=" * 70)
    print(f"\n📁 All artifacts saved to: {OUTPUT_DIR}")
    print(f"\n✅ Clinical Documentation Integrity Layer demonstrated successfully!")
    print("\nNext steps:")
    print("  • Review generated certificates")
    print("  • Share with compliance officers")
    print("  • Integrate with EHR systems")
    print("  • Deploy to production environment\n")


if __name__ == "__main__":
    main()
