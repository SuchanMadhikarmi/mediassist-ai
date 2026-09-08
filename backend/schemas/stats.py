# ============================================================
# backend/schemas/stats.py
# Pydantic response models for GET /api/stats (Phase 7.5).
#
# These declare the EXACT dashboard payload contract. The frontend
# (Phase 8) can build every chart from this one response — no other
# endpoint needed. This is the "single source of truth" for what the
# dashboard knows about the system.
# ============================================================

from datetime import datetime

from pydantic import BaseModel


class LabelCount(BaseModel):
    """One bucket of a GROUP BY: a value + how many rows fall in it.

    Covers ALL grouped stats (users by role, predictions by model,
    predictions by output, audit by action, per-day series) with one
    shape — the frontend renders them all with ONE generic bar-chart
    component.
    """

    label: str
    count: int


class PredictionQuality(BaseModel):
    """The 'how healthy is the ML service' card."""

    avg_confidence: float | None = None
    avg_inference_time_ms: float | None = None
    positive_rate: float | None = None  # share of outputs == "yes"


class ActiveModel(BaseModel):
    """One row from model_registry, drawn as a model card."""

    model_name: str
    version: str
    is_active: bool
    artifact_path: str | None = None
    metrics: dict | None = None


class RecentActivity(BaseModel):
    """One audit-log line enriched with the acting user's username."""

    action: str
    username: str | None = None
    created_at: datetime


class StatsResponse(BaseModel):
    """Everything the dashboard needs in ONE response."""

    totals: dict[str, int]
    users_by_role: list[LabelCount]
    predictions_by_model: list[LabelCount]
    predictions_by_output: list[LabelCount]
    quality: PredictionQuality
    model_registry: list[ActiveModel]
    audit_breakdown: list[LabelCount]
    recent_activity: list[RecentActivity]
    predictions_last_7_days: list[LabelCount]