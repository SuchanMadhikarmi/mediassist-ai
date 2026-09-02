# ============================================================
# backend/schemas/user.py
# Pydantic schemas for User — the API contract around users.
#
# Three schemas for three uses (the classic pattern):
#   - UserCreate  : what admin POSTs to create (or public registers)
#   - UserUpdate  : what admin PUTs to change
#   - UserResponse: what the API returns (NEVER shows password_hash)
#
# model_config = ConfigDict(from_attributes=True) lets Pydantic build a
# response directly from an ORM object (User model). Without it we'd have
# to manually copy every field.
# ============================================================

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from security.models import Role


class UserCreate(BaseModel):
    """Admin creates any user, or public registration (public forces end_user)."""
    username: str = Field(min_length=3, max_length=50, description="3-50 chars")
    email: EmailStr = Field(max_length=100)
    password: str = Field(min_length=8, max_length=128, description="min 8 chars")

    # Optional role. IMPORTANT: registration endpoint IGNORES this and
    # forces end_user — only an authorized admin path may set admin/expert.
    role: Role | None = None


class UserUpdate(BaseModel):
    """Admin updates a user. All fields optional (partial update)."""
    username: str | None = Field(default=None, min_length=3, max_length=50)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: Role | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    """What the API returns for a user. NO password_hash — security by omission."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
