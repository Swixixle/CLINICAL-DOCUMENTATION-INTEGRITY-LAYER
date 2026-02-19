"""
Tests for Courtroom Defense Mode - Phase 4: Offline CLI Verifier.

Tests:
- CLI tool can verify valid defense bundles
- CLI tool detects tampered bundles
- CLI tool returns correct exit codes
- CLI tool works offline (no network required)
"""

import pytest
import subprocess
import tempfile
from pathlib import Path
import shutil
from fastapi.testclient import TestClient

from gateway.app.main import app
from gateway.app.db.migrate import ensure_schema
from gateway.app.services.storage import bootstrap_dev_keys
from gateway.tests.auth_helpers import create_clinician_headers


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
    import gateway.app.db.migrate as migrate_module
    original_get_db_path = migrate_module.get_db_path
    
    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "test.db"
    
    migrate_module.get_db_path = lambda: temp_db_path
    ensure_schema()
    bootstrap_dev_keys()
    
    yield temp_db_path
    
    migrate_module.get_db_path = original_get_db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def client(test_db):
    """Test client with test database."""
    return TestClient(app)


def issue_and_get_defense_bundle(client, tenant_id="hospital-alpha"):
    """Helper to issue certificate and get defense bundle."""
    # Issue certificate
    request_data = {
        "model_name": "gpt-4",
        "model_version": "2024-01-15",
        "prompt_version": "clinical-v1.0",
        "governance_policy_version": "CDOC-v1",
        "note_text": "Patient presents with headache. Vital signs stable.",
        "human_reviewed": True,
        "human_reviewer_id": "DR-TEST-001",
        "encounter_id": "ENC-TEST-001"
    }
    
    headers = create_clinician_headers(tenant_id)
    cert_response = client.post("/v1/clinical/documentation", json=request_data, headers=headers)
    assert cert_response.status_code == 200
    cert_id = cert_response.json()["certificate_id"]
    
    # Get defense bundle
    bundle_response = client.get(f"/v1/certificates/{cert_id}/defense-bundle", headers=headers)
    assert bundle_response.status_code == 200
    
    return bundle_response.content


def test_cli_verifier_passes_valid_bundle(client):
    """
    Test that CLI verifier returns exit code 0 for valid bundle.
    """
    # Get defense bundle
    bundle_bytes = issue_and_get_defense_bundle(client)
    
    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.zip', delete=False) as f:
        temp_path = f.name
        f.write(bundle_bytes)
    
    try:
        # Run CLI verifier
        result = subprocess.run(
            ['python3', 'tools/verify_bundle.py', temp_path],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent  # Project root
        )
        
        # Should pass (exit code 0)
        assert result.returncode == 0
        
        # Check output
        assert "PASS" in result.stdout
        assert "CERTIFICATE VALID" in result.stdout or "valid" in result.stdout.lower()
        
    finally:
        # Cleanup
        Path(temp_path).unlink(missing_ok=True)


def test_cli_verifier_detects_tampered_bundle(client):
    """
    Test that CLI verifier returns exit code 1 for tampered bundle.
    """
    import zipfile
    from io import BytesIO
    import json
    
    # Get defense bundle
    bundle_bytes = issue_and_get_defense_bundle(client)
    
    # Tamper with the bundle by modifying canonical_message.json
    tampered_buffer = BytesIO()
    
    with zipfile.ZipFile(BytesIO(bundle_bytes), 'r') as zf_in:
        with zipfile.ZipFile(tampered_buffer, 'w', zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.infolist():
                data = zf_in.read(item.filename)
                
                if item.filename == 'canonical_message.json':
                    # Tamper: change note_hash
                    canonical = json.loads(data.decode('utf-8'))
                    canonical['note_hash'] = "TAMPERED_HASH_VALUE"
                    data = json.dumps(canonical, indent=2).encode('utf-8')
                
                zf_out.writestr(item, data)
    
    tampered_bytes = tampered_buffer.getvalue()
    
    # Write tampered bundle to temp file
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.zip', delete=False) as f:
        temp_path = f.name
        f.write(tampered_bytes)
    
    try:
        # Run CLI verifier
        result = subprocess.run(
            ['python3', 'tools/verify_bundle.py', temp_path],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent
        )
        
        # Should fail (exit code 1)
        assert result.returncode == 1
        
        # Check output
        assert "FAIL" in result.stdout or "INVALID" in result.stdout
        
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_cli_verifier_handles_missing_file():
    """
    Test that CLI verifier returns exit code 2 for missing file.
    """
    result = subprocess.run(
        ['python3', 'tools/verify_bundle.py', '/nonexistent/file.zip'],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent
    )
    
    # Should error (exit code 2)
    assert result.returncode == 2
    
    # Check output
    assert "not found" in result.stdout.lower() or "ERROR" in result.stdout


def test_cli_verifier_handles_invalid_zip(client):
    """
    Test that CLI verifier returns exit code 2 for invalid ZIP.
    """
    # Create invalid ZIP file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.zip', delete=False) as f:
        temp_path = f.name
        f.write("NOT A VALID ZIP FILE")
    
    try:
        result = subprocess.run(
            ['python3', 'tools/verify_bundle.py', temp_path],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent
        )
        
        # Should error (exit code 2)
        assert result.returncode == 2
        
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_cli_verifier_shows_usage_without_args():
    """
    Test that CLI verifier shows usage when called without arguments.
    """
    result = subprocess.run(
        ['python3', 'tools/verify_bundle.py'],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent
    )
    
    # Should show usage (exit code 2)
    assert result.returncode == 2
    
    # Check output
    assert "Usage" in result.stdout or "usage" in result.stdout.lower()


def test_cli_verifier_output_has_verification_steps(client):
    """
    Test that CLI verifier output shows all verification steps.
    """
    # Get defense bundle
    bundle_bytes = issue_and_get_defense_bundle(client)
    
    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.zip', delete=False) as f:
        temp_path = f.name
        f.write(bundle_bytes)
    
    try:
        # Run CLI verifier
        result = subprocess.run(
            ['python3', 'tools/verify_bundle.py', temp_path],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent
        )
        
        # Check that verification steps are shown
        output = result.stdout
        
        # Should show steps
        assert "STEP 1" in output or "EXTRACT" in output
        assert "STEP 2" in output or "HASH" in output
        assert "STEP 3" in output or "SIGNATURE" in output
        assert "STEP 4" in output or "CHAIN" in output
        assert "STEP 5" in output or "ATTESTATION" in output
        
        # Should show summary
        assert "SUMMARY" in output or "Summary" in output
        
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_cli_verifier_shows_certificate_details(client):
    """
    Test that CLI verifier shows certificate details in output.
    """
    # Get defense bundle
    bundle_bytes = issue_and_get_defense_bundle(client)
    
    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.zip', delete=False) as f:
        temp_path = f.name
        f.write(bundle_bytes)
    
    try:
        # Run CLI verifier
        result = subprocess.run(
            ['python3', 'tools/verify_bundle.py', temp_path],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent
        )
        
        output = result.stdout
        
        # Should show certificate details
        assert "Certificate Details" in output or "ID:" in output
        assert "Model" in output or "model" in output.lower()
        assert "Human Reviewed" in output or "reviewed" in output.lower()
        
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_cli_verifier_validates_provenance_fields(client):
    """
    Test that CLI verifier validates presence of provenance fields.
    """
    # Get defense bundle
    bundle_bytes = issue_and_get_defense_bundle(client)
    
    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.zip', delete=False) as f:
        temp_path = f.name
        f.write(bundle_bytes)
    
    try:
        # Run CLI verifier
        result = subprocess.run(
            ['python3', 'tools/verify_bundle.py', temp_path],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent
        )
        
        output = result.stdout
        
        # Should check provenance fields
        assert "provenance" in output.lower() or "fields" in output.lower()
        
    finally:
        Path(temp_path).unlink(missing_ok=True)
