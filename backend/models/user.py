# ============================================================
# backend/models/user.py
# User ORM model — maps the User Python class to the 'users' table.
#
# This is the REPLACEMENT for the hardcoded MOCK_USERS dict in
# routes/auth.py. Same concept (a user has username/password/role),
# but now persisted in PostgreSQL and queryable.
#
# ORM mapping: each class attribute below maps to a COLUMN.
#   - __tablename__  : the actual table name in Postgres
#   - Mapped[...]    : type annotation (SQLAlchemy 2.0 style)
#   - mapped_column  : the column definition (name, type, constraints)
#
# The Role enum lives in security/models.py to avoid a circular import.
# ============================================================

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from security.models import Role


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    # UUID primary key (globally unique, better for distributed systems
    # than sequential ints, and can't be enumerated/guessed by outsiders).
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    # UNIQUE => Postgres enforces no two users share a username/email.
    # index=True => fast lookup by username at login time.
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)

    # NEVER store plaintext passwords — only the bcrypt hash.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Role: 'admin' | 'expert' | 'end_user' (3 roles per university req).
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=Role.END_USER.value)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_utcnow(), nullable=False
    )

    def __repr__(self) -> str:  # readable representation for debugging/logs
        return f"<User id={self.id} username={self.username} role={self.role}>"
