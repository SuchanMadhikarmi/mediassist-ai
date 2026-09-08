"""
llmops/streaming.py
───────────────────
Phase 7, Step 2 — Server-Sent Events (SSE) streaming for the chat answer.

Layered exactly like the two protocols involved:

  1. OLLAMA layer  → Ollama /api/chat with "stream": true returns
                     NDJSON (one JSON object per line). We iterate the
                     response as an async generator of individual
                     content tokens.

  2. SINK layer    → The "token-sink" pattern. The graph's `generate`
                     node streams tokens into an asyncio.Queue placed in
                     the graph CONFIG. The HTTP route simultaneously
                     pumps that queue into the response. Producer and
                     consumer run concurrently on the same event loop,
                     never blocking each other.

  3. SSE layer     → sse_frame() wraps a payload as a properly framed
                     server-sent event (data: <json>\\n\\n). This is what
                     a browser EventSource frontend parses.
"""

import asyncio
import json

import httpx
from config import settings

from ai_engine.llm import build_generation_messages
from llmops.router import get_router

OLLAMA_URL = f"{settings.ollama_host}/api/chat"


async def _ollama_token_stream(messages: list[dict], model: str | None = None):
    """POST to Ollama in stream mode and YIELD each assistant content token.

    CONCEPT (NDJSON streaming):
    With "stream": true, httpx keeps the response body open and hands us
    newline-delimited lines. Each line is a JSON object:
        {"message": {"role": "assistant", "content": "The"}, "done": false}
    ...until a final object with "done": true.
    We re-emit "think": false at the TOP LEVEL exactly like the blocking
    _call_ollama (same qwen3.5 thinking-mode workaround — shared rationale).

    ROUTING (Phase 7, Step 3):
    The router picks the model per-query (A/B), same as the blocking path.
    On success we report to the breaker; if the stream fails mid-way we
    report a failure so the breaker can open if this is a pattern.
    """
    router = get_router()

    # Infer the model if the caller didn't force one (same default rule as
    # the blocking path). Normally stream_answer_into_sink passes it in.
    if model is None:
        query = messages[-1]["content"] if messages else ""
        model = router.pick_model(query)

    breaker = router._breaker(model)

    # ── CIRCUIT GATE: refuse fast if this model is tripped ─────────
    if not breaker.allow_call:
        print(f"[stream] {model} circuit OPEN — failing fast.")
        return

    payload = {
        "model": model,          # routed, not hardcoded
        "messages": messages,
        "stream": True,
        "think": False,          # top-level: skip qwen thinking tokens
        "options": {
            "temperature": 0.3,  # match the blocking path's settings
            "num_predict": 512,
        },
    }

    # No stream should ever time out mid-answer: use read=60s per chunk.
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", OLLAMA_URL, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("done"):
                        router.on_success(model)
                        return
                    # qwen-paranoia: accept content from either field.
                    content = data.get("message", {}).get("content") or ""
                    if content:
                        yield content
    except Exception as exc:
        print(f"[stream] {model} stream failed: {exc!r}")
        router.on_failure(model)
        return


async def stream_answer_into_sink(
    query: str,
    docs: list[dict],
    sink: asyncio.Queue,
    tool_result: dict | None = None,
) -> str:
    """Generate the answer BY STREAMING tokens into `sink`, and return the
    full assembled answer string.

    CONCEPT (token-sink pattern):
    The graph node needs TWO things that pull in opposite directions:
      * the final, complete answer (so faithfulness grading can judge it,
        and so state carries a normal `answer` value)
      * live token-by-token updates (so the HTTP response can stream)

    The sink gives us BOTH: we accumulate locally while publishing each
    token to the queue.

    CONTRACT (who ends the stream):
    There is deliberately NO per-call "done" sentinel. The graph may run
    this node MORE THAN ONCE (faithfulness retry → regenerate), and each
    run would push a sentinel — a consumer that stops on the first one
    would cut off the second answer. Instead the consumer stops when the
    graph task itself completes AND the queue is empty: the queue's
    lifetime is exactly the graph's lifetime.

    ROUTING (Phase 7, Step 3):
    The router picks the model once (A/B on query complexity), then the
    token stream uses it — same model for the whole answer, same policy
    as the blocking path.

    Returns: the fully assembled answer string.
    """
    messages = build_generation_messages(query, docs, tool_result)

    # Pick the model ONCE (not per token!). The breaker lives in the router
    # and tracks this model's health across the whole app.
    model = get_router().pick_model(query)

    parts: list[str] = []
    async for token in _ollama_token_stream(messages, model=model):
        parts.append(token)
        # put_nowait: unbounded queue never blocks; consumer drains fast.
        sink.put_nowait({"kind": "token", "text": token})

    return "".join(parts)


def sse_frame(payload: dict) -> str:
    """Frame a dict as one server-sent event.

    CONCEPT (SSE framing):
    The wire format is exactly:  data: <payload> \\n\\n
    The two trailing newlines separate one event from the next — that is
    the ONLY delimiter the browser's EventSource understands.
    """
    return f"data: {json.dumps(payload)}\n\n"