# ============================================================
# backend/schemas/prediction.py
# Pydantic schemas for ML predictions.
# ============================================================

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Valid categorical values — hard-coded from the Bank Marketing dataset
# (see backend/data/bank_marketing/). We validate against these so a
# client can't send nonsense like job="wizard", which the OneHotEncoder
# never saw and would silently mishandle.
VALID_JOBS = [
    "admin.", "blue-collar", "entrepreneur", "housemaid", "management",
    "retired", "self-employed", "services", "student", "technician",
    "unemployed", "unknown",
]
VALID_MARITAL = ["divorced", "married", "single"]
VALID_EDUCATION = ["primary", "secondary", "tertiary", "unknown"]
VALID_BINARY = ["no", "yes"]
VALID_CONTACT = ["cellular", "telephone", "unknown"]
VALID_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
                "jul", "aug", "sep", "oct", "nov", "dec"]
VALID_POUTCOME = ["failure", "other", "success", "unknown"]


class PredictionInput(BaseModel):
    """Validated input for the /api/predict endpoint.

    CONCEPT (Pydantic validation):
    Pydantic rejects bad input BEFORE our route logic runs — out-of-range
    numbers (age=200) or unknown categories (job="wizard") return HTTP 422
    automatically. This is both a correctness AND a security guard: never
    let malformed data reach the ML model.
    """
    age: int = Field(ge=18, le=100)
    job: str
    marital: str
    education: str
    default: str
    balance: float
    housing: str
    loan: str
    contact: str
    day: int = Field(ge=1, le=31)
    month: str
    duration: int = Field(ge=0)
    campaign: int = Field(ge=1)
    pdays: int = Field(ge=-1)
    previous: int = Field(ge=0)
    poutcome: str
    model_name: str | None = Field(
        default=None,
        description="Optional: 'xgboost' (default) or 'logistic_regression'",
    )

    # Validate categorical fields against the known-good lists.
    # CONCEPT (model_validator):
    # This runs AUTOMATICALLY when Pydantic builds a PredictionInput from a
    # request body. If any category is invalid, it raises ValueError, and
    # FastAPI turns that into an HTTP 422 response — no route code needed.
    # Field(ge=.../le=...) above already handled numeric ranges.
    @model_validator(mode="after")
    def _check_categories(self):
        def _check(value: str, allowed: list[str], field: str) -> str:
            if value not in allowed:
                raise ValueError(
                    f"{field} must be one of {allowed}, got '{value}'"
                )
            return value

        _check(self.job, VALID_JOBS, "job")
        _check(self.marital, VALID_MARITAL, "marital")
        _check(self.education, VALID_EDUCATION, "education")
        _check(self.default, VALID_BINARY, "default")
        _check(self.housing, VALID_BINARY, "housing")
        _check(self.loan, VALID_BINARY, "loan")
        _check(self.contact, VALID_CONTACT, "contact")
        _check(self.month, VALID_MONTHS, "month")
        _check(self.poutcome, VALID_POUTCOME, "poutcome")
        return self


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

