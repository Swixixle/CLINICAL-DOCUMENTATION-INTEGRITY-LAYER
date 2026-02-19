"""
JWT-based authentication and authorization for CDIL.

This module implements identity binding and role-based access control.
All tenant context is derived from authenticated identity, never from client input.

Security Principles:
1. All requests must be authenticated with a valid JWT
2. Tenant ID is extracted from JWT claims, never from headers/body
3. Role-based access controls which operations can be performed
4. JWT signature is validated (RS256 for production-ready design)
5. Token expiration is enforced

Roles:
- clinician: Can issue certificates
- auditor: Can verify certificates and query audit logs
- admin: Full access to all operations
- ehr_gateway: Can verify certificates and issue commit tokens (EHR gatekeeper mode)
"""

import os
from datetime import datetime, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

# JWT Configuration
# In production, use RS256 with public key from identity provider
# For MVP, using HS256 with secret key
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")  # Use RS256 in production

# Security scheme
security = HTTPBearer()


class Identity(BaseModel):
    """
    Authenticated identity extracted from JWT.

    This is the source of truth for tenant context and user identity.
    Client cannot forge this - it's derived from cryptographically validated JWT.
    """

    sub: str  # User ID (subject)
    tenant_id: str  # Tenant ID (from JWT claim)
    role: str  # User role (clinician, auditor, admin)
    exp: Optional[int] = None  # Expiration timestamp

    def has_role(self, required_role: str) -> bool:
        """Check if identity has the required role."""
        return self.role == required_role or self.role == "admin"


def decode_jwt(token: str) -> dict:
    """
    Decode and validate JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded JWT payload

    Raises:
        JWTError: If token is invalid, expired, or malformed
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "require_exp": True,
                "require_sub": True,
            },
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "message": f"Token validation failed: {str(e)}",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_identity(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Identity:
    """
    Extract and validate identity from JWT token.

    This is the primary authentication mechanism for CDIL.
    All routes requiring authentication should depend on this function.

    Args:
        credentials: HTTP Bearer credentials from Authorization header

    Returns:
        Validated Identity object

    Raises:
        HTTPException: 401 if token is invalid or missing required claims
    """
    token = credentials.credentials

    try:
        payload = decode_jwt(token)

        # Extract required claims
        sub = payload.get("sub")
        tenant_id = payload.get("tenant_id")
        role = payload.get("role")
        exp = payload.get("exp")

        # Validate required claims
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "missing_claim",
                    "message": "Token missing 'sub' claim",
                },
            )

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "missing_claim",
                    "message": "Token missing 'tenant_id' claim",
                },
            )

        if not role:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "missing_claim",
                    "message": "Token missing 'role' claim",
                },
            )

        # Validate role value
        valid_roles = {"clinician", "auditor", "admin", "ehr_gateway"}
        if role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_role",
                    "message": f"Invalid role '{role}'. Must be one of: {valid_roles}",
                },
            )

        return Identity(sub=sub, tenant_id=tenant_id, role=role, exp=exp)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "authentication_failed",
                "message": f"Failed to authenticate: {str(e)}",
            },
        )


def require_role(required_role: str):
    """
    Dependency factory for role-based access control.

    Usage:
        @router.post("/certificates")
        async def issue_certificate(
            identity: Identity = Depends(require_role("clinician"))
        ):
            ...

    Args:
        required_role: Role required to access the endpoint

    Returns:
        Dependency function that validates role
    """

    async def role_checker(
        identity: Identity = Depends(get_current_identity),
    ) -> Identity:
        if not identity.has_role(required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "insufficient_permissions",
                    "message": f"Role '{required_role}' required. You have: '{identity.role}'",
                },
            )
        return identity

    return role_checker


# Helper function for generating dev/test tokens
def create_jwt_token(
    sub: str, tenant_id: str, role: str, expires_in_seconds: int = 3600
) -> str:
    """
    Create a JWT token for development/testing.

    In production, tokens are issued by your identity provider (e.g., Auth0, Cognito).
    This function is for testing and development only.

    Args:
        sub: User ID
        tenant_id: Tenant ID
        role: User role
        expires_in_seconds: Token expiration time (default 1 hour)

    Returns:
        JWT token string
    """
    now = datetime.now(timezone.utc)
    exp = int(now.timestamp()) + expires_in_seconds

    payload = {
        "sub": sub,
        "tenant_id": tenant_id,
        "role": role,
        "exp": exp,
        "iat": int(now.timestamp()),
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
