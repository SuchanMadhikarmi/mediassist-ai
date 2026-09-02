# ============================================================
# backend/routes/chat.py
# POST /chat — answer a user's question using RAG + CRAG agent.
#
# Phase 6 version: runs the LangGraph CRAG graph, which now produces
# a real LLM-generated answer (not just retrieved chunks).
# Streaming (SSE) is added in Phase 7.
#
# Flow:
#   1. Authenticate + enforce RBAC
#   2. Run the CRAG graph:
#        retrieve → grade → (generate | reformulate→retry)
#   3. Return the LLM answer + the sources it used for citations.
# ============================================================

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from security.auth import get_current_user
from security.pii_redactor import redact_pii
from agent.graph import crag_graph

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]  # citations the LLM can reference


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: dict = Depends(get_current_user),
):
    """Answer a question through the CRAG graph."""
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # ── Run the CRAG graph ──────────────────────────────────────
    # Initial state: the user's query, their role (for RBAC filtering
    # in the retriever), zero retries, empty docs/answer placeholders.
    initial_state = {
        "query": body.message,
        "rbac_label": user["role"],  # used by retrieve() for data-level RBAC
        "docs": [],
        "answer": "",
        "retries": 0,
    }

    result = await crag_graph.ainvoke(initial_state)

    # ── Build the response ──────────────────────────────────────
    answer = result.get("answer", "").strip()

    if not answer:
        # No answer → the graph exhausted its retries without finding
        # relevant docs. Give a graceful "I couldn't find it" response.
        return ChatResponse(
            answer=(
                "I could not find relevant information about that in the "
                "available documents. Please try rephrasing your question "
                "or check that the relevant manual has been uploaded."
            ),
            sources=[],
        )

    # Gather the sources that informed the answer (for citations).
    sources = []
    for doc in result["docs"]:
        payload = doc.get("payload", {})
        if doc.get("rerank_score", -999) > 0:
            text = redact_pii(doc.get("text", ""))
            sources.append({
                "text": text,
                "source": payload.get("source"),
                "page": payload.get("page"),
                "rerank_score": doc.get("rerank_score"),
            })

    return ChatResponse(answer=answer, sources=sources)
