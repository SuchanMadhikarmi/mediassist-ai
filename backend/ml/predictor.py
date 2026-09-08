"""
ml/predictor.py
───────────────
Loads the saved model + preprocessor and runs INFERENCE on new input.

This is the link between Phase 6.5 (training) and Phase 6.6 (the /api/predict
endpoint). The pipeline at train time was:

    raw features → [fitted preprocessor] → 51 features → [model] → prediction

At inference we MUST replay the exact same transformation, because the model
only knows how to read the 51-feature form it was trained on. That is why we
saved the FITTED preprocessor alongside the model.

CONCEPT (singleton / lazy loading):
The artifacts live on disk (.pkl). Reading a 677 KB model file on EVERY
request would be slow. So we load them ONCE into module-level variables the
first time they're needed (lazy), then reuse them — this is the classic
"cache the expensive setup" pattern. Same idea as get_crag_graph() in Phase 6.
"""

import os

import joblib

# Where the artifacts live (same dir as this module, in models/).
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

# Default model to serve. We pick the best one from training (xgboost).
# A version string for logging/matching in model_registry.
DEFAULT_MODEL_NAME = "xgboost"
DEFAULT_MODEL_FILE = "xgboost_v1.pkl"
DEFAULT_MODEL_VERSION = "xgboost_v1.0"
PREPROCESSOR_FILE = "preprocessor.pkl"

# Lazy singletons — filled on first use.
_preprocessor = None
_model = None
_model_version = None
_model_name = None


def _load_artifacts(model_name: str | None = None):
    """Load (once) the preprocessor + requested model into module globals.

    WHY pass model_name? So we can swap between xgboost and logistic
    regression at runtime. Defaults to the production choice (xgboost).
    """
    global _preprocessor, _model, _model_version, _model_name

    if _model is not None and _model_name == model_name:
        # Already loaded and it's the right model — nothing to do.
        return _preprocessor, _model

    name = model_name or DEFAULT_MODEL_NAME
    model_file = {
        "xgboost": "xgboost_v1.pkl",
        "logistic_regression": "logistic_regression_v1.pkl",
    }.get(name)
    if model_file is None:
        raise ValueError(f"Unknown model name: {name}")

    preprocessor_path = os.path.join(MODEL_DIR, PREPROCESSOR_FILE)
    model_path = os.path.join(MODEL_DIR, model_file)
    if not (os.path.exists(preprocessor_path) and os.path.exists(model_path)):
        raise FileNotFoundError(
            f"Artifacts missing. Run `python ml/train.py` first. "
            f"Need {preprocessor_path} and {model_path}"
        )

    _preprocessor = joblib.load(preprocessor_path)
    _model = joblib.load(model_path)
    _model_name = name
    _model_version = {"xgboost": "xgboost_v1.0", "logistic_regression": "lr_v1.0"}[name]

    return _preprocessor, _model


def predict(features: dict, model_name: str | None = None) -> dict:
    """Run inference on a single row of raw feature values.

    Args:
        features: dict of 16 raw feature values (the 15 inputs + no target).
        model_name: optional, "xgboost" (default) or "logistic_regression".

    Returns:
        {
            "prediction": "yes" | "no",
            "confidence": float 0..1 (probability of the PREDICTED class),
            "prob_no": float 0..1 (probability of 'no'),
            "prob_yes": float 0..1 (probability of 'yes'),
            "model_version": str (for logging / registry matching),
            "model_name": str,
        }

    CONCEPT (single-row input):
    The preprocessor expects a 2-D structure (many rows) or at least a list
    of one row. So we wrap the dict in a list. Our preprocessor is a
    ColumnTransformer which needs a DataFrame with the training columns, so
    we build one for a single row.
    """
    import pandas as pd

    preprocessor, model = _load_artifacts(model_name)

    # Build a one-row DataFrame with the exact training column order.
    # Column order matters — the preprocessor maps columns BY NAME, so order
    # is safe as long as names match the training set.
    row = pd.DataFrame([features])

    # Transform with the FITTED preprocessor (same as training).
    X = preprocessor.transform(row)

    # Predict the class ('yes'/'no') and the probabilities of each class.
    proba = model.predict_proba(X)[0]  # [P(no), P(yes)]
    pred_class = "yes" if model.predict(X)[0] == 1 else "no"

    # Confidence = probability of the PREDICTED class (max of the two).
    # CONVENTION: "I am 96% sure it's 'no'" — for a 'no' prediction that is
    # P(no) = 1 - P(yes). Showing what the model actually picked is far less
    # misleading than always printing P(yes) (the old code made a perfectly
    # confident 'no' read as a shaky 3.9%).
    confidence = round(float(proba[1 if pred_class == "yes" else 0]), 4)

    # Both probabilities travel with the response so the UI can show the
    # full picture (argmax label + a REAL probability for each side).
    # This is what makes a demo feel stable: when the label flips, the
    # user sees P(no) 60.8% -> 28.0% and P(yes) 39.2% -> 72.0% glide
    # smoothly across the 50% boundary instead of snapping unpredictably.
    prob_no, prob_yes = round(float(proba[0]), 4), round(float(proba[1]), 4)

    return {
        "prediction": pred_class,
        "confidence": confidence,
        "prob_no": prob_no,
        "prob_yes": prob_yes,
        "model_version": _model_version,
        "model_name": _model_name,
    }


def get_model_info() -> dict:
    """Return info about the loaded/production model (used by the registry)."""
    name = DEFAULT_MODEL_NAME
    return {
        "model_name": name,
        "model_version": DEFAULT_MODEL_VERSION,
        "artifact_path": os.path.join(MODEL_DIR, DEFAULT_MODEL_FILE),
    }


if __name__ == "__main__":
    # Quick self-test with a made-up (but valid) client row.
    sample = {
        "age": 35, "job": "admin.", "marital": "married", "education": "secondary",
        "default": "no", "balance": 1500, "housing": "no", "loan": "no",
        "contact": "cellular", "day": 15, "month": "may", "duration": 220,
        "campaign": 2, "pdays": -1, "previous": 0, "poutcome": "unknown",
    }
    print(predict(sample))
