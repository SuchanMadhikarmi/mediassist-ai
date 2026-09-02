# ============================================================
# backend/models/__init__.py
# Exports all ORM models so that:
#   1. Alembic autogenerate can discover every table (they must all be
#      imported here before Alembic introspects Base.metadata)
#   2. Other modules can do `from models import User, Document, ...`
# ============================================================

from models.audit_log import AuditLog
from models.document import Document
from models.model_registry import ModelRegistry
from models.prediction import Prediction
from models.user import User

__all__ = [
    "User",
    "Document",
    "Prediction",
    "AuditLog",
    "ModelRegistry",
]
