"""
ai_engine/llm.py
─────────────────
Thin async wrapper around Ollama's HTTP API for non-streaming generation.

Used by the generate node in the LangGraph CRAG graph.
Streaming (SSE) is added in Phase 7.
"""

import httpx
from config import settings


# Ollama's /api/chat endpoint — returns the full response in one go.
OLLAMA_URL = f"{settings.ollama_host}/api/chat"

# Some Ollama models (incl. qwen3.5:4b) have a "thinking" mode: their actual
# text occasionally lands in `thinking` with `content` empty/truncated,
# especially for short answer prompts. Retry up to this many times to get a
# non-empty `content`.
GENERATION_RETRIES = 3


async def _call_ollama(messages: list[dict]) -> str:
    """POST to Ollama and return the assistant's content, retrying if empty.

    Keeps the retry logic in ONE place (the LLM wrapper) so the caller never
    has to deal with a flaky empty response.

    NOTE: This retries GENERATION (a bad/empty model reply). It is totally
    separate from the graph's retrieval-retry loop in reformulate().
    """
    payload = {
        "model": settings.primary_model,
        "messages": messages,
        "stream": False,       # non-streaming — full response at once
        "options": {
            "temperature": 0.3,  # low temp = less hallucination
            "num_predict": 512,  # cap answer length
        },
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(1, GENERATION_RETRIES + 1):
            response = await client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            content = data["message"]["content"].strip()

            # Accept the reply only if it's long enough to be a real answer.
            if content:
                return content

            # If empty/truncated, retry. Log so we can observe flakiness.
            print(f"[llm] empty content on attempt {attempt}, retrying...")

    return ""  # all retries failed — caller decides how to handle


async def generate_answer(query: str, docs: list[dict]) -> str:
    """Call Ollama (qwen3.5:4b) to generate an answer from retrieved context.

    Args:
        query: The user's question (possibly rewritten by reformulate node).
        docs:  List of retrieved chunks, each with 'text', 'source', 'page'.

    Returns:
        The LLM's answer as a plain string ("" if all retries failed).
    """
    # ── Build the context block from retrieved docs ──────────────
    # Number each chunk so the LLM can reference them by number
    # (this enables citations in the final answer).
    context_parts: list[str] = []
    for i, doc in enumerate(docs, start=1):
        source = doc.get("source", "unknown")
        page = doc.get("page", "?")
        text = doc.get("text", "")
        context_parts.append(f"[{i}] (source: {source}, page {page})\n{text}")

    context_block = "\n\n".join(context_parts) if context_parts else "No relevant documents found."

    # ── Construct the messages ───────────────────────────────────
    system_msg = (
        "You are MediAssist AI, a clinical support assistant for a WebPOS/ERP company. "
        "Answer the user's question using ONLY the provided context. "
        "If the context does not contain enough information to answer, say so clearly. "
        "Cite your sources using the [1], [2], etc. notation from the context block. "
        "Be concise and accurate. Do not make up information."
    )

    user_msg = (
        f"Context from company documents:\n\n{context_block}\n\n"
        f"Question: {query}\n\n"
        "Answer:"
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    return await _call_ollama(messages)
