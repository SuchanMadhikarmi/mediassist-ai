# ============================================================
# backend/ai_engine/embeddings.py
# Text <-> vector conversion using Ollama's nomic-embed-text.
#
# Our earlier plan used sentence-transformers locally, but we REVISED:
# Ollama already has nomic-embed-text downloaded, and serving embeddings
# through it keeps RAM low (no need to load a second model into Python).
#
# nomic-embed-text produces a 768-dimensional vector that captures the
# SEMANTIC MEANING of text: similar meanings -> nearby vectors.
# ============================================================

import httpx

from config import settings


async def embed_text(text: str) -> list[float]:
    """Embed a single string into a 768-dim vector via Ollama.

    WHY async: Ollama may take ~50ms+ per call. Async lets the server
    handle other requests while waiting, instead of blocking.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ollama_host}/api/embeddings",
            json={"model": settings.embedding_model, "prompt": text},
        )
        resp.raise_for_status()
        data = resp.json()
    return data["embedding"]


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings. Reuses one HTTP client for efficiency.

    NOTE: Ollama's HTTP /api/embeddings takes ONE prompt at a time, so we
    simply map over them. For large PDFs (hundreds of chunks) this is fine;
    a production system would use a pooling/batching client or GPU server.
    """
    results: list[list[float]] = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for text in texts:
            resp = await client.post(
                f"{settings.ollama_host}/api/embeddings",
                json={"model": settings.embedding_model, "prompt": text},
            )
            resp.raise_for_status()
            results.append(resp.json()["embedding"])
    return results
