# ============================================================
# backend/routes/health.py
# A health-check endpoint. Proves the server is alive AND that
# all its backing services (Qdrant, Ollama) are reachable.
#
# In production, load balancers / orchestrators poll this to decide
# whether to send traffic or kill+restart the container.
# ============================================================

import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from config import settings
from database import engine

router = APIRouter()


@router.get("/health")
async def health():
    """Return service health. 200 if everything's reachable, 503 otherwise."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "services": {
            "qdrant": await _check("qdrant", settings.qdrant_url + "/healthz"),
            "ollama": await _check("ollama", settings.ollama_host + "/api/tags"),
            "phoenix": await _check("phoenix", settings.phoenix_url + "/health"),
            "postgres": _check_db(),
        },
    }


def _check_db() -> dict:
    """Return whether PostgreSQL is reachable by running `SELECT 1`."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"up": True, "url": settings.database_url.split("@")[-1]}
    except Exception:
        return {"up": False, "url": settings.database_url.split("@")[-1]}


async def _check(name: str, url: str) -> dict:
    """Ping a URL with a short timeout; report up/down without crashing."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(url)
            ok = r.status_code < 500
    except Exception:
        ok = False
    return {"up": ok, "url": url}
