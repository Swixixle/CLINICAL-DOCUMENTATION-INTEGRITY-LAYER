"""
Authentication helpers for migrating tests to JWT-based auth.

This module provides backward-compatible helpers for tests that used X-Tenant-Id headers.
"""

from gateway.tests.test_helpers import generate_test_jwt


def create_jwt_headers(tenant_id: str, role: str = "clinician", sub: str = None) -> dict:
    """
    Create JWT authentication headers for testing.
    
    This is a convenience wrapper that replaces the old X-Tenant-Id pattern.
    
    Args:
        tenant_id: Tenant identifier (derived from JWT, not header)
        role: User role (clinician, auditor, admin)
        sub: User ID (auto-generated if not provided)
        
    Returns:
        Dictionary with Authorization header
    """
    if sub is None:
        sub = f"test-user-{tenant_id}"
    
    token = generate_test_jwt(
        sub=sub,
        tenant_id=tenant_id,
        role=role
    )
    
    return {
        "Authorization": f"Bearer {token}"
    }


def create_clinician_headers(tenant_id: str, sub: str = None) -> dict:
    """Create headers for clinician role (can issue certificates)."""
    return create_jwt_headers(tenant_id, role="clinician", sub=sub)


def create_auditor_headers(tenant_id: str, sub: str = None) -> dict:
    """Create headers for auditor role (can verify certificates)."""
    return create_jwt_headers(tenant_id, role="auditor", sub=sub)


def create_admin_headers(tenant_id: str, sub: str = None) -> dict:
    """Create headers for admin role (full access)."""
    return create_jwt_headers(tenant_id, role="admin", sub=sub)


def create_ehr_gateway_headers(tenant_id: str, sub: str = None) -> dict:
    """Create headers for ehr_gateway role (can verify and issue commit tokens)."""
    return create_jwt_headers(tenant_id, role="ehr_gateway", sub=sub)
