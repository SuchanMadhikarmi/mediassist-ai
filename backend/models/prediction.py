# ============================================================
# backend/models/prediction.py
# Prediction ORM model — audit log for EVERY ML inference.
#
# University requirement: "Every prediction logged in DB (input, output,
# confidence, model_version, user, timestamp)". This table IS that log.
#
#   - input_data        : JSONB (flexible JSON blob of the raw model input)
#   - predicted_output  : the model's answer (yes/no, or class)
#   - confidence        : 0.0-1.0 probability from the model
#   - model_version     : which model artifact produced it (e.g. xgboost_v1)
#   - user_id           : who made the prediction (links to users.id)
#
# JSONB lets us store any-shaped input without a rigid column per field.
# ============================================================

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, NUMERIC
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )

    input_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    predicted_output: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float | None] = mapped_column(NUMERIC(5, 4), nullable=True)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    inference_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Prediction id={self.id} output={self.predicted_output} conf={self.confidence}>"
