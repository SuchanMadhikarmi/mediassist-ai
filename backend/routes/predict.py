# ============================================================
# backend/routes/predict.py
# ML Inference Endpoint — Phase 6.6.
#
# POST /api/predict
#   Body   : PredictionInput (validated 16 features)
#   Auth   : Bearer token (any logged-in role)
#   Returns: prediction + confidence + model version + prediction id
#
# On every prediction we:
#   1. validate input (Pydantic does ranges + categories)
#   2. run inference via ml.predictor (loads saved preprocessor + model)
#   3. measure inference time
#   4. log the prediction row to the `predictions` table (university
#      requirement: every prediction logged: input, output, confidence,
#      model_version, user, timestamp)
#   5. write an audit_log entry (enterprise audit trail)
# ============================================================

import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user_db
from ml.predictor import predict
from models import AuditLog, Prediction, User
from schemas.prediction import PredictionInput

router = APIRouter(prefix="/api/predict", tags=["predict"])


@router.post("")
def make_prediction(
    body: PredictionInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_db),
):
    """Run the ML model on validated input and log the result."""
    # --- 1. Convert the validated Pydantic model to a plain feature dict ---
    # We drop `model_name` (it's not a model feature) and keep the 16 inputs.
    features = body.model_dump(exclude={"model_name"})

    # --- 2. Run inference + time it ---
    # predict() loads the saved preprocessor + model (cached after first
    # call), transforms the row, and returns prediction + confidence.
    start = time.perf_counter()
    try:
        result = predict(features, model_name=body.model_name)
    except FileNotFoundError as exc:
        # Artifacts missing → tell the admin to run training, 500.
        raise HTTPException(status_code=500, detail=str(exc))
    inference_ms = int((time.perf_counter() - start) * 1000)

    # --- 3. Log the prediction row (audit trail for ML) ---
    pred = Prediction(
        user_id=user.id,
        input_data=features,
        predicted_output=result["prediction"],
        confidence=result["confidence"],
        model_version=result["model_version"],
        inference_time_ms=inference_ms,
    )
    db.add(pred)
    db.flush()  # ensure pred.id is populated before we reference it below

    # --- 4. Audit log entry (append-only enterprise trail) ---
    db.add(
        AuditLog(
            user_id=user.id,
            action="PREDICTION_CREATED",
            details={
                "prediction_id": pred.id,
                "model_name": result["model_name"],
                "predicted_output": result["prediction"],
                "confidence": result["confidence"],
            },
        )
    )
    db.commit()
    db.refresh(pred)

    # --- 5. Return a clean response ---
    return {
        "prediction_id": pred.id,
        "prediction": result["prediction"],
        "confidence": result["confidence"],
        "prob_no": result["prob_no"],      # for the visual probability bar
        "prob_yes": result["prob_yes"],    # for the visual probability bar
        "model_name": result["model_name"],
        "model_version": result["model_version"],
        "inference_time_ms": inference_ms,
        "created_at": pred.created_at.isoformat() if pred.created_at else None,
    }
