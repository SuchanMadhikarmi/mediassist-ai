# ============================================================
# backend/dependencies.py
# SHARED FastAPI dependencies — the glue reused by every CRUD router.
#
# This is the CENTRAL place for the boring-but-essential wiring:
#   - get_db(): yield a DB session (defined in database.py, re-exported)
#   - require_roles(): allow a SET of roles (more flexible than single role)
#   - get_current_user_db(): authenticated user loaded fresh from the DB
#   - pagination params: page / per_page / search
#
# WHY a single file: every router needs these. Centralizing them means
# one import, one source of truth, and consistent behavior everywhere.
# This is the reusable "API layer" of the boring 80% stack.
# ============================================================

from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from security.auth import _decode_token, _bearer
from security.models import Role

# Convenience alias: an endpoint does `db: Session = Depends(get_db)`.
DbSession = Annotated[Session, Depends(get_db)]


def get_current_user_db(
    credentials=Depends(_bearer),
    db: Session = Depends(get_db),
) -> "User":
    """Authenticate via JWT AND load the live user row from the DB.

    WHY load from DB (not just trust the JWT claims):
    - we can enforce is_active (disabled user can't keep using a token)
    - role changes take effect immediately (not stuck in the old token)
    - we get the full user object (id, email, etc.) for downstream use

    This is the standard pattern: JWT proves identity, DB provides the
    current truth about that identity.
    """
    from models import User  # local import to avoid circular deps

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


class RoleGuard:
    """Dependency factory that requires the user to have one of `roles`.

    WHY a class (vs a bare function like the old require_role):
    - it can hold the allowed roles as state
    - it validates that the requested roles are REAL enum values
      (catches typos like "Admmin" at import/startup time, not request time)
    - __call__ makes the instance itself a usable FastAPI dependency
    """
    def __init__(self, *roles: Role):
        # Fail fast at construction time if an invalid role is passed.
        unknown = [r for r in roles if not isinstance(r, Role)]
        if unknown:
            raise ValueError(f"Invalid role(s): {unknown}")
        self.roles = roles

    def __call__(self, user: "User" = Depends(get_current_user_db)) -> "User":
        if user.role not in [r.value for r in self.roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role(s) {[r.value for r in self.roles]} required for this action",
            )
        return user


# Convenience pre-built role guards (avoids repeating guard instances).
require_admin = RoleGuard(Role.ADMIN)
require_staff = RoleGuard(Role.ADMIN, Role.EXPERT)


def pagination_params(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
) -> dict:
    """Standard, validated pagination query params.

    An endpoint injects this dict and uses page/per_page to slice.
    The '/' operator in SQLAlchemy means 'divide' — but here slicing uses
    Python list slicing [offset:offset+per_page]. See paginate() below.
    """
    return {"page": page, "per_page": per_page}


def paginate(query, page: int, per_page: int) -> dict:
    """Apply offset/limit to an ORM query and return a standard envelope.

    Returns the reusable response shape used across ALL CRUD endpoints:
        {"items": [...], "total": N, "page": p, "per_page": k, "pages": m}

    This consistent envelope is what lets the frontend build ONE generic
    table/pagination component that works for every list endpoint.
    """
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    pages = (total + per_page - 1) // per_page  # ceiling division
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }
