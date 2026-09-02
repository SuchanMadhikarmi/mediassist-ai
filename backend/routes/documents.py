# ============================================================
# backend/routes/documents.py
# CRUD over document METADATA (the actual PDF ingestion stays in /ingest).
#
# RBAC at the DATA level: end_users can only see documents whose
# rbac_label matches their own role (they can't list admin/expert docs).
# Admins see everything. Experts see admin+expert docs.
#
# This shows the "row-level security" pattern: filter the QUERY by role
# BEFORE returning — not just gating the ENDPOINT.
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from dependencies import get_current_user_db, paginate, require_admin, DbSession
from models import Document, User
from schemas.document import DocumentResponse

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _visible_docs_query(db: Session, user: User):
    """Return a query filtered by what THIS user may see.

    A user may only see documents with rbac_label in {their role, and
    any stricter roles they outrank}. Concretely:
      - admin    : sees all
      - expert   : sees expert + admin
      - end_user : sees end_user only
    """
    q = db.query(Document)
    if user.role == "admin":
        return q
    if user.role == "expert":
        return q.filter(or_(Document.rbac_label == "admin", Document.rbac_label == "expert"))
    # end_user (and 'viewer' alias) -> own label only
    return q.filter(Document.rbac_label == user.role)


@router.get("")
def list_documents(
    db: DbSession,
    user: User = Depends(get_current_user_db),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List documents visible to the caller (data-level RBAC) + search/paginate."""
    query = _visible_docs_query(db, user)
    if search:
        query = query.filter(Document.filename.ilike(f"%{search}%"))
    result = paginate(query, page, per_page)
    result["items"] = [DocumentResponse.model_validate(d) for d in result["items"]]
    return result


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(doc_id: str, db: DbSession, user: User = Depends(get_current_user_db)):
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    # Data-level RBAC: ensure the user may see THIS doc's label.
    if doc.rbac_label not in _visible_labels(user):
        raise HTTPException(status_code=403, detail="Not allowed to view this document")
    return doc


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document_meta(doc_id: str, db: DbSession, user: User = Depends(require_admin)):
    """Admin deletes document metadata. (Vector deletion is Phase 4 cleanup.)"""
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()


def _visible_labels(user: User) -> list[str]:
    """Which rbac_labels this user may read."""
    if user.role == "admin":
        return ["admin", "expert", "end_user"]
    if user.role == "expert":
        return ["admin", "expert"]
    return [user.role]
