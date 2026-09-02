# ============================================================
# backend/security/models.py
# Pydantic schemas for security-related data.
#
# Pydantic models define the SHAPE of data. When a client sends
# JSON to /login, we validate it against LoginRequest. When we
# return a token, it matches Token. This gives us:
#   - free validation (wrong types -> clean 422 error)
#   - documentation (the /docs UI shows these schemas)
# ============================================================

from enum import Enum

from pydantic import BaseModel


class Role(str, Enum):
    """The three roles in our RBAC system (university requirement).

    Enum values ARE the strings stored in the JWT and Qdrant payloads.
    Using an Enum (not a raw string) prevents typos like "Admmin".

    Permissions (see Docs for full matrix):
      - admin   : manage all users, view everything, approve HITL, export
      - expert  : review/override predictions, view all predictions + audit
      - end_user: register, submit predictions, view own predictions only
    """
    ADMIN = "admin"
    EXPERT = "expert"
    END_USER = "end_user"

    # Backward compat alias: old "viewer" role → treated as end_user.
    VIEWER = "viewer"


class LoginRequest(BaseModel):
    """What a client sends to POST /login."""
    username: str
    password: str


class RegisterRequest(BaseModel):
    """What a client sends to POST /api/auth/register.

    Registration is PUBLIC (anyone can create an account), but the role
    is ALWAYS set to end_user server-side — a user cannot self-assign
    admin/expert (that would be a privilege escalation vulnerability).
    """
    username: str
    email: str
    password: str


class TokenResponse(BaseModel):
    """What a successful login/register returns to a client.

    Two tokens: access (short-lived, used on every API call) and refresh
    (long-lived, exchanged for a new access token when it expires). This
    is the standard OAuth2-style dual-token pattern.
    """
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # RFC 6750 bearer token scheme
    role: "Role"


class RefreshRequest(BaseModel):
    """What a client sends to POST /api/auth/refresh."""
    refresh_token: str


class User(BaseModel):
    """An authenticated user. In a real system this comes from a DB;
    here we use an in-memory mock user store (see routes/auth.py)."""
    user_id: str
    username: str
    role: "Role"
    # NEVER store plaintext passwords. Store a hash.
    password_hash: str
