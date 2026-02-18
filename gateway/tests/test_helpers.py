"""
Test helpers for CDIL security testing.

Provides utilities for generating JWT tokens and setting up authenticated test clients.
"""

import os
from datetime import datetime, timezone, timedelta
from jose import jwt


def generate_test_jwt(
    sub: str = "test-user-123",
    tenant_id: str = "test-tenant-001",
    role: str = "clinician",
    expires_in_seconds: int = 3600,
    secret_key: str = None,
    algorithm: str = None
) -> str:
    """
    Generate a test JWT token for authentication testing.
    
    Args:
        sub: User ID (subject)
        tenant_id: Tenant identifier
        role: User role (clinician, auditor, admin)
        expires_in_seconds: Token validity duration
        secret_key: JWT secret key (uses env var if not provided)
        algorithm: JWT algorithm (uses env var if not provided)
        
    Returns:
        JWT token string
    """
    if secret_key is None:
        secret_key = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
    
    if algorithm is None:
        algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    
    now = datetime.now(timezone.utc)
    exp = int(now.timestamp()) + expires_in_seconds
    
    payload = {
        "sub": sub,
        "tenant_id": tenant_id,
        "role": role,
        "exp": exp,
        "iat": int(now.timestamp()),
        "iss": "test-issuer"
    }
    
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def generate_expired_jwt(
    sub: str = "test-user-123",
    tenant_id: str = "test-tenant-001",
    role: str = "clinician"
) -> str:
    """
    Generate an expired JWT token for testing expiration handling.
    
    Args:
        sub: User ID
        tenant_id: Tenant identifier
        role: User role
        
    Returns:
        Expired JWT token string
    """
    secret_key = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    
    # Create token that expired 1 hour ago
    now = datetime.now(timezone.utc)
    exp = int((now - timedelta(hours=1)).timestamp())
    
    payload = {
        "sub": sub,
        "tenant_id": tenant_id,
        "role": role,
        "exp": exp,
        "iat": int((now - timedelta(hours=2)).timestamp())
    }
    
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def generate_malformed_jwt() -> str:
    """Generate a malformed JWT for testing error handling."""
    return "malformed.jwt.token"


def create_auth_headers(token: str = None, **jwt_kwargs) -> dict:
    """
    Create Authorization headers for API requests.
    
    Args:
        token: Pre-generated JWT token, or None to generate one
        **jwt_kwargs: Arguments passed to generate_test_jwt if token is None
        
    Returns:
        Dictionary with Authorization header
    """
    if token is None:
        token = generate_test_jwt(**jwt_kwargs)
    
    return {
        "Authorization": f"Bearer {token}"
    }


# Common test identities
TEST_CLINICIAN = {
    "sub": "clinician-001",
    "tenant_id": "hospital-a",
    "role": "clinician"
}

TEST_AUDITOR = {
    "sub": "auditor-001",
    "tenant_id": "hospital-a",
    "role": "auditor"
}

TEST_ADMIN = {
    "sub": "admin-001",
    "tenant_id": "hospital-a",
    "role": "admin"
}

TEST_TENANT_B_CLINICIAN = {
    "sub": "clinician-002",
    "tenant_id": "hospital-b",
    "role": "clinician"
}
