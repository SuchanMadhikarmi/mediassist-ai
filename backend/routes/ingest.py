# ============================================================
# backend/routes/ingest.py
# POST /ingest — admin uploads a PDF for ingestion into the vector DB.
#
# SECURITY layering (ties Phase 3 together):
#   - require_role(Role.ADMIN) -> only admins may add documents (RBAC)
#   - rbac_label chosen from the caller's role -> enforces data-level access
#   - PII redaction applied to page text BEFORE embedding, so no PII
#     lands in the vector DB / prompts
# ============================================================

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ai_engine.ingestion import ingest_pdf
from security.rbac import require_role
from security.models import Role

router = APIRouter(prefix="/ingest", tags=["ingest"])


class IngestResponse(BaseModel):
    ingested: int
    doc_id: str
    source: str


@router.post("", response_model=IngestResponse)
async def ingest(
    file: UploadFile = File(...),
    user: dict = Depends(require_role(Role.ADMIN)),  # RBAC gate
):
    """Ingest an uploaded PDF. Returns how many chunks were stored."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # tag every chunk with the uploader's role for data-level RBAC
    rbac_label = user["role"]

    result = await ingest_pdf(
        pdf_bytes=pdf_bytes,
        source=file.filename,
        rbac_label=rbac_label,
        ingested_by=user["user_id"],
    )

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    return IngestResponse(
        ingested=result["ingested"],
        doc_id=result["doc_id"],
        source=result["source"],
    )
