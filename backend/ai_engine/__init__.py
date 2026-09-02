# ============================================================
# backend/ai_engine/__init__.py
# The AI Engine package. Holds the "intelligence" layers:
#   - embeddings  : text <-> vector (via Ollama nomic-embed-text)
#   - ingestion   : PDF -> chunks -> vectors -> Qdrant  (Phase 4)
#   - retrieval   : hybrid search (dense+sparse+RRF) + rerank  (Phase 5)
#   - reranker    : cross-encoder re-ranking (Phase 5)
# ============================================================
