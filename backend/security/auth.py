# ============================================================
# backend/security/auth.py
# JWT token lifecycle + password hashing + FastAPI auth dependency.
#
# Two halves:
#   1. Token functions (create/verify) — pure logic, testable
#   2. FastAPI dependency (get_current_user) — plugs into endpoints
# ============================================================

from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from config import settings

# --- Password hashing ---------------------------------------------------
# bcrypt is a slow, salted hash — deliberately slow to resist brute force.
# NEVER store or compare plaintext passwords.

def hash_password(plain: str) -> str:
    # hashpw returns bytes; decode to a str for storage.
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    # checkpw compares safely (constant-time) against the stored hash.
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# --- JWT creation -------------------------------------------------------

def _create_token(user_id: str, role: str, token_type: str, minutes: int) -> str:
    """Sign a JWT embedding the user's identity + role + token type.

    The same encoder is used for access AND refresh tokens; the `type`
    claim differentiates them so a refresh token can't be used as an
    access token (and vice versa).
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "type": token_type,  # "access" | "refresh"
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    # jwt.encode signs header+payload with our secret using HS256.
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, role: str) -> str:
    """Short-lived token (JWT_EXPIRATION_MINUTES) sent on every API call."""
    return _create_token(user_id, role, "access", settings.jwt_expiration_minutes)


def create_refresh_token(user_id: str, role: str) -> str:
    """Longer-lived token exchanged for a fresh access token when it expires."""
    # Refresh lives 7 days by default (longer than access).
    return _create_token(user_id, role, "refresh", 60 * 24 * 7)


# --- JWT verification / extraction ---------------------------------------
# HTTPBearer tells FastAPI "this endpoint reads the Authorization: Bearer <token>
# header". auto_error=False -> we handle missing tokens ourselves for clean errors.

_bearer = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> dict:
    """Decode + verify a token's signature and expiry. Raises HTTPException on any problem."""
    try:
        # jwt.decode verifies the SIGNATURE (tamper-proof) and the EXP claim.
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    return payload


def decode_refresh_token(token: str) -> dict:
    """Decode a refresh token, ensuring it is a refresh (not access) token."""
    payload = _decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not a valid refresh token",
        )
    return payload


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """FastAPI dependency: extract the authenticated user's identity.

    Usage in endpoints:
        @app.get("/secure")
        def secure(user: dict = Depends(get_current_user)):
            return {"logged_in_as": user["role"]}

    If no/invalid token is provided, a 401 is raised BEFORE the endpoint runs.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode_token(credentials.credentials)
    # Access tokens only: do not accept a refresh token as proof of auth.
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "user_id": payload.get("sub"),
        "role": payload.get("role"),
    }
