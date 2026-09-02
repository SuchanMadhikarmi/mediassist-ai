# ============================================================
# backend/models/model_registry.py
# ModelRegistry ORM model — tracks trained ML model versions.
#
# University: "model saved as artifact (.pkl)". This table records each
# version we trained: which file, its metrics, hyperparameters, and who
# trained it. This gives us model versioning — we can always look up the
# exact artifact + metrics behind any prediction.
#
#   - artifact_path : where the .pkl lives on disk
#   - metrics       : JSONB {accuracy, precision, recall, f1, roc_auc}
#   - is_active     : which version is currently serving inference
# ============================================================

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    hyperparameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    training_data_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    trained_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<ModelRegistry {self.model_name} v{self.version} active={self.is_active}>"
