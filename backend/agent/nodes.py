"""
agent/nodes.py
──────────────
Node functions for the LangGraph CRAG graph.

Each node reads from AgentState and returns a partial dict to merge back.
Nodes are pure functions — no side effects except the return value.

Graph flow:
    retrieve → grade_docs → [conditional] → generate → END
                                      ↘ reformulate → retrieve (loop)
"""

from __future__ import annotations

from ai_engine.retrieval import hybrid_search, load_corpus
from ai_engine.llm import generate_answer
from agent.state import AgentState


# ── Threshold for heuristic grading ──────────────────────────────
# From Phase 5 tests: relevant chunks scored ~+7, irrelevant scored ~-10.
# 0 is a clean, safe cutoff.
RELEVANCE_THRESHOLD = 0.0

# Maximum retries before giving up (prevents infinite loops).
MAX_RETRIES = 2


# ── Node 1: retrieve ────────────────────────────────────────────
async def retrieve(state: AgentState) -> dict:
    """Run hybrid search (dense + sparse + RRF + rerank) on the query.

    Reads:  query, rbac_label
    Writes: docs
    """
    # Make sure BM25 corpus is loaded (first call only).
    load_corpus()

    docs = await hybrid_search(
        query=state["query"],
        rbac_label=state["rbac_label"],
    )
    return {"docs": docs}


# ── Node 2: grade_docs ──────────────────────────────────────────
def grade_docs(state: AgentState) -> dict:
    """Check whether any retrieved doc is relevant (heuristic: rerank score).

    This node is a logical step in the graph — it does NOT modify state.
    The conditional edge that follows reads state['docs'] to decide routing.

    Reads:  docs (list of dicts with 'rerank_score')
    Writes: (nothing — conditional edge handles the decision)
    """
    docs = state.get("docs", [])
    if not docs:
        # No docs at all — nothing to grade.
        print("[grade_docs] No documents retrieved.")
    else:
        best = max(d.get("rerank_score", -999) for d in docs)
        above = sum(1 for d in docs if d.get("rerank_score", -999) > RELEVANCE_THRESHOLD)
        print(f"[grade_docs] {len(docs)} docs, {above} above threshold, best score: {best:.2f}")

    # Return empty dict — we don't mutate state here.
    # The conditional edge (decide_route) will read state["docs"] next.
    return {}


# ── Node 3: generate ────────────────────────────────────────────
async def generate(state: AgentState) -> dict:
    """Call Ollama to produce a cited answer from the retrieved context.

    Reads:  query, docs
    Writes: answer
    """
    # Extract the relevant fields the LLM needs (not the full Qdrant payload).
    llm_docs = []
    for doc in state["docs"]:
        llm_docs.append({
            "text": doc.get("text", ""),
            "source": doc.get("payload", {}).get("source", "unknown"),
            "page": doc.get("payload", {}).get("page", "?"),
        })

    answer = await generate_answer(query=state["query"], docs=llm_docs)
    return {"answer": answer}


# ── Node 4: reformulate ─────────────────────────────────────────
def reformulate(state: AgentState) -> dict:
    """Rewrite the query to improve retrieval on retry.

    This is a naive heuristic — just adds specificity cues.
    In production you'd use an LLM to reformulate, but for learning
    the graph structure, this is enough. A student can swap this later.

    Reads:  query, retries
    Writes: query, retries (incremented)
    """
    original = state["query"]
    new_query = f"{original} (detailed technical explanation)"
    new_retries = state["retries"] + 1

    print(f"[reformulate] Retry {new_retries}: '{original}' → '{new_query}'")
    return {"query": new_query, "retries": new_retries}


# ── Conditional edge function ────────────────────────────────────
def decide_route(state: AgentState) -> str:
    """Read state and decide which node to go to next.

    Returns:
        "generate"    — at least one doc is relevant, proceed to answer.
        "reformulate" — no relevant docs, rewrite query and retry.
        "__end__"     — retries exhausted, give up gracefully.
    """
    docs = state.get("docs", [])

    # Check if any doc passed the relevance threshold.
    has_relevant = any(
        d.get("rerank_score", -999) > RELEVANCE_THRESHOLD for d in docs
    )

    if has_relevant:
        return "generate"

    # No relevant docs — should we retry?
    retries = state.get("retries", 0)
    if retries < MAX_RETRIES:
        return "reformulate"

    # Retries exhausted — give up.
    return "__end__"
