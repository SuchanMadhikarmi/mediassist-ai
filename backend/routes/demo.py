# ============================================================
# backend/routes/demo.py
# TEMPORARY demo endpoints to PROVE the Phase 3 security layer works.
# We can delete these once real AI endpoints exist (Phase 5+).
#
# These show, end to end:
#   - get_current_user  : requires a valid JWT  (authentication)
#   - require_role      : restricts to a role    (authorization / RBAC)
#   - redact_pii        : strips PII from text   (data masking)
# ============================================================

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from security.auth import get_current_user
from security.models import Role
from security.pii_redactor import redact_pii
from security.rbac import require_role

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoQuery(BaseModel):
    text: str


@router.get("/whoami")
def whoami(user: dict = Depends(get_current_user)):
    """Authentication demo: requires a valid JWT, returns who you are."""
    return {"authenticated_as": user}


@router.get("/admin-only")
def admin_only(user: dict = Depends(require_role(Role.ADMIN))):
    """RBAC demo: only the 'admin' role may call this."""
    return {"message": "You are an admin. This secret is now visible.", "user": user}


@router.post("/redact")
def redact(body: DemoQuery):
    """PII demo: show original vs redacted text (works pre-auth, no token needed)."""
    return {"original": body.text, "redacted": redact_pii(body.text)}
