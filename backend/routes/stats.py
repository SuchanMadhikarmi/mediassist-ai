# ============================================================
# backend/routes/stats.py
# GET /api/stats — dashboard aggregation endpoint (Phase 7.5).
#
# CONCEPT (this phase's core lesson — aggregation vs row-queries):
# Every endpoint until now RETURNED ROWS (CRUD lists). A dashboard wants
# NUMBERS that summarize many rows. We compute them IN THE DATABASE:
#
#     SQL:   SELECT predicted_output, COUNT(*) FROM predictions
#            GROUP BY predicted_output
#     SQLAlch: db.query(Prediction.predicted_output,
#                       func.count(Prediction.id))
#                 .group_by(Prediction.predicted_output)
#
# WHY in SQL and not Python? Streaming 1M rows into Python to count them
# is slow and memory-hungry. GROUP BY counts on the server and ships back
# a handful of numbers. Same answer, tiny network cost. This is THE
# reusable pattern for every chart/report in every project.
#
# RBAC: staff-only (admin/expert) — the same audience as the audit log.
# ============================================================

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func

from dependencies import require_staff, DbSession
from models import AuditLog, Document, ErpOrder, ModelRegistry, Prediction, User
from schemas.stats import (
    ActiveModel,
    LabelCount,
    PredictionQuality,
    RecentActivity,
    StatsResponse,
)

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
def dashboard_stats(db: DbSession, _staff=Depends(require_staff)) -> StatsResponse:
    """Return the full dashboard payload: counts + quality + trends."""

    # ── Scalar aggregate helper ────────────────────────────────────
    # db.query(func.count(X.id)).scalar()  → ONE number (COUNT on the DB).
    # `.scalar()` unwraps the single-cell result; `.first()[0]` would work too.
    def count_rows(model) -> int:
        return db.query(func.count(model.id)).scalar() or 0

    # ── GROUP BY helper ────────────────────────────────────────────
    # SELECT col, COUNT(*) ... GROUP BY col  → list of (value, count).
    # One generic helper serves users-by-role, by-model, by-output and
    # the audit breakdown — four call sites, one pattern.
    def grouped(column) -> list[LabelCount]:
        rows = db.query(column, func.count()).group_by(column).all()
        return [
            LabelCount(label=str(value if value is not None else "(none)"), count=count)
            for value, count in rows
        ]

    # ── totals: a few independent COUNT(*)s ────────────────────────
    totals = {
        "predictions": count_rows(Prediction),
        "users": count_rows(User),
        "documents": count_rows(Document),
        "erp_orders": count_rows(ErpOrder),
        "model_versions": count_rows(ModelRegistry),
    }

    # ── grouped breakdowns: ONE query each ─────────────────────────
    users_by_role = grouped(User.role)
    predictions_by_model = grouped(Prediction.model_version)
    predictions_by_output = grouped(Prediction.predicted_output)

    # ── quality metrics (AVG + conditional COUNT) ──────────────────
    # Conditional count: the FILTER clause turns COUNT(*) into
    # "count only rows where predicted_output == 'yes'". This is how we
    # compute a share WITHOUT a second GROUP BY.
    total_preds = count_rows(Prediction)
    positive = db.query(
        func.count().filter(Prediction.predicted_output == "yes")
    ).scalar() or 0
    quality = PredictionQuality(
        avg_confidence=_as_float(db.query(func.avg(Prediction.confidence)).scalar()),
        avg_inference_time_ms=_as_float(
            db.query(func.avg(Prediction.inference_time_ms)).scalar()
        ),
        positive_rate=round(positive / total_preds, 4) if total_preds else None,
    )

    # ── model registry: which model versions are trained/serving ───
    model_registry = [
        ActiveModel(
            model_name=m.model_name,
            version=m.version,
            is_active=m.is_active,
            artifact_path=m.artifact_path,
            metrics=m.metrics,
        )
        for m in db.query(ModelRegistry).order_by(ModelRegistry.trained_at.desc()).all()
    ]

    # ── audit breakdown + recent activity ──────────────────────────
    audit_breakdown = grouped(AuditLog.action)
    recent_rows = (
        db.query(AuditLog, User.username)
        .outerjoin(User, AuditLog.user_id == User.id)  # left join: keep logs w/o user
        .order_by(AuditLog.created_at.desc())
        .limit(8)
        .all()
    )
    recent_activity = [
        RecentActivity(action=log.action, username=username, created_at=log.created_at)
        for log, username in recent_rows
    ]

    # ── time series: predictions per day, last 7 calendar days ─────
    # date_trunc('day', ts)  →  truncates each timestamp to midnight of
    # its day, so GROUP BY gives ONE bucket per day. This is the
    # dashboard's trend line.
    cutoff = datetime.now(timezone.utc) - timedelta(days=6)
    day = func.date_trunc("day", Prediction.created_at)
    daily_rows = (
        db.query(day.label("bucket"), func.count(Prediction.id))
        .filter(Prediction.created_at >= cutoff)
        .group_by(day)
        .order_by(day.asc())
        .all()
    )
    predictions_last_7_days = [
        LabelCount(label=bucket.strftime("%Y-%m-%d"), count=count)
        for bucket, count in daily_rows
    ]

    return StatsResponse(
        totals=totals,
        users_by_role=users_by_role,
        predictions_by_model=predictions_by_model,
        predictions_by_output=predictions_by_output,
        quality=quality,
        model_registry=model_registry,
        audit_breakdown=audit_breakdown,
        recent_activity=recent_activity,
        predictions_last_7_days=predictions_last_7_days,
    )


def _as_float(value) -> float | None:
    """NUMERIC/Decimal from Postgres → plain float for JSON (round to 4dp).

    NUMERIC columns return Decimal, which FastAPI cannot serialize to JSON
    directly. Convert + round for a clean dashboard.
    """
    if value is None:
        return None
    return round(float(value), 4)