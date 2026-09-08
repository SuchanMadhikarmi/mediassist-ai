# ============================================================
# backend/llmops/cache.py
# FAISS semantic cache for chat answers.
#
# CONCEPT (semantic cache):
# LLM calls are SLOW (seconds) and COSTLY. Real users keep asking the
# same questions (just phrased differently). Instead of a normal
# cache (exact string match), we embed the question into a vector and
# search PAST questions for "similar meaning".
#
#   new question ──embed──> vector ──FAISS search──> near past question?
#       sim >= threshold?  YES ──> return cached answer (skip the LLM)
#                          NO  ──> run the graph, then STORE (q → a)
#
# This is "RAG in reverse": retrieval searched documents for meaning,
# here we search previously-asked questions for meaning.
#
# CONCEPT (cosine similarity via inner product):
# FAISS IndexFlatIP computes the inner product (dot product). For two
# UNIT vectors, dot product == cosine similarity (1.0 = aligned meaning,
# 0 = unrelated). So we NORMALIZE every embedding to length 1 before
# adding it — that tiny step turns plain IP into cosine similarity.
#
# Threshold 0.95 is deliberately STRICT: better to miss the cache and
# call the LLM than to serve a wrong cached answer to a similar-but-
# different question. In production you might tune this per domain.
#
# CONCEPT (bounded cache + eviction):
# An unlimited cache leaks memory. When full, we drop the OLDEST entry
# (FIFO) and rebuild the index. IndexFlatIP has no "remove" operation,
# so rebuild = recreate + re-add the survivors (cheap, we cap N ~ 100).
# A production upgrade would be LRU (evict least-RECENTLY-used).
#
# CONCEPT (pure data structure):
# This module knows NOTHING about FastAPI/HTTP. It stores plain data
# (question, answer, sources, vector) and returns plain data. That keeps
# it testable in isolation and reusable in any project (same design
# principle as agent/hitl.py).
# ============================================================

import threading
from dataclasses import dataclass, field

import faiss
import numpy as np

from ai_engine.embeddings import embed_text

# nomic-embed-text produces 768-dim vectors (matches our config).
EMBED_DIM = 768
DEFAULT_THRESHOLD = 0.95
DEFAULT_MAX_ENTRIES = 100


@dataclass
class CacheEntry:
    """One cached (question → answer) pair, plus its 768-dim vector.

    We store the VECTOR too so eviction can rebuild the FAISS index
    without re-embedding (re-embedding would need Ollama — slow).
    """
    question: str
    answer: str
    sources: list[dict]
    vector: np.ndarray


@dataclass
class SemanticCache:
    """A thread-safe, bounded, cosine-based cache of Q/A pairs."""

    threshold: float = DEFAULT_THRESHOLD
    max_entries: int = DEFAULT_MAX_ENTRIES
    index: faiss.IndexFlatIP = field(init=False)
    entries: list[CacheEntry] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        # IndexFlatIP = inner-product index. Combined with normalized
        # (unit-length) vectors, the score it returns IS cosine similarity.
        self.index = faiss.IndexFlatIP(EMBED_DIM)
        # Small knobs: FAISS may reserve more on .add(); keep memory tight.
        self.index.verbose = False

    # ── public API ────────────────────────────────────────────────
    async def lookup(self, question: str) -> tuple[CacheEntry | None, float]:
        """Embed the question and search past questions.

        Returns (entry, similarity). If similarity >= threshold → HIT
        (entry is not None). Otherwise MISS (entry is None) but we still
        return the raw similarity (useful for logging/near-miss tuning).
        """
        vector = _normalize(await embed_text(question))

        if self.index.ntotal == 0:
            return None, 0.0

        # FAISS wants a 2-D matrix (n_rows x dim); we have one query row.
        query2d = np.expand_dims(vector, axis=0)
        similarities, indices = self.index.search(query2d, k=1)
        similarity = float(similarities[0][0])
        position = int(indices[0][0])

        if similarity >= self.threshold:
            # Read-only metadata access still guarded for safety (another
            # request may be evicting/rebuilding the index concurrently).
            with self._lock:
                entry = self.entries[position]
            return entry, similarity

        return None, similarity

    async def store(self, question: str, answer: str, sources: list[dict]) -> None:
        """Cache a fresh (question → answer). Call ONLY after a real answer.

        Also refuses to cache an EMPTY answer — an empty string is never a
        real success (it would poison future lookups with a blank reply).
        """
        if not answer.strip():
            return
        vector = _normalize(await embed_text(question))
        entry = CacheEntry(question=question, answer=answer, sources=sources, vector=vector)

        with self._lock:
            if len(self.entries) >= self.max_entries:
                self._evict_oldest_and_add(entry)
            else:
                self.entries.append(entry)
                self.index.add(np.expand_dims(entry.vector, axis=0))

    def __len__(self) -> int:
        return len(self.entries)

    # ── internals ─────────────────────────────────────────────────
    def _evict_oldest_and_add(self, entry: CacheEntry) -> None:
        """Drop the OLDEST entry (entries[0]), then add the new one last.

        FIFO eviction. Rebuild the index from the survivors' stored
        vectors (no re-embedding needed) + the new vector.
        """
        survivors = self.entries[1:]
        self.entries = survivors + [entry]

        self.index.reset()
        if survivors:
            self.index.add(np.stack([e.vector for e in survivors]))
        self.index.add(np.expand_dims(entry.vector, axis=0))


# ── module-level singleton ─────────────────────────────────────────
# Safe at import time (unlike the Phase 6 graph checkpointer, which needs
# a running event loop): a FAISS index is just numbers in memory.
#
# NAMESPACING (RBAC leak prevention):
# Data-level RBAC means different user roles may legally see DIFFERENT
# documents. A cache is shared by default — if 'nurse' got an answer built
# from docs only 'admin' may see, that's a permission leak. So we key
# caches by a namespace string (we use the user's role). Each role gets
# its OWN cache instance. Same idea as Redis key prefixes (namespace:...).
_caches: dict[str, SemanticCache] = {}


def get_cache(namespace: str = "default") -> SemanticCache:
    """Return a shared cache for the given namespace (lazy per namespace).

    Usage: get_cache(user_role) — one cache per role, no cross-role leaks.
    """
    if namespace not in _caches:
        _caches[namespace] = SemanticCache()
    return _caches[namespace]


def _normalize(vector: list[float]) -> np.ndarray:
    """Turn a raw embedding into a UNIT-length float32 numpy vector.

    REQUIRED so that IndexFlatIP's inner product == cosine similarity.
    """
    arr = np.asarray(vector, dtype="float32")
    norm = float(np.linalg.norm(arr))
    if norm > 0:
        arr = arr / norm
    return arr


if __name__ == "__main__":
    # ── Self-test (needs Ollama up for nomic-embed-text) ──────────
    # Proves: exact-hit, paraphrase-hit, miss on unrelated, hit even
    # AFTER one eviction (rebuild path).
    import asyncio

    async def main() -> None:
        cache = SemanticCache(max_entries=2)  # tiny: forces eviction
        await cache.store("What does error 4012 mean?", "The 4012 error is...", [])
        await cache.store("How do I reset my password?", "Password reset steps...", [])

        # 1. Exact repeat → HIT
        entry, sim = await cache.lookup("What does error 4012 mean?")
        print(f"exact hit     : {'YES' if entry else 'no'}  sim={sim:.4f}")

        # 2. Paraphrase → sim is real data; whether it HITs depends on threshold.
        entry, sim = await cache.lookup("please explain error code 4012")
        para_sim = sim  # CAPTURE now — `sim` is reused by later lookups
        print(f"paraphrase    : {'HIT' if entry else 'MISS'}  sim={sim:.4f}")

        # 3. Unrelated → MISS (way below any sane threshold)
        entry, sim = await cache.lookup("What is the status of order ORD-1003?")
        print(f"unrelated miss: {'YES' if entry else 'no'}  sim={sim:.4f}")

        # 4. Fill cache to capacity → evicts oldest, then a HIT on the new one
        await cache.store("How do I add a new clinic user?", "Admin → Users → Add...", [])
        entry, sim = await cache.lookup("How do I add a new clinic user?")
        print(f"post-evict hit: {'YES' if entry else 'no'}  sim={sim:.4f}")
        print(f"cache size    : {len(cache)} (capped at 2)")

        # 5. TUNING DEMO — the same paraphrase at different thresholds.
        #    Shows WHY lookup() returns sim even on a miss: to tune with
        #    evidence. Tighter = safer but misses paraphrases; looser =
        #    catches them but risks pairing unrelated questions.
        print("\nthreshold tuning for the paraphrase above (sim="
              + f"{para_sim:.4f}):")
        for t in (0.95, 0.93, 0.90):
            verdict = "HIT" if para_sim >= t else "miss"
            print(f"  threshold {t:.2f} → {verdict}")

    asyncio.run(main())