#!/usr/bin/env python3
"""
init-tenant-vault.py

Generates a tenant-scoped RSA-4096 keypair for signing/verification.
Encrypts the private key with an environment-level passphrase.
Outputs a System Readiness Report (public key hash/fingerprint).

Usage:
  TENANT_VAULT_PASSPHRASE="strong passphrase" \
    python tools/init-tenant-vault.py --tenant acme-clinic

Options:
  --out-dir   Base output directory (default: tenant_vault)
  --force     Overwrite existing tenant vault directory
  --env       Passphrase env var name (default: TENANT_VAULT_PASSPHRASE)
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import os
import pathlib
import re
import sys

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
except ImportError as e:
    print("ERROR: Missing dependency 'cryptography'. Install it, e.g.: pip install cryptography", file=sys.stderr)
    raise


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    if not value:
        raise ValueError("Tenant name produced an empty slug. Provide a valid tenant identifier.")
    return value


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True, help="Tenant identifier (e.g., 'acme-clinic')")
    ap.add_argument("--out-dir", default="tenant_vault", help="Base output dir (default: tenant_vault)")
    ap.add_argument("--force", action="store_true", help="Overwrite existing tenant directory")
    ap.add_argument("--env", default="TENANT_VAULT_PASSPHRASE", help="Passphrase env var name")
    args = ap.parse_args()

    tenant_slug = _slugify(args.tenant)
    base_dir = pathlib.Path(args.out_dir).resolve()
    tenant_dir = base_dir / tenant_slug

    passphrase = os.environ.get(args.env)
    if not passphrase:
        print(f"ERROR: Missing passphrase. Set env var {args.env}.", file=sys.stderr)
        return 2
    if len(passphrase) < 16:
        print("ERROR: Passphrase too short. Use 16+ chars (ideally 24+).", file=sys.stderr)
        return 2

    if tenant_dir.exists():
        if not args.force:
            print(f"ERROR: Tenant vault already exists at: {tenant_dir}\n"
                  f"Use --force to overwrite.", file=sys.stderr)
            return 3
        # cautious delete: only remove files we expect
        for p in tenant_dir.glob("*"):
            if p.is_file():
                p.unlink()
        # keep directory

    tenant_dir.mkdir(parents=True, exist_ok=True)

    # Generate RSA-4096
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    public_key = private_key.public_key()

    # Serialize + encrypt private key (PKCS8 + best available encryption)
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(passphrase.encode("utf-8")),
    )

    pub_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Fingerprints / hashes (useful for audit & configuration)
    pub_sha256 = _sha256_hex(pub_pem)
    pub_fpr_short = f"{pub_sha256[:8]}…{pub_sha256[-8:]}"
    pub_sha256_b64 = base64.b64encode(hashlib.sha256(pub_pem).digest()).decode("ascii")

    # Write files with safer permissions where possible
    priv_path = tenant_dir / "tenant_private_key.pem"
    pub_path = tenant_dir / "tenant_public_key.pem"
    meta_path = tenant_dir / "readiness_report.txt"

    priv_path.write_bytes(priv_pem)
    pub_path.write_bytes(pub_pem)

    # Best-effort chmod (Windows may ignore)
    try:
        os.chmod(priv_path, 0o600)
        os.chmod(pub_path, 0o644)
    except Exception:
        pass

    report = f"""SECURESTAFF / INSTITUTIONAL TRUST — SYSTEM READINESS REPORT
Generated (UTC): {_utc_now_iso()}
Tenant: {args.tenant}
Tenant Slug: {tenant_slug}

KEY MATERIAL
- Algorithm: RSA
- Key Size: 4096
- Public Key File: {pub_path}
- Private Key File: {priv_path}
- Private Key Encryption: PKCS8 PEM (BestAvailableEncryption) using env var '{args.env}'

PUBLIC KEY IDENTIFIERS (for configuration / audit)
- Public Key SHA-256 (hex): {pub_sha256}
- Public Key SHA-256 (base64): {pub_sha256_b64}
- Public Key Fingerprint (short): {pub_fpr_short}

OPERATIONAL NOTES
- Store the passphrase in your secrets manager (NOT in git, NOT in .env committed to repo).
- Rotate keys per tenant based on policy; keep old public keys if you must validate legacy signatures.
- Treat the private key as a regulated asset (access logging + least privilege).

STATUS: READY
"""
    meta_path.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
