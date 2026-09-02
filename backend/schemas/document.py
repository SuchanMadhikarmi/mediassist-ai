# ============================================================
# backend/schemas/document.py
# Pydantic schemas for Document metadata.
# ============================================================

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    """Metadata returned for an ingested document. No internal internals."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    uploaded_by: str | None
    chunk_count: int | None
    rbac_label: str
    file_size_bytes: int | None
    created_at: datetime
