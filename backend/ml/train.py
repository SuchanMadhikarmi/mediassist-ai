"""
ml/train.py
───────────
Orchestrates the training pipeline.

This is the "controller" that wires the ML steps together:
  load → split → preprocess → (balance) → train → evaluate → save

We build it in stages. The full pipeline:
  load → STRATIFIED split → preprocess (fit on TRAIN only)
  → balance (SMOTE, train only) → train → evaluate → save

CONCEPT (the 3-way split):
  - TRAIN (70%):  the model LEARNS from this.
  - VALID (15%):  we tune hyperparameters on this (not trained on).
  - TEST (15%):   held out until the very end, for the FINAL honest score.
We must NEVER peek at test while training/tuning, or scores are dishonest.

CONCEPT (stratified split):
Keeps the 88/12 class proportion in EVERY split, so the rare 'yes' class
is represented fairly in train/valid/test alike. Random splitting could
give test a distorted share of the rare class.

CONCEPT (leakage prevention, applied here):
We fit the preprocessor (scaler + encoder) on X_train ONLY, then transform
train/valid/test with the SAME fitted object. Fitting on all data would let
the model "see" test statistics → inflated, dishonest scores.

For reproducibility we set a random_state seed: same seed → same split every
run. This makes our experiments comparable between runs.
"""

import os

import joblib
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

from ml.data_loader import load_data
from ml.preprocessing import build_preprocessor

# Reproducibility: same seed every run = same split + same results.
RANDOM_STATE = 42

# Split proportions.
TRAIN_SIZE = 0.70
VALID_SIZE = 0.15
TEST_SIZE = 0.15

# Where to save processed artifacts later.
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")


def split_data(X, y):
    """Stratified split into train/valid/test (70/15/15).

    We do it in two steps:
      Step A: split off TEST (15%).
      Step B: split the remaining 85% into TRAIN (70% of total) and VALID.
    This is equivalent to a single 3-way split, done with two 2-way calls.

    stratify=y tells sklearn to preserve class proportions in each split.
    """

    # Step A: take out the test set.
    X_train_val, X_test, y_train_val, y_test = train_test_split(
        X, y,
        test_size=TEST_SIZE,          # 15% to test
        stratify=y,                   # keep class proportions
        random_state=RANDOM_STATE,
    )

    # Step B: split the remaining 85% into train + valid.
    # valid_size relative to the remaining set: 0.15/0.85 ≈ 0.1765
    X_train, X_valid, y_train, y_valid = train_test_split(
        X_train_val, y_train_val,
        test_size=VALID_SIZE / (TRAIN_SIZE + VALID_SIZE),  # ~0.176 → 15% of total
        stratify=y_train_val,
        random_state=RANDOM_STATE,
    )

    return X_train, X_valid, X_test, y_train, y_valid, y_test


def main():
    # 1. Load raw data.
    df = load_data()
    print(f"Loaded: {df.shape[0]} rows, {df.shape[1]} cols")

    # 2. Separate features (X) from target (y).
    #    X = every column except the target 'y'; y = the target column.
    X = df.drop(columns=["y"])
    y = df["y"]  # 'yes'/'no' strings — we'll encode to 1/0 later

    # 3. Stratified split.
    X_train, X_valid, X_test, y_train, y_valid, y_test = split_data(X, y)
    print(
        f"Split -> train {X_train.shape[0]} | valid {X_valid.shape[0]} | "
        f"test {X_test.shape[0]}"
    )

    # 4. Build + FIT the preprocessor on TRAIN ONLY (leak prevention).
    preprocessor = build_preprocessor()
    preprocessor.fit(X_train)          # ⚠️ learn parameters from TRAIN data only

    # 5. Transform train/valid/test with the SAME fitted preprocessor.
    X_train_pp = preprocessor.transform(X_train)
    X_valid_pp = preprocessor.transform(X_valid)
    X_test_pp = preprocessor.transform(X_test)

    print(f"After preprocessing -> train {X_train_pp.shape} | "
          f"valid {X_valid_pp.shape} | test {X_test_pp.shape}")

    # ── Persist the fitted preprocessor ───────────────────────────
    # We must save the FITTED preprocessor, because at INFERENCE time
    # (Phase 6.6) we need to transform a brand-new input with the exact
    # same column layout the model learned. Save it once, reuse everywhere.
    os.makedirs(MODEL_DIR, exist_ok=True)
    preprocessor_path = os.path.join(MODEL_DIR, "preprocessor.pkl")
    joblib.dump(preprocessor, preprocessor_path)
    print(f"Saved fitted preprocessor -> {preprocessor_path}")

    # ── Verify class proportions are preserved (stratification worked) ──
    print("\nStratification check (% 'yes' in each split):")
    for name, yy in [("train", y_train), ("valid", y_valid), ("test", y_test)]:
        pct_yes = (yy == "yes").mean() * 100
        print(f"  {name:6s}: {pct_yes:.2f}% yes")

    # =============================================================
    # STAGE 2 — Target encoding + class imbalance (SMOTE)
    # =============================================================

    # ── 2a. Encode the target: 'yes'/'no' strings → 1/0 numbers ──
    # Most sklearn models need numeric target. We map no=0, yes=1.
    # '1' = positive class = we WANT to detect a subscriber.
    le = LabelEncoder()
    y_train_enc = le.fit_transform(y_train)   # fit on TRAIN only
    y_valid_enc = le.transform(y_valid)       # apply same encoder
    y_test_enc = le.transform(y_test)
    # le.classes_ is ['no','yes'] so index 1 == 'yes' (the positive class).
    print("\nEncoded target classes:", list(le.classes_))

    # ── 2b. SMOTE — rebalance the TRAINING set only ──────────────
    # We need more 'yes' samples to train on, so the model doesn't just
    # learn "always say no". SMOTE creates synthetic 'yes' points.
    #
    # ⚠️ LEAKAGE RULE: apply SMOTE to X_train/y_train ONLY. Never to
    # valid/test — those must stay real/unmodified so evaluation is honest.
    print(f"\nClass counts in train BEFORE SMOTE: {pd.Series(y_train_enc).value_counts().to_dict()}")
    smote = SMOTE(random_state=RANDOM_STATE)
    X_train_bal, y_train_bal = smote.fit_resample(X_train_pp, y_train_enc)
    print(f"Class counts in train AFTER SMOTE: {pd.Series(y_train_bal).value_counts().to_dict()}")

    # valid/test stay UNBALANCED (real world distribution) — that's correct.
    print(
        "Note: valid/test remain at the real 88/12 distribution (honest eval).\n"
    )

    # =============================================================
    # STAGE 3 — Train the two models
    # =============================================================

    # ── 3a. Baseline: Logistic Regression ────────────────────────
    # Why 'class_weight="balanced"'? Even though SMOTE balanced the
    # training data, this adds a SECOND safeguard: it makes the model
    # itself penalize misclassifying the minority class more. Belt + braces.
    #
    # max_iter raised because gradient descent for LR may need more
    # iterations to converge on 51 features.
    lr_model = LogisticRegression(max_iter=1000, class_weight="balanced")
    lr_model.fit(X_train_bal, y_train_bal)
    print("Trained Logistic Regression (baseline).")

    # ── 3b. Main model: XGBoost ─────────────────────────────────
    # 'scale_pos_weight' is XGBoost's native imbalance handling:
    #   ratio = count(negative) / count(positive) in the ORIGINAL train.
    # It tells XGBoost to weigh the rare 'yes' class more heavily.
    # We compute it from the UNBALANCED train (real ratio), NOT the SMOTE-
    # balanced one — those are two independent imbalance strategies, and
    # using both real-ratio weight + SMOTE is fine.
    neg = (y_train_enc == 0).sum()
    pos = (y_train_enc == 1).sum()
    scale_pos_weight = neg / pos   # ~7.5: the real yes:no ratio

    xgb_model = XGBClassifier(
        n_estimators=200,           # number of trees
        max_depth=6,                # tree depth (6 = good default for tabular)
        learning_rate=0.1,          # step size (lower = slower but often better)
        scale_pos_weight=scale_pos_weight,
        eval_metric="logloss",
        use_label_encoder=False,    # we already encoded the target; disables legacy path
        random_state=RANDOM_STATE,
    )
    xgb_model.fit(
        X_train_bal, y_train_bal,
        # Watch performance on VALIDATION during training (never test).
        eval_set=[(X_valid_pp, y_valid_enc)],
        verbose=False,
    )
    print("Trained XGBoost (main model).")

    # =============================================================
    # STAGE 4 — Evaluate BOTH models on the TEST set
    # =============================================================
    # NOW we finally touch the held-out test set — the honest evaluation.
    # Everything before this must not have "seen" test.
    results = {}
    models = {"logistic_regression": lr_model, "xgboost": xgb_model}
    for name, model in models.items():
        y_pred = model.predict(X_test_pp)                 # hard class predictions
        y_proba = model.predict_proba(X_test_pp)[:, 1]    # probability of 'yes'
        acc = accuracy_score(y_test_enc, y_pred)
        prec, rec, f1, _ = precision_recall_fscore_support(y_test_enc, y_pred, average="macro")
        auc = roc_auc_score(y_test_enc, y_proba)
        cm = confusion_matrix(y_test_enc, y_pred)
        results[name] = {
            "accuracy": round(acc, 4),
            "precision_macro": round(prec, 4),
            "recall_macro": round(rec, 4),
            "f1_macro": round(f1, 4),
            "roc_auc": round(auc, 4),
            "confusion_matrix": cm.tolist(),
        }
        print(f"\n===== {name.upper()} =====")
        print(f"Accuracy : {acc:.4f} | ROC-AUC: {auc:.4f}")
        print(f"Precision(macro): {prec:.4f} | Recall(macro): {rec:.4f} | F1(macro): {f1:.4f}")
        print("Confusion matrix [[TN FP], [FN TP]]:")
        print(cm)
        print("Classification report:")
        print(classification_report(y_test_enc, y_pred, target_names=["no", "yes"]))

    # =============================================================
    # STAGE 5 — Save artifacts (.pkl) for inference (Phase 6.6)
    # =============================================================
    # Save each trained model with joblib. At inference time the API will
    # load BOTH the saved preprocessor (to transform input) and the model
    # (to predict). Naming includes the version so we can track models in
    # the registry (model_registry table) and pick one to serve.
    for name, model in models.items():
        model_path = os.path.join(MODEL_DIR, f"{name}_v1.pkl")
        joblib.dump(model, model_path)
        print(f"Saved model artifact -> {model_path}")

    # ── Print a clean comparison table ──────────────────────────
    print("\n" + "=" * 64)
    print("MODEL COMPARISON (on held-out TEST set)")
    print("=" * 64)
    print(
        f"{'Model':<20}{'Acc':<8}{'Prec(m)':<10}{'Recall(m)':<11}{'F1(m)':<8}{'AUC':<8}"
    )
    for name, r in results.items():
        print(
            f"{name:<20}{r['accuracy']:<8}{r['precision_macro']:<10}"
            f"{r['recall_macro']:<11}{r['f1_macro']:<8}{r['roc_auc']:<8}"
        )
    print("=" * 64)

    # The model we choose to serve in production (Phase 6.6).
    best_name = max(results, key=lambda n: results[n]["roc_auc"])
    print(f"Best model by ROC-AUC: {best_name}")

    # =============================================================
    # STAGE 6 — Register models in model_registry (needs Postgres)
    # =============================================================
    # Record each trained model's metrics + hyperparameters + artifact in
    # the DB so we can version and trace them. Best model (xgboost) is
    # marked is_active=True (the one /api/predict serves by default).
    hyperparameters = {
        "logistic_regression": {
            "max_iter": 1000,
            "class_weight": "balanced",
        },
        "xgboost": {
            "n_estimators": 200,
            "max_depth": 6,
            "learning_rate": 0.1,
            "scale_pos_weight": round(neg / pos, 3) if pos else None,
            "eval_metric": "logloss",
        },
    }
    register_models(results, hyperparameters)

    return results


def register_models(
    results: dict,
    hyperparameters: dict,
    trained_by: str | None = None,
):
    """Register trained models in the `model_registry` table (Postgres).

    CONCEPT (model registry):
    A registry is a version log of every model trained: which artifact file,
    its metrics, hyperparameters, and who trained it. This lets us always
    trace WHICH model produced a given prediction, and flip `is_active` to
    serve a different version — proper model versioning (university req).

    This step needs Postgres. We guard it so training still succeeds if the
    DB is down (offline dev), but print a warning.

    Args:
        results: {model_name: {metrics...}} from training.
        hyperparameters: {model_name: {hyperparams...}}.
        trained_by: user id of who ran training (optional).
    """
    try:
        from database import SessionLocal
        from models import ModelRegistry
    except Exception as exc:  # noqa: BLE001 - DB import/setup may fail offline
        print(f"⚠️ Could not connect to DB for registration (skip): {exc}")
        return

    # A deterministic hash of the raw data so we can track WHICH dataset
    # version a model was trained on.
    try:
        from ml.data_loader import RAW_CSV
        import hashlib
        h = hashlib.sha256()
        with open(RAW_CSV, "rb") as f:
            h.update(f.read())
        data_hash = h.hexdigest()[:16]
    except Exception:  # noqa: BLE001
        data_hash = None

    with SessionLocal() as db:
        for name in results:
            hp = hyperparameters.get(name, {})
            # Compute the artifact filename the same way train.py saved it.
            artifact = os.path.join(MODEL_DIR, f"{name}_v1.pkl")
            # Library-defined version string (matches predictor.py).
            version = {"logistic_regression": "lr_v1.0", "xgboost": "xgboost_v1.0"}[name]

            # Upsert: if this model+version already registered, update it.
            existing = (
                db.query(ModelRegistry)
                .filter(
                    ModelRegistry.model_name == name,
                    ModelRegistry.version == version,
                )
                .first()
            )
            if existing is None:
                db.add(
                    ModelRegistry(
                        model_name=name,
                        version=version,
                        artifact_path=artifact,
                        metrics=results[name],
                        hyperparameters=hp,
                        training_data_hash=data_hash,
                        trained_by=trained_by,
                        is_active=(name == "xgboost"),  # serve the best one
                    )
                )
            else:
                existing.metrics = results[name]
                existing.hyperparameters = hp
            db.commit()
            print(f"Registered model in model_registry: {name} v{version}")
    return results


if __name__ == "__main__":
    main()
