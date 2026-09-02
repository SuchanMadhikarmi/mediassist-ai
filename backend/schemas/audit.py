# ============================================================
# backend/schemas/audit.py
# Pydantic schema for AuditLog responses (admin/expert viewer).
# ============================================================

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str | None
    action: str
    details: dict | None
    ip_address: str | None
    created_at: datetime
