"""Tests for init-tenant-vault.py tool."""

import os
import pathlib
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


def test_init_tenant_vault_basic():
    """Test basic tenant vault creation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set up environment
        passphrase = "test-passphrase-minimum-16chars"
        tenant_name = "test-clinic"
        
        # Run the script
        result = subprocess.run(
            [
                sys.executable,
                "tools/init-tenant-vault.py",
                "--tenant", tenant_name,
                "--out-dir", tmpdir,
            ],
            env={**os.environ, "TENANT_VAULT_PASSPHRASE": passphrase},
            capture_output=True,
            text=True,
        )
        
        # Check exit code
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        
        # Check output contains expected sections
        assert "SYSTEM READINESS REPORT" in result.stdout
        assert "KEY MATERIAL" in result.stdout
        assert "PUBLIC KEY IDENTIFIERS" in result.stdout
        assert "STATUS: READY" in result.stdout
        
        # Check files were created
        tenant_dir = Path(tmpdir) / "test-clinic"
        assert tenant_dir.exists()
        
        priv_key = tenant_dir / "tenant_private_key.pem"
        pub_key = tenant_dir / "tenant_public_key.pem"
        report = tenant_dir / "readiness_report.txt"
        
        assert priv_key.exists()
        assert pub_key.exists()
        assert report.exists()
        
        # Check private key is encrypted (contains ENCRYPTED keyword)
        priv_content = priv_key.read_text()
        assert "ENCRYPTED" in priv_content
        assert "BEGIN ENCRYPTED PRIVATE KEY" in priv_content
        
        # Check public key format
        pub_content = pub_key.read_text()
        assert "BEGIN PUBLIC KEY" in pub_content
        assert "END PUBLIC KEY" in pub_content


def test_init_tenant_vault_missing_passphrase():
    """Test that script fails without passphrase."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Run without passphrase
        result = subprocess.run(
            [
                sys.executable,
                "tools/init-tenant-vault.py",
                "--tenant", "test-clinic",
                "--out-dir", tmpdir,
            ],
            env={k: v for k, v in os.environ.items() if k != "TENANT_VAULT_PASSPHRASE"},
            capture_output=True,
            text=True,
        )
        
        # Should fail with exit code 2
        assert result.returncode == 2
        assert "Missing passphrase" in result.stderr


def test_init_tenant_vault_short_passphrase():
    """Test that script rejects short passphrases."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [
                sys.executable,
                "tools/init-tenant-vault.py",
                "--tenant", "test-clinic",
                "--out-dir", tmpdir,
            ],
            env={**os.environ, "TENANT_VAULT_PASSPHRASE": "short"},
            capture_output=True,
            text=True,
        )
        
        # Should fail with exit code 2
        assert result.returncode == 2
        assert "Passphrase too short" in result.stderr


def test_init_tenant_vault_already_exists():
    """Test that script fails if tenant vault already exists without --force."""
    with tempfile.TemporaryDirectory() as tmpdir:
        passphrase = "test-passphrase-minimum-16chars"
        tenant_name = "test-clinic"
        
        # Create vault first time
        result1 = subprocess.run(
            [
                sys.executable,
                "tools/init-tenant-vault.py",
                "--tenant", tenant_name,
                "--out-dir", tmpdir,
            ],
            env={**os.environ, "TENANT_VAULT_PASSPHRASE": passphrase},
            capture_output=True,
            text=True,
        )
        assert result1.returncode == 0
        
        # Try to create again without --force
        result2 = subprocess.run(
            [
                sys.executable,
                "tools/init-tenant-vault.py",
                "--tenant", tenant_name,
                "--out-dir", tmpdir,
            ],
            env={**os.environ, "TENANT_VAULT_PASSPHRASE": passphrase},
            capture_output=True,
            text=True,
        )
        
        # Should fail with exit code 3
        assert result2.returncode == 3
        assert "already exists" in result2.stderr
        assert "--force" in result2.stderr


def test_init_tenant_vault_force_overwrite():
    """Test that --force flag allows overwriting existing vault."""
    with tempfile.TemporaryDirectory() as tmpdir:
        passphrase = "test-passphrase-minimum-16chars"
        tenant_name = "test-clinic"
        
        # Create vault first time
        result1 = subprocess.run(
            [
                sys.executable,
                "tools/init-tenant-vault.py",
                "--tenant", tenant_name,
                "--out-dir", tmpdir,
            ],
            env={**os.environ, "TENANT_VAULT_PASSPHRASE": passphrase},
            capture_output=True,
            text=True,
        )
        assert result1.returncode == 0
        
        # Get original public key
        tenant_dir = Path(tmpdir) / "test-clinic"
        original_pub = (tenant_dir / "tenant_public_key.pem").read_text()
        
        # Create again with --force
        result2 = subprocess.run(
            [
                sys.executable,
                "tools/init-tenant-vault.py",
                "--tenant", tenant_name,
                "--out-dir", tmpdir,
                "--force",
            ],
            env={**os.environ, "TENANT_VAULT_PASSPHRASE": passphrase},
            capture_output=True,
            text=True,
        )
        
        # Should succeed
        assert result2.returncode == 0
        
        # Public key should be different (new keypair)
        new_pub = (tenant_dir / "tenant_public_key.pem").read_text()
        assert original_pub != new_pub


def test_init_tenant_vault_tenant_slug():
    """Test that tenant names are properly slugified."""
    with tempfile.TemporaryDirectory() as tmpdir:
        passphrase = "test-passphrase-minimum-16chars"
        
        # Test with special characters and spaces
        result = subprocess.run(
            [
                sys.executable,
                "tools/init-tenant-vault.py",
                "--tenant", "Test Clinic (Main Campus)!",
                "--out-dir", tmpdir,
            ],
            env={**os.environ, "TENANT_VAULT_PASSPHRASE": passphrase},
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        
        # Check that directory was created with slug
        tenant_dir = Path(tmpdir) / "test-clinic-main-campus"
        assert tenant_dir.exists()
        
        # Check that report contains both original name and slug
        report = (tenant_dir / "readiness_report.txt").read_text()
        assert "Test Clinic (Main Campus)!" in report
        assert "test-clinic-main-campus" in report


def test_init_tenant_vault_custom_env_var():
    """Test using custom environment variable for passphrase."""
    with tempfile.TemporaryDirectory() as tmpdir:
        passphrase = "test-passphrase-minimum-16chars"
        custom_env = "MY_CUSTOM_PASSPHRASE"
        
        result = subprocess.run(
            [
                sys.executable,
                "tools/init-tenant-vault.py",
                "--tenant", "test-clinic",
                "--out-dir", tmpdir,
                "--env", custom_env,
            ],
            env={**os.environ, custom_env: passphrase},
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        
        # Check report mentions the custom env var
        tenant_dir = Path(tmpdir) / "test-clinic"
        report = (tenant_dir / "readiness_report.txt").read_text()
        assert custom_env in report


def test_init_tenant_vault_report_contains_fingerprints():
    """Test that the readiness report contains all expected fingerprints."""
    with tempfile.TemporaryDirectory() as tmpdir:
        passphrase = "test-passphrase-minimum-16chars"
        
        result = subprocess.run(
            [
                sys.executable,
                "tools/init-tenant-vault.py",
                "--tenant", "test-clinic",
                "--out-dir", tmpdir,
            ],
            env={**os.environ, "TENANT_VAULT_PASSPHRASE": passphrase},
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        
        tenant_dir = Path(tmpdir) / "test-clinic"
        report = (tenant_dir / "readiness_report.txt").read_text()
        
        # Check for required sections
        assert "Public Key SHA-256 (hex):" in report
        assert "Public Key SHA-256 (base64):" in report
        assert "Public Key Fingerprint (short):" in report
        
        # Check that fingerprints are present (hex should be 64 chars)
        import re
        hex_match = re.search(r"Public Key SHA-256 \(hex\): ([0-9a-f]{64})", report)
        assert hex_match is not None
        
        # Check base64 format
        b64_match = re.search(r"Public Key SHA-256 \(base64\): ([A-Za-z0-9+/=]+)", report)
        assert b64_match is not None


def test_init_tenant_vault_explicit_kdf_parameters():
    """Test that explicit KDF parameters are documented for audit compliance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        passphrase = "test-passphrase-minimum-16chars"
        
        result = subprocess.run(
            [
                sys.executable,
                "tools/init-tenant-vault.py",
                "--tenant", "test-clinic",
                "--out-dir", tmpdir,
            ],
            env={**os.environ, "TENANT_VAULT_PASSPHRASE": passphrase},
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        
        tenant_dir = Path(tmpdir) / "test-clinic"
        report = (tenant_dir / "readiness_report.txt").read_text()
        
        # Check report contains explicit KDF information
        assert "ENCRYPTION PARAMETERS (EXPLICIT FOR AUDIT)" in report
        assert "PBKDF2HMAC" in report
        assert "600,000" in report or "600000" in report
        assert "AES-256-CBC" in report
        assert "SHA-256" in report
        assert "AUDIT-OPTIMAL" in report
        
        # Check KDF parameters file exists
        kdf_file = tenant_dir / "kdf_parameters.txt"
        assert kdf_file.exists()
        
        kdf_content = kdf_file.read_text()
        assert "KDF PARAMETERS" in kdf_content
        assert "PBKDF2HMAC" in kdf_content
        assert "600,000" in kdf_content or "600000" in kdf_content
        assert "AES-256-CBC" in kdf_content
        assert "NIST SP 800-132" in kdf_content
        assert "OWASP 2023" in kdf_content
        assert "COMPLIANCE NOTES" in kdf_content
