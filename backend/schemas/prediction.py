# ============================================================
# backend/schemas/prediction.py
# Pydantic schemas for ML predictions.
# ============================================================

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PredictionCreate(BaseModel):
    """Client submits new prediction input. Model computes the rest."""
    input_data: dict = Field(description="Feature values for the ML model")
    model_version: str = Field(min_length=1, description="e.g. xgboost_v1")


class PredictionReview(BaseModel):
    """Expert overrides/reviews a prediction (university: expert can override)."""
    reviewed_output: str = Field(min_length=1, max_length=50)
    is_approved: bool = True


class PredictionResponse(BaseModel):
    """What the API returns for a prediction. Full audit trail."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str | None
    input_data: dict
    predicted_output: str
    confidence: float | None
    model_version: str
    inference_time_ms: int | None
    created_at: datetime
