# ============================================================
# backend/routes/predictions.py
# CRUD over ML prediction logs + expert review.
#
# Role-based visibility (university requirement):
#   - admin / expert : see ALL predictions
#   - end_user       : see ONLY their own predictions
#
# This is the "ownership scoping" pattern — the query is filtered by
# user_id for end_users, which is the standard multi-tenant isolation.
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from dependencies import get_current_user_db, paginate, require_staff, DbSession
from models import Prediction, User
from schemas.prediction import PredictionCreate, PredictionReview, PredictionResponse

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.get("")
def list_predictions(
    db: DbSession,
    user: User = Depends(get_current_user_db),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List predictions. Admin/expert -> all; end_user -> own only."""
    query = db.query(Prediction)
    # Ownership scoping: non-staff see only their own rows.
    if user.role not in ("admin", "expert"):
        query = query.filter(Prediction.user_id == user.id)
    if search:
        query = query.filter(Prediction.predicted_output.ilike(f"%{search}%"))
    result = paginate(query, page, per_page)
    result["items"] = [PredictionResponse.model_validate(p) for p in result["items"]]
    return result


@router.post("", response_model=PredictionResponse, status_code=status.HTTP_201_CREATED)
def create_prediction(
    body: PredictionCreate, db: DbSession, user: User = Depends(get_current_user_db)
):
    """Placeholder submission — real ML inference lands in Phase 6.6.
    For now we store a stub row so the CRUD + RBAC flow is testable."""
    pred = Prediction(
        user_id=user.id,
        input_data=body.input_data,
        predicted_output="pending",
        model_version=body.model_version,
    )
    db.add(pred)
    db.commit()
    db.refresh(pred)
    return pred


@router.put("/{pred_id}/review", response_model=PredictionResponse)
def review_prediction(
    pred_id: str,
    body: PredictionReview,
    db: DbSession,
    user: User = Depends(require_staff),  # expert or admin
):
    """Expert/admin reviews/overrides a prediction (university requirement)."""
    pred = db.get(Prediction, pred_id)
    if pred is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    pred.predicted_output = body.reviewed_output
    # Confidence set to 1.0 meaning "human-confirmed" (expert override).
    if body.is_approved:
        pred.confidence = 1.0
    db.commit()
    db.refresh(pred)
    return pred


@router.delete("/{pred_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prediction(pred_id: str, db: DbSession, user: User = Depends(require_staff)):
    """Admin/expert deletes a prediction record."""
    pred = db.get(Prediction, pred_id)
    if pred is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    db.delete(pred)
    db.commit()
