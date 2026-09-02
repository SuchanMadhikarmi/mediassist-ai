# ============================================================
# backend/ai_engine/reranker.py
# Cross-Encoder re-ranking: scores (query, doc) PAIRS directly.
#
# Why re-rank after RRF?
#   RRF merges search lists but ranks by search-position, not by
#   true relevance to THIS query. A cross-encoder reads the actual
#   query + document together and outputs a relevance score, giving
#   much better final ordering.
#
# Why only on top candidates (not whole corpus)?
#   A cross-encoder runs a full neural forward pass per pair, so it
#   is O(n) and slow. We only score the ~20 candidates from RRF
#   (not all 100k chunks), keeping it fast AND accurate. This is the
#   classic "retrieval funnel": cheap-and-fast first, accurate-last.
#
# MEMORY NOTE: the model is loaded ONCE as a module-level singleton,
# so every request shares it (no reloading per query -> saves RAM).
# ============================================================

from sentence_transformers import CrossEncoder

MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Lazy singleton: loaded on first use, reused forever after.
_reranker: CrossEncoder | None = None


def _get_reranker() -> CrossEncoder:
    """Return the shared cross-encoder, loading it if not already loaded."""
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(MODEL_NAME)
    return _reranker


def rerank_cross_encoder(
    query: str, documents: list[dict], top_k: int = 5
) -> list[dict]:
    """Score each (query, document) pair and return the top_k by relevance.

    `documents` is the fused list from RRF, each with at least "text".
    Mutates a copy (doesn't touch input) and returns the re-ordered list.
    """
    if not documents:
        return []

    model = _get_reranker()

    # Build (query, doc_text) pairs for the model.
    pairs = [(query, d["text"]) for d in documents]
    scores = model.predict(pairs)  # one relevance score per pair

    # Attach score to each doc.
    scored = []
    for d, s in zip(documents, scores):
        d = dict(d)  # copy so we don't mutate caller's list
        d["rerank_score"] = float(s)
        scored.append(d)

    # Sort descending by relevance, keep top_k.
    scored.sort(key=lambda x: x["rerank_score"], reverse=True)
    return scored[:top_k]
