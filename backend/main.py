# ============================================================
# backend/main.py
# FastAPI application entrypoint. This is the file uvicorn runs.
#
# Structure:
#   - create the FastAPI() app
#   - configure CORS (which origins may call us from a browser)
#   - mount route routers
#   - (later) startup hooks to init Qdrant/Ollama/telemetry
#
# WHY CORS: the React frontend runs in a browser on a DIFFERENT
# origin (localhost:5173) than the API (localhost:8000). Browsers
# enforce same-origin policy, so we must explicitly allow the
# frontend's origin to make requests to us.
# ============================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from llmops.telemetry import configure_telemetry
from routes.audit import router as audit_router
from routes.auth import router as auth_router
from routes.chat import router as chat_router
from routes.demo import router as demo_router  # TEMP: Phase 3 proof, delete later
from routes.documents import router as documents_router
from routes.health import router as health_router
from routes.ingest import router as ingest_router
from routes.predict import router as predict_router
from routes.predictions import router as predictions_router
from routes.stats import router as stats_router
from routes.users import router as users_router

# Create the app. title/version show up in the auto-generated /docs UI.
app = FastAPI(title=settings.app_name, version=settings.app_version)

# Start OpenTelemetry tracing → Phoenix (must run AFTER app creation because
# FastAPIInstrumentor needs the app object to hook into; idempotent).
configure_telemetry(app)

# CORS: allow the Vite dev server (and later the production origin) to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server (frontend)
        "http://127.0.0.1:5173",
        "http://localhost:5174",  # in case Vite picks a different port
    ],
    allow_credentials=True,
    allow_methods=["*"],   # allow all HTTP methods (GET, POST, ...)
    allow_headers=["*"],   # allow all headers (incl. Authorization for JWT)
)

# Mount the route modules' routers. Each router groups related endpoints.
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(ingest_router)
app.include_router(chat_router)
app.include_router(users_router)
app.include_router(documents_router)
app.include_router(predict_router)
app.include_router(predictions_router)
app.include_router(stats_router)
app.include_router(audit_router)
app.include_router(demo_router)  # TEMP: Phase 3 proof, delete later
