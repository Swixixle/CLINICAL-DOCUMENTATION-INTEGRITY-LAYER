"""
Per-tenant key registry for CDIL.

This module manages cryptographic keys on a per-tenant basis, ensuring that:
1. Each tenant has isolated keys (prevents cross-tenant forgery)
2. Keys can be rotated without invalidating existing certificates
3. Verification uses the specific key_id that signed each certificate

Security Principle: Cryptographic boundary MUST equal tenant boundary.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Optional
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

from gateway.app.db.migrate import get_connection


class KeyRegistry:
    """
    Registry for managing per-tenant cryptographic keys.

    In production, this would integrate with AWS KMS, GCP KMS, or Azure Key Vault.
    For MVP, keys are stored in the database with in-memory caching.
    """

    def __init__(self):
        """Initialize key registry with empty cache."""
        self._cache: Dict[str, Dict] = {}  # {tenant_id: {key_id: key_data}}

    def get_active_key(self, tenant_id: str) -> Optional[Dict]:
        """
        Get the active signing key for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dictionary with:
                - key_id: Key identifier
                - private_key: Cryptography private key object
                - public_jwk: Public key as JWK
                - status: 'active'
            None if no active key exists
        """
        # Check cache first
        if tenant_id in self._cache:
            for key_id, key_data in self._cache[tenant_id].items():
                if key_data.get("status") == "active":
                    return key_data

        # Load from database
        conn = get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT key_id, private_key_pem, public_jwk_json, status
                FROM tenant_keys
                WHERE tenant_id = ? AND status = 'active'
                ORDER BY created_at_utc DESC
                LIMIT 1
            """,
                (tenant_id,),
            )

            row = cursor.fetchone()
            if not row:
                return None

            # Load private key
            private_key_pem = row["private_key_pem"]
            private_key = serialization.load_pem_private_key(
                private_key_pem.encode("utf-8"),
                password=None,
                backend=default_backend(),
            )

            # Parse JWK
            public_jwk = json.loads(row["public_jwk_json"])

            key_data = {
                "key_id": row["key_id"],
                "private_key": private_key,
                "public_jwk": public_jwk,
                "status": row["status"],
            }

            # Cache it
            if tenant_id not in self._cache:
                self._cache[tenant_id] = {}
            self._cache[tenant_id][row["key_id"]] = key_data

            return key_data

        finally:
            conn.close()

    def get_key_by_id(self, tenant_id: str, key_id: str) -> Optional[Dict]:
        """
        Get a specific key by ID (for verification of old certificates).

        Args:
            tenant_id: Tenant identifier
            key_id: Key identifier

        Returns:
            Dictionary with key data, or None if not found
        """
        # Check cache first
        if tenant_id in self._cache and key_id in self._cache[tenant_id]:
            return self._cache[tenant_id][key_id]

        # Load from database
        conn = get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT key_id, private_key_pem, public_jwk_json, status
                FROM tenant_keys
                WHERE tenant_id = ? AND key_id = ?
            """,
                (tenant_id, key_id),
            )

            row = cursor.fetchone()
            if not row:
                return None

            # Load private key (may not be present for rotated keys in production)
            private_key = None
            if row["private_key_pem"]:
                private_key = serialization.load_pem_private_key(
                    row["private_key_pem"].encode("utf-8"),
                    password=None,
                    backend=default_backend(),
                )

            # Parse JWK
            public_jwk = json.loads(row["public_jwk_json"])

            key_data = {
                "key_id": row["key_id"],
                "private_key": private_key,
                "public_jwk": public_jwk,
                "status": row["status"],
            }

            # Cache it
            if tenant_id not in self._cache:
                self._cache[tenant_id] = {}
            self._cache[tenant_id][key_id] = key_data

            return key_data

        finally:
            conn.close()

    def generate_key_for_tenant(self, tenant_id: str) -> str:
        """
        Generate a new key pair for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            key_id of the newly generated key
        """
        # Generate new ECDSA P-256 key pair
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

        # Export private key as PEM
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        # Export public key as JWK
        public_key = private_key.public_key()
        public_numbers = public_key.public_numbers()

        # Convert to base64url encoding (JWK format)
        import base64

        x_bytes = public_numbers.x.to_bytes(32, byteorder="big")
        y_bytes = public_numbers.y.to_bytes(32, byteorder="big")

        x_b64 = base64.urlsafe_b64encode(x_bytes).decode("utf-8").rstrip("=")
        y_b64 = base64.urlsafe_b64encode(y_bytes).decode("utf-8").rstrip("=")

        # Generate key_id
        from gateway.app.services.uuid7 import generate_uuid7

        key_id = f"key-{generate_uuid7()}"

        public_jwk = {
            "kty": "EC",
            "crv": "P-256",
            "x": x_b64,
            "y": y_b64,
            "use": "sig",
            "kid": key_id,
        }

        public_jwk_json = json.dumps(public_jwk, sort_keys=True)

        # Store in database
        created_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO tenant_keys (
                    key_id,
                    tenant_id,
                    private_key_pem,
                    public_jwk_json,
                    status,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, 'active', ?)
            """,
                (key_id, tenant_id, private_key_pem, public_jwk_json, created_at_utc),
            )
            conn.commit()
        finally:
            conn.close()

        # Clear cache for this tenant to force reload
        if tenant_id in self._cache:
            del self._cache[tenant_id]

        return key_id

    def rotate_key(self, tenant_id: str) -> str:
        """
        Rotate keys for a tenant.

        This marks the current active key as 'rotated' and generates a new active key.
        Existing certificates remain valid and can be verified using their key_id.

        Args:
            tenant_id: Tenant identifier

        Returns:
            key_id of the new active key
        """
        conn = get_connection()
        try:
            # Mark current active key as rotated
            conn.execute(
                """
                UPDATE tenant_keys
                SET status = 'rotated'
                WHERE tenant_id = ? AND status = 'active'
            """,
                (tenant_id,),
            )
            conn.commit()
        finally:
            conn.close()

        # Clear cache
        if tenant_id in self._cache:
            del self._cache[tenant_id]

        # Generate new key
        return self.generate_key_for_tenant(tenant_id)

    def ensure_tenant_has_key(self, tenant_id: str) -> str:
        """
        Ensure a tenant has an active key, generating one if needed.

        Args:
            tenant_id: Tenant identifier

        Returns:
            key_id of the active key
        """
        key = self.get_active_key(tenant_id)
        if key:
            return key["key_id"]

        return self.generate_key_for_tenant(tenant_id)


# Global registry instance
_registry = KeyRegistry()


def get_key_registry() -> KeyRegistry:
    """Get the global key registry instance."""
    return _registry
