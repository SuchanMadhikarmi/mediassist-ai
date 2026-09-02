# ============================================================
# backend/routes/users.py
# Admin-only CRUD over users + the reusable search/paginate pattern.
#
# This is the "CRUD on an entity, admin-scoped" template. Copy it for
# any future entity: change the model, the schema, and the allowed roles.
#
# Patterns shown:
#   - require_admin      : RBAC gate (only admin)
#   - get_db session     : per-request DB session (auto-closed)
#   - search + paginate  : ?search= & page/per_page -> standard envelope
#   - soft delete        : set is_active=False instead of DELETE row
#     (preserves history/FKs — the industry-standard safest delete)
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from dependencies import paginate, require_admin, DbSession
from models import User
from schemas.user import UserCreate, UserResponse, UserUpdate
from security.auth import hash_password
from security.models import Role

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("")
def list_users(
    db: DbSession,
    _admin: dict = Depends(require_admin),
    search: str | None = Query(None, description="Filter by username/email/role"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List users with optional keyword search + pagination (admin only)."""
    query = db.query(User)
    if search:
        # ILIKE = case-insensitive LIKE; OR across username/email/role.
        like = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(like),
                User.email.ilike(like),
                User.role.ilike(like),
            )
        )
    result = paginate(query, page, per_page)
    # Serialize ORM items -> Pydantic responses (strips password_hash, etc.)
    result["items"] = [UserResponse.model_validate(u) for u in result["items"]]
    return result


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: DbSession, _admin: dict = Depends(require_admin)):
    """Create a user with an explicit role (admin only)."""
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=409, detail="Username already taken")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    role = body.role.value if body.role else Role.END_USER.value
    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: str, db: DbSession, _admin: dict = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str, body: UserUpdate, db: DbSession, _admin: dict = Depends(require_admin)
):
    """Partial update (only provided fields change). """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if body.username is not None:
        user.username = body.username
    if body.email is not None:
        user.email = body.email
    if body.password is not None:
        # Password must be re-hashed; NEVER store the raw value.
        user.password_hash = hash_password(body.password)
    if body.role is not None:
        user.role = body.role.value
    if body.is_active is not None:
        user.is_active = body.is_active

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, db: DbSession, _admin: dict = Depends(require_admin)):
    """Soft delete: mark inactive rather than removing the row."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.commit()
