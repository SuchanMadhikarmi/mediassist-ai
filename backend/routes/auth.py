# ============================================================
# backend/routes/auth.py
# Authentication routes — now DB-BACKED (replaces the MOCK_USERS dict).
#
# This is the reusable AuthN pattern for ~every project:
#   POST /api/auth/register  — public: create an account (forced end_user)
#   POST /api/auth/login     — username+password -> access + refresh tokens
#   POST /api/auth/refresh   — refresh token -> new access token
#   GET  /api/auth/me        — return the current user's profile
#
# Security notes:
#   - passwords hashed with bcrypt BEFORE storage (never plaintext)
#   - registration FORCES role=end_user (no self-elevation to admin)
#   - login returns two tokens: short access + long refresh
#   - every sensitive action is written to the audit_log table
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import AuditLog, User
from security.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from security.models import LoginRequest, RefreshRequest, RegisterRequest, Role, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Audit + "me" support
from dependencies import get_current_user_db  # noqa: E402
from schemas.user import UserResponse  # noqa: E402


def _write_audit(db: Session, action: str, user_id: str | None, details: dict | None = None):
    """Helper: log an action to the audit trail. Never raises on failure."""
    db.add(
        AuditLog(user_id=user_id, action=action, details=details)
    )
    db.commit()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Public registration. Always creates an end_user (never admin/expert)."""
    # Check for duplicates so we give a clean error, not a DB constraint error.
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=409, detail="Username already taken")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create + hash. role forced to end_user for security.
    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role=Role.END_USER.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)  # reload with generated id/created_at

    _write_audit(db, "USER_REGISTER", user.id)

    return _tokens_for(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate and issue tokens."""
    user = db.query(User).filter(User.username == body.username).first()
    # Constant-time-ish: same error for bad user OR bad password.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )

    _write_audit(db, "USER_LOGIN", user.id)
    return _tokens_for(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a fresh access + refresh pair."""
    payload = decode_refresh_token(body.refresh_token)
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return _tokens_for(user)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user_db)):
    """Return the currently authenticated user (from the live DB row)."""
    return user


def _tokens_for(user: User) -> TokenResponse:
    """Build a TokenResponse from a User (signs both access + refresh)."""
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id, user.role),
        role=Role(user.role),  # convert string back to Role enum for response
    )
