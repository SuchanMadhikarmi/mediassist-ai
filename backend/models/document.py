# ============================================================
# backend/models/document.py
# Document ORM model — METADATA for ingested PDFs.
#
# NOTE: the actual vector chunks live in Qdrant (vector DB). This table
# stores the relational METADATA about each uploaded PDF (who uploaded,
# when, how many chunks, the RBAC label). This is a classic split:
#   - Qdrant    : the chunk VECTORS (semantic search)
#   - Postgres  : the document ROW (relational facts, RBAC, ownership)
#
# Foreign key 'uploaded_by' links to users.id — a one-to-many: one user
# can upload many documents.
# ============================================================

from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)

    # uploaded_by -> users.id. This enforces referential integrity at the
    # DB level: you cannot reference a user that doesn't exist.
    uploaded_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )

    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rbac_label: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename}>"
