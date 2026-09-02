# ============================================================
# backend/ai_engine/retrieval.py
# RETRIEVAL: find the most relevant document chunks for a query.
#
# This is Phase 5's core. It answers: "I have a user question,
# which stored chunks should I give the LLM to answer from?"
#
# The retrieval FUNNEL (cheap & fast first, accurate last):
#   1. DENSE search  -> Qdrant vector search (semantic meaning)
#   2. SPARSE search -> BM25 (exact keyword match)
#   3. RRF fusion    -> merge the two ranked lists (rank-based)
#   4. RE-RANK       -> Cross-Encoder scores top candidates
#
# Why hybrid (dense + sparse)? They cover each other's gaps:
#   - Dense finds MEANING (synonyms, paraphrases) but can miss
#     exact tokens like "4012".
#   - Sparse finds EXACT keywords but can't understand meaning.
#   Together + RRF = best of both.
# ============================================================

from rank_bm25 import BM25Okapi

from ai_engine.embeddings import embed_text
from ai_engine.reranker import rerank_cross_encoder
from config import settings
from security.pii_redactor import redact_pii


# Module-level BM25 index: we build it once and reuse it across queries.
# It's built from every chunk currently stored in Qdrant.
_bm25: BM25Okapi | None = None
_corpus_texts: list[str] = []          # parallel to Qdrant points order
_corpus_ids: list[str] = []            # parallel to _corpus_texts
_corpus_payloads: list[dict] = []      # the metadata for each chunk


def _get_client():
    from qdrant_client import QdrantClient
    return QdrantClient(url=settings.qdrant_url)


def load_corpus(force: bool = False) -> None:
    """Fetch ALL chunks from Qdrant and build the BM25 index on their text.

    WHY fetch everything into memory? BM25 needs the full corpus to compute
    IDF (how rare each word is). Qdrant doesn't provide BM25, so we build it
    here. For our scale this is fine; production would use Qdrant's sparse
    vectors instead.
    """
    global _bm25, _corpus_texts, _corpus_ids, _corpus_payloads
    if _bm25 is not None and not force:
        return  # already loaded; don't rebuild every query

    client = _get_client()
    points, next_offset = client.scroll(
        collection_name=settings.qdrant_collection,
        limit=1000,
        with_payload=True,
        with_vectors=False,
    )
    corpus_texts, corpus_ids, corpus_payloads = [], [], []
    for p in points:
        text = (p.payload or {}).get("text", "")
        if text.strip():
            corpus_texts.append(text)
            corpus_ids.append(p.id)
            corpus_payloads.append(p.payload or {})
    # BM25 tokenizes on whitespace + punctuation
    tokenized = [text.lower().split() for text in corpus_texts]
    _bm25 = BM25Okapi(tokenized)
    _corpus_texts = corpus_texts
    _corpus_ids = corpus_ids
    _corpus_payloads = corpus_payloads


def _rbac_filter(rbac_label: str) -> dict:
    """Return a Qdrant filter that restricts results to the caller's role.

    admin sees everything; everyone else only sees chunks tagged with their
    own exact role label. This is where the keyword index from Phase 4 pays
    off (fast filtering, no full scan).
    """
    if rbac_label == "admin":
        return {}  # admins bypass filtering (see all)
    # Filter: rbac_label == <this exact role>
    return {
        "must": [
            {"key": "rbac_label", "match": {"value": rbac_label}}
        ]
    }


async def dense_search(query: str, rbac_label: str, top_k: int = 20) -> list[dict]:
    """Semantic search via Qdrant vector similarity.

    Embeds the query, then asks Qdrant for the nearest vectors, filtered
    by RBAC. Returns: [{"id":..., "text":..., "payload":...}, ...]
    """
    client = _get_client()
    vector = await embed_text(query)          # 768-dim query vector
    qfilter = _rbac_filter(rbac_label)
    result = client.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        query_filter=qfilter,
        limit=top_k,
        with_payload=True,
    )
    hits = []
    for h in result.points:
        hits.append(
            {
                "id": str(h.id),
                "text": (h.payload or {}).get("text", ""),
                "payload": h.payload or {},
                "dense_rank": len(hits) + 1,
            }
        )
    return hits


def sparse_search(query: str, rbac_label: str, top_k: int = 20) -> list[dict]:
    """Keyword search via BM25 over the corpus we loaded.

    Returns the top_k chunks by BM25 score, filtered by RBAC.
    """
    load_corpus()  # ensure index exists
    tokenized_query = query.lower().split()
    scores = _bm25.get_scores(tokenized_query)  # one score per corpus doc
    # Pair each doc's index with its score, keep those matching RBAC
    ranked = []
    for i, score in enumerate(scores):
        payload = _corpus_payloads[i]
        label = payload.get("rbac_label")
        if rbac_label != "admin" and label != rbac_label:
            continue  # skip chunks the user shouldn't see
        if score > 0:
            ranked.append((i, score))
    ranked.sort(key=lambda x: x[1], reverse=True)  # best score first
    ranked = ranked[:top_k]

    hits = []
    for i, score in ranked:
        hits.append(
            {
                "id": _corpus_ids[i],
                "text": _corpus_texts[i],
                "payload": _corpus_payloads[i],
                "bm25_score": score,
                "sparse_rank": len(hits) + 1,
            }
        )
    return hits


def rrf_fusion(
    dense: list[dict], sparse: list[dict], k: int = 60
) -> list[dict]:
    """Fuse two ranked lists using Reciprocal Rank Fusion.

    RRF_score(d) = sum over lists of 1/(k + rank(d) in that list).
    - Uses RANK (position), not raw score, so it's scale-independent.
    - A doc ranked highly in BOTH lists scores higher than one ranked
      #1 in only one list.
    """
    scores: dict[str, float] = {}
    by_id: dict[str, dict] = {}

    for i, hit in enumerate(dense):
        rank = i + 1  # 1-based
        scores[hit["id"]] = scores.get(hit["id"], 0) + 1.0 / (k + rank)
        by_id[hit["id"]] = hit

    for i, hit in enumerate(sparse):
        rank = i + 1
        scores[hit["id"]] = scores.get(hit["id"], 0) + 1.0 / (k + rank)
        if hit["id"] not in by_id:
            by_id[hit["id"]] = hit

    # Sort all seen ids by descending RRF score
    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    result = []
    for hit_id, score in fused:
        hit = dict(by_id[hit_id])
        hit["rrf_score"] = score
        result.append(hit)
    return result


async def hybrid_search(
    query: str, rbac_label: str, candidates: int = None, top_k: int = None
) -> list[dict]:
    """Full retrieval funnel: dense + sparse -> RRF -> re-rank -> top_k.

    Returns the final list of documents (with their payloads) ready to be
    handed to the LLM in Phase 6.
    """
    candidates = candidates or settings.retrieval_candidates  # default 20
    top_k = top_k or settings.rerank_top_k                     # default 5

    # Redact PII from the query BEFORE it's used for search, so PII never
    # gets logged or lands in trace context (compliance tie-in).
    clean_query = redact_pii(query)

    # 1 & 2: get candidates from both search types
    dense = await dense_search(clean_query, rbac_label, top_k=candidates)
    sparse = sparse_search(clean_query, rbac_label, top_k=candidates)

    # 3: fuse
    fused = rrf_fusion(dense, sparse, k=60)

    # 4: re-rank the fused top candidates with the cross-encoder
    top_candidates = fused[:candidates]
    reranked = rerank_cross_encoder(clean_query, top_candidates, top_k=top_k)

    return reranked
