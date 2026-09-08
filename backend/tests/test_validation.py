# ============================================================
# backend/tests/test_validation.py
# Deterministic tests for the Pydantic input-validation gate
# (Phase 6.6 — the "422 gate" on the ML inference endpoint).
#
# WHY: /api/predict trusts Pydantic to reject malformed input BEFORE it
# reaches the ML model (job="wizard" would break the OneHotEncoder; an
# age of 200 is nonsense). These tests pin the contract so a future
# schema edit can't silently accept garbage.
# ============================================================

import pytest
from pydantic import ValidationError

from schemas.prediction import PredictionInput


VALID = {
    "age": 42,
    "job": "technician",
    "marital": "married",
    "education": "secondary",
    "default": "no",
    "balance": 1000.0,
    "housing": "yes",
    "loan": "no",
    "contact": "cellular",
    "day": 15,
    "month": "may",
    "duration": 200,
    "campaign": 1,
    "pdays": -1,
    "previous": 0,
    "poutcome": "unknown",
}


class TestPredictionInput:
    def test_valid_payload_parses(self):
        p = PredictionInput(**VALID)
        assert p.job == "technician"
        assert p.model_name is None  # optional field defaults

    def test_optional_model_name_accepted(self):
        p = PredictionInput(**{**VALID, "model_name": "logistic_regression"})
        assert p.model_name == "logistic_regression"

    # ── categorical garbage is rejected ──
    @pytest.mark.parametrize("bad_field", ["job", "marital", "education", "contact", "month", "poutcome"])
    def test_unknown_category_rejected(self, bad_field):
        payload = {**VALID, bad_field: "wizard"}  # nonsense category
        with pytest.raises(ValidationError):
            PredictionInput(**payload)

    def test_unknown_binary_value_rejected(self):
        for field in ("default", "housing", "loan"):
            with pytest.raises(ValidationError):
                PredictionInput(**{**VALID, field: "maybe"})

    # ── numeric range violations are rejected (Field ge/le) ──
    @pytest.mark.parametrize(
        ("field", "value"),
        [("age", 200), ("age", 12), ("day", 32), ("duration", -5), ("campaign", 0), ("previous", -2), ("pdays", -2)],
    )
    def test_out_of_range_number_rejected(self, field, value):
        with pytest.raises(ValidationError):
            PredictionInput(**{**VALID, field: value})

    def test_negative_balance_is_allowed(self):
        # Bank dataset uses balance as a real euro amount; debt is normal.
        p = PredictionInput(**{**VALID, "balance": -1500.0})
        assert p.balance == -1500.0