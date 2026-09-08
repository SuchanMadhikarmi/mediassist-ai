"""
ai_engine/llm.py
─────────────────
Thin async wrapper around Ollama's HTTP API for non-streaming generation.

Used by the generate node in the LangGraph CRAG graph.
Streaming (SSE) is added in Phase 7.
"""

import httpx
from config import settings
from llmops.router import get_router


# Ollama's /api/chat endpoint — returns the full response in one go.
OLLAMA_URL = f"{settings.ollama_host}/api/chat"

# Some Ollama models (incl. qwen3.5:4b) have a "thinking" mode: their actual
# text occasionally lands in `thinking` with `content` empty/truncated,
# especially for short answer prompts. Retry up to this many times to get a
# non-empty `content`.
GENERATION_RETRIES = 3


async def _call_ollama(messages: list[dict], model: str | None = None) -> str:
    """POST to Ollama and return the assistant's content, retrying if empty.

    Args:
        messages: The [system, user] message list to send.
        model:    Override the model name. Defaults to the router's A/B pick
                  based on rutting (callers pass the already-picked model).

    Keeps the retry logic in ONE place (the LLM wrapper) so the caller never
    has to deal with a flaky empty response.

    CIRCUIT BREAKER (Phase 7, Step 3):
    The router owns a per-model CircuitBreaker. Before ANY attempt we check
    `breaker.allow_call`; if the model is tripped we fail FAST (no HTTP call
    at all) instead of waiting for the 60s timeout. After the attempt we feed
    success/failure back so the breaker can track health. This is what turns a
    dead Ollama into a <50ms graceful refusal instead of a multi-second hang.

    NOTE (live-test bug caught in Phase 7):
    qwen3.5:4b has a "thinking" mode where its ENTIRE reply lands in
    `message.thinking` and `content` stays EMPTY. It even ignores
    `"think": false` inside `options`. The working switch is `"think": False`
    at the TOP LEVEL of the request body. We disable it: our judges only need
    yes/no and the answer must be concise grounded text — thinking tokens are
    pure waste here (slower + costlier). The retry loop below is ALSO the
    defensive net for any model/prompt where thinking still sneaks in.

    NOTE: This retries GENERATION (a bad/empty model reply). It is totally
    separate from the graph's retrieval-retry loop in reformulate().
    """
    router = get_router()

    # A/B pick if the caller didn't force a model (e.g. a streaming helper).
    if model is None:
        # The callers pass the chosen model explicitly. If none, infer from
        # the last message (the user question) — pragmatic default for judges.
        query = messages[-1]["content"] if messages else ""
        model = router.pick_model(query)

    breaker = router._breaker(model)

    # ── CIRCUIT GATE: refuse fast if this model is tripped ─────────
    if not breaker.allow_call:
        print(f"[llm] {model} circuit OPEN — failing fast (no HTTP call).")
        return ""  # caller (generate_answer) will treat as no answer

    payload = {
        "model": model,          # routed, not hardcoded
        "messages": messages,
        "stream": False,         # non-streaming — full response at once
        "think": False,          # TOP-LEVEL (see note above) — skip thinking tokens
        "options": {
            "temperature": 0.3,  # low temp = less hallucination
            "num_predict": 512,  # cap answer length
        },
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(1, GENERATION_RETRIES + 1):
            try:
                response = await client.post(OLLAMA_URL, json=payload)
                response.raise_for_status()
            except Exception as exc:
                # Network / non-2xx failure → report to the breaker and retry.
                print(f"[llm] {model} attempt {attempt} failed: {exc!r}")
                if attempt == GENERATION_RETRIES:
                    router.on_failure(model)
                    return ""
                continue

            data = response.json()
            content = data["message"].get("content", "").strip()

            if not content:
                # Defensive fallback: some models still answer via thinking.
                # Use the thinking text rather than returning an empty answer.
                content = (data["message"].get("thinking") or "").strip()

            # Accept the reply only if it's long enough to be a real answer.
            if content:
                router.on_success(model)   # healthy reply → heal breaker
                return content

            # If empty/truncated, retry. Log so we can observe flakiness.
            print(f"[llm] empty content on attempt {attempt}, retrying...")

    # All retries exhausted → the model is being flaky → trip/open the breaker.
    router.on_failure(model)
    return ""  # all retries failed — caller decides how to handle


def build_generation_messages(
    query: str, docs: list[dict], tool_result: dict | None = None
) -> list[dict]:
    """Build the exact messages the generator LLM sees (PURE function).

    CONCEPT (single source of truth):
    Both the BLOCKING path (/chat → generate node → _call_ollama) and the
    STREAMING path (/chat/stream → llmops.streaming) must feed Ollama the
    EXACT same prompt — otherwise a cached/streamed answer could diverge
    from a non-streaming one. Extracting this pure builder guarantees:
    "one prompt, written once, reused everywhere".

    Returns: the [system, user] message list for /api/chat.
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

    # ── If a tool returned LIVE data, add it as an authoritative block ──
    # Tool data is FRESH and ground-truth (unlike possibly-stale docs).
    # We present it separately and mark it as live/system data so the LLM
    # trusts it as current fact (this is the "tool calling" payoff).
    if tool_result:
        context_parts.append(
            f"[LIVE] (source: ERP system — current data)\n{tool_result}"
        )

    context_block = "\n\n".join(context_parts) if context_parts else "No relevant documents found."

    # ── Construct the messages ───────────────────────────────────
    system_msg = (
        "You are MediAssist AI, a clinical support assistant for a WebPOS/ERP company. "
        "Answer the user's question using ONLY the provided context. "
        "If the context does not contain enough information to answer, say so clearly. "
        "Cite your sources using the [1], [2], etc. notation from the context block. "
        "When answering about LIVE data marked [LIVE], treat it as current and accurate. "
        "Be concise and accurate. Do not make up information."
    )

    user_msg = (
        f"Context from company documents and live data:\n\n{context_block}\n\n"
        f"Question: {query}\n\n"
        "Answer:"
    )

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


async def generate_answer(query: str, docs: list[dict], tool_result: dict | None = None) -> str:
    """Call Ollama to generate an answer from retrieved context.

    Args:
        query: The user's question (possibly rewritten by reformulate node).
        docs:  List of retrieved chunks, each with 'text', 'source', 'page'.
        tool_result: Optional live data returned by a tool (e.g. ERP order).
                     If present, it is added to the context so the answer
                     can reference REAL current data, not just static docs.

    Returns:
        The LLM's answer as a plain string ("" if all retries failed).

    A/B ROUTING (Phase 7, Step 3):
    Complex questions get routed to the smart model (llama), simple ones
    to the fast model (qwen). The choice is a PURE policy — we only need to
    ask once per generation because the whole answer is a single call.
    """
    # Delegate message construction to the shared pure builder so the
    # BLOCKING and STREAMING paths always prompt Ollama identically.
    messages = build_generation_messages(query, docs, tool_result)

    model = get_router().pick_model(query)
    return await _call_ollama(messages, model=model)


async def grade_sufficiency(query: str, docs: list[dict]) -> str:
    """LLM-as-a-judge: are the retrieved docs ENOUGH to answer the question?

    CONCEPT (Sufficiency grading):
    Relevance asks "are these docs ON TOPIC?" — sufficiency asks "have we got
    EVERYTHING needed to fully answer?" Crucially, we prompt the LLM to detect
    when the answer needs LIVE/current data that documents can't possibly
    contain (e.g. "what's the status of order ORD-1003 right now?"). That's
    the trigger for calling the ERP tool.

    Returns: "yes" (docs suffice) or "no" (need tool / more info).
    """
    context_parts = []
    for i, doc in enumerate(docs, start=1):
        text = doc.get("text", "")
        context_parts.append(f"[{i}] {text}")
    context_block = "\n\n".join(context_parts) if context_parts else "No documents."

    system_msg = (
        "You are a search-quality judge. Decide whether the provided "
        "documents contain ENOUGH information to fully answer the question. "
        "Answer with exactly one word. "
        "Reply 'no' if the question needs LIVE/current data (like a current "
        "order status, live stock, or recent activity) that static documents "
        "cannot contain, of if the documents are too sparse. "
        "Otherwise reply 'yes'."
    )
    user_msg = (
        f"Documents:\n{context_block}\n\n"
        f"Question: {query}\n\n"
        f"Are these documents sufficient? Reply 'yes' or 'no':"
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    verdict = await _call_ollama(messages)
    verdict = verdict.strip().lower()
    return "no" if verdict.startswith("no") else "yes"


async def grade_faithfulness(query: str, docs: list[dict], answer: str, tool_result: dict | None = None) -> str:
    """LLM-as-a-judge: is the generated answer GROUNDED in the context?

    CONCEPT (Faithfulness grading):
    Faithfulness asks: "Did the answer stick to the source material, or did
    the LLM invent/hallucinate facts that are NOT in the docs or tool data?"
    We give the judge BOTH the context AND the answer, and it checks whether
    every claim in the answer is supported.

    This closes the "Corrective" loop in CRAG:
      - retrieve read the wrong docs  → reformulate (correct retrieval)
      - generate hallucinated         → regenerate    (correct generation)

    Returns: "yes" (faithful) or "no" (hallucinated / not grounded).
    """
    # Rebuild the same context block the generator saw, so the judge compares
    # against exactly what the model had available (fairgrounds the check).
    context_parts = []
    for i, doc in enumerate(docs, start=1):
        text = doc.get("text", "")
        context_parts.append(f"[{i}] {text}")
    if tool_result:
        context_parts.append(f"[LIVE] (ERP data)\n{tool_result}")
    context_block = "\n\n".join(context_parts) if context_parts else "No documents."

    system_msg = (
        "You are a fact-checking judge. A model generated an answer using "
        "only the provided context. Your job: decide whether EVERY factual "
        "claim / number / status in the answer is DIRECTLY supported by the "
        "context. If the answer adds details not present in the context, it "
        "is NOT faithful. "
        "Answer with exactly one word: 'yes' (faithful) or 'no' (not faithful)."
    )
    user_msg = (
        f"Context:\n{context_block}\n\n"
        f"Question: {query}\n\n"
        f"Model Answer:\n{answer}\n\n"
        f"Is the answer faithful to the context? Reply 'yes' or 'no':"
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    verdict = await _call_ollama(messages)
    verdict = verdict.strip().lower()
    return "no" if verdict.startswith("no") else "yes"
