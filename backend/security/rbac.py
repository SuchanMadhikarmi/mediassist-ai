# ============================================================
# backend/security/rbac.py
# Role-Based Access Control: depend on a specific role to gate an endpoint.
#
# We reuse FastAPI dependency injection. get_current_user already
# validated the JWT and returned {"user_id", "role"}. This module
# adds an authorization layer on top: "is this user ALLOWED to
# do this action?"
#
#   - Who you are      -> Authentication (JWT)   [security/auth.py]
#   - What you may do  -> Authorization   (RBAC) [this file]
#
# Usage:
#   from security.rbac import require_role
#   from security.models import Role
#
#   @app.post("/ingest")
#   def ingest(user: dict = Depends(require_role(Role.ADMIN))):
#       ...
# ============================================================

from typing import Callable

from fastapi import Depends, HTTPException, status

from security.auth import get_current_user
from security.models import Role


def require_role(required_role: "Role") -> Callable:
    """Return a FastAPI dependency that enforces a role.

    Returns a function FastAPI calls with the authenticated user.
    If the user's role doesn't match, raise 403 Forbidden.
    """
    def _checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") != required_role.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role.value}' required for this action",
            )
        return user

    return _checker
