# ============================================================
# backend/schemas/__init__.py
# Pydantic schemas = the API contract (request/response shapes).
#
# These sit between the JSON the client sends and the ORM Model.
# WHY separate schemas from models:
#   - Security: never return password_hash / internal fields to clients
#   - Flexibility: response shape can differ from DB shape
#   - Validation: enforce rules (email format, password length...) at the edge
# ============================================================

from schemas.audit import AuditResponse
from schemas.document import DocumentResponse
from schemas.prediction import PredictionCreate, PredictionResponse, PredictionReview
from schemas.user import UserCreate, UserResponse, UserUpdate

__all__ = [
    "UserCreate",
    "UserResponse",
    "UserUpdate",
    "DocumentResponse",
    "PredictionCreate",
    "PredictionResponse",
    "PredictionReview",
    "AuditResponse",
]
