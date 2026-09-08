# ============================================================
# backend/config.py
# Central settings loaded from .env via Pydantic Settings.
#
# WHY: Hardcoding URLs/secrets throughout the codebase is a
# maintenance nightmare and a security risk. One Settings object
# reads all config from environment variables (populated from .env)
# and exposes them as typed attributes everywhere.
# ============================================================

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Tell pydantic-settings to look for a .env file, treating
    # variable names as case-insensitive, and don't require it to exist.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore unknown env vars (don't fail startup)
    )

    # --- App ---
    app_name: str = "MediAssist AI"
    app_version: str = "0.1.0"

    # --- Infrastructure endpoints ---
    ollama_host: str = "http://localhost:11434"   # bare-metal Ollama (not dockerized)
    qdrant_url: str = "http://localhost:6333"     # standalone qdrant container
    phoenix_url: str = "http://localhost:6006"    # phoenix container

    # --- Models (all already downloaded in ~/.ollama) ---
    primary_model: str = "qwen3.5:4b"     # fast, supports tools + thinking
    fallback_model: str = "llama3.1:8b"   # slower, smarter fallback
    embedding_model: str = "nomic-embed-text"  # 768-dim embeddings

    # --- Vector DB ---
    qdrant_collection: str = "webpos_documents"

    # --- PostgreSQL (Data Tier, Phase 3.5) ---
    # SQLAlchemy uses this connection string to talk to Postgres.
    # Pattern for ANY project: postgresql://db_user:db_password@host:port/db_name
    database_url: str = "postgresql://medassist:medassist_dev@localhost:5432/medassist"

    # --- Security ---
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # --- LLMOps parameters ---
    # Reranking: how many candidates to fetch, then keep top K
    retrieval_candidates: int = 20
    rerank_top_k: int = 5

    # --- LLMOps Router (Phase 7, Step 3) ---
    # A/B routing: simple vs complex queries pick a different model.
    routing_complexity_threshold: float = 6.0  # route to smart model above this

    # Circuit breaker: count consecutive failures before "opening" the circuit.
    breaker_failure_threshold: int = 3    # failures before OPEN
    breaker_cooldown_seconds: float = 30.0  # wait before HALF-OPEN probe


# A single, app-wide settings instance. Import it anywhere:
#     from config import settings
settings = Settings()
