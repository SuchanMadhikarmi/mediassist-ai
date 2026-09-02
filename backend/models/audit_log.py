# ============================================================
# backend/models/audit_log.py
# AuditLog ORM model — immutable trail of important actions.
#
# WHY: university requires an audit trail, and every enterprise app
# wants one. Whenever a sensitive action happens (login, delete,
# prediction, HITL approve/deny), we INSERT a row here. Audit logs are
# append-only by design — you never UPDATE/DELETE these rows, only add.
#
#   - action    : human-readable verb ("USER_LOGIN", "DOCUMENT_DELETE")
#   - details   : JSONB extra context (object ids, before/after state)
#   - ip_address: who from where (for forensics)
#   - user_id   : which user triggered it
# ============================================================

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )

    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} action={self.action}>"
