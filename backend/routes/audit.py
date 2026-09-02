# ============================================================
# backend/routes/audit.py
# Audit log viewer — admin/expert only (read-only, paginated).
#
# Audit logs are APPEND-ONLY: this router only lists, never edits.
# The 'action' search lets an admin filter e.g. all USER_LOGIN events.
# ============================================================

from fastapi import APIRouter, Depends, Query

from dependencies import paginate, require_staff, DbSession
from models import AuditLog
from schemas.audit import AuditResponse

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(
    db: DbSession,
    _staff: dict = Depends(require_staff),
    action: str | None = Query(None, description="Filter by action verb"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Paginated audit trail, newest first. Admin/expert only."""
    query = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    result = paginate(query, page, per_page)
    result["items"] = [AuditResponse.model_validate(a) for a in result["items"]]
    return result
