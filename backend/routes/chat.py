# ============================================================
# backend/routes/chat.py
# POST /chat        — answer using RAG + CRAG agent (one JSON block).
# POST /chat/stream — same, but streams answer tokens over SSE.
# POST /chat/resume — resume a HITL-paused chat with a decision.
#
# Phase 6 full version: CRAG graph + tool calling + faithfulness +
# Human-in-the-Loop (dangerous actions pause for approval).
#
# HITL flow (the reusable approval-workflow pattern):
#   1. user sends a question
#   2. graph runs; if it detects a DANGEROUS request it PAUSES
#   3. POST /chat returns {"status":"needs_approval", thread_id, action}
#   4. a human calls POST /chat/resume {thread_id, approve}
#   5. graph resumes: approve→answers, reject→safe refusal
#
# Why thread_id matters:
#   With a Postgres checkpointer, every conversation is keyed by a
#   thread_id. The paused state is saved under that id, so /chat/resume
#   can pick up exactly where the graph stopped.
# ============================================================

import asyncio
import contextlib
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from security.auth import get_current_user
from security.pii_redactor import redact_pii
from agent.graph import get_crag_graph
from agent.hitl import is_dangerous, build_action_summary
from langgraph.types import Command
from llmops.cache import get_cache
from llmops.router import get_router
from llmops.streaming import sse_frame
from llmops.telemetry import chat_span_ctx

router = APIRouter(prefix="/chat", tags=["chat"])

# The answer we give when retrieval found nothing relevant. Kept as a
# constant so the cache FILL logic can detect & refuse to cache failures.
FALLBACK_ANSWER = (
    "I could not find relevant information about that in the "
    "available documents. Please try rephrasing your question "
    "or check that the relevant manual has been uploaded."
)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]  # citations the LLM can reference
    cached: bool = False  # True = answered from the semantic cache (no LLM)


class ApprovalRequest(BaseModel):
    thread_id: str
    approve: bool


class ApprovalResponse(BaseModel):
    status: str          # "answered" or "rejected"
    answer: str
    thread_id: str


def _build_initial_state(message: str, role: str) -> dict:
    """Build the AgentState for a fresh chat run.

    Includes ALL fields the graph nodes read/write, so the state schema
    is complete from the first step.
    """
    return {
        "query": message,
        "rbac_label": role,          # used by retrieve() for data-level RBAC
        "docs": [],
        "answer": "",
        "retries": 0,
        "need_tool": False,
        "tool_result": None,
        "is_faithful": False,
        "requires_approval": False,
        "action_summary": "",
        "approval": "",
    }


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: dict = Depends(get_current_user),
):
    """Answer a question through the CRAG graph.

    If the graph PAUSES for HITL (dangerous action), this endpoint raises
    an HTTP 409 so the frontend knows to ask for human approval. The
    thread_id needed to resume is returned in the error detail.
    """
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # ── CACHE GATE ────────────────────────────────────────────────
    # Lookup BEFORE the graph: a hit returns instantly — the graph and
    # the LLM never even start. Namespaced by role → no cross-role leak.
    cache = get_cache(user["role"])
    entry, _similarity = await cache.lookup(body.message)
    if entry is not None:
        return ChatResponse(answer=entry.answer, sources=entry.sources, cached=True)

    graph = get_crag_graph()

    # A fresh thread per request lets us resume paused chats later.
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = _build_initial_state(body.message, user["role"])

    # ── MANUAL SPAN (telemetry): capture BUSINESS context that the auto-
    #    instrumented FastAPI/httpx spans don't know about (role, cache
    #    status, model route, final answer length). See llmops/telemetry.py.
    model_route = get_router().pick_model(body.message)
    snapshot = None
    with chat_span_ctx(body.message, user["role"]) as span:
        await graph.ainvoke(initial_state, config=config)
        snapshot = await graph.aget_state(config)  # final state (or paused)
        state_vals = snapshot.values
        span.set_attribute("chat.thread_id", thread_id)
        span.set_attribute("chat.cached", False)
        span.set_attribute("chat.model", model_route)
        span.set_attribute("chat.tool_used", bool(state_vals.get("need_tool")))
        span.set_attribute(
            "chat.answer_length", len(state_vals.get("answer") or "")
        )

    # Did the graph pause for HITL? Check if it never reached END.
    if snapshot.next:  # non-empty 'next' = paused mid-graph (check_hitl)
        # The graph paused INSIDE interrupt() — its action_summary update is
        # not written to the thread yet. Detect via the same pure helper to
        # give the human a readable description of what's pending approval.
        # (Detection is a pure function in agent/hitl.py → reusable anywhere.)
        _dangerous, _label = is_dangerous(body.message)
        summary = build_action_summary(body.message, _label) if _dangerous else ""
        raise HTTPException(
            status_code=409,
            detail={
                "status": "needs_approval",
                "thread_id": thread_id,
                "action": summary,
                "message": "This request requires human approval before it can be acted on.",
            },
        )

    response = _to_response(snapshot.values)

    # ── CACHE FILL ────────────────────────────────────────────────
    # Store ONLY when the answer is a REAL success:
    #   1) not the failure placeholder     (never cache a failure)
    #   2) the graph did NOT use the tool  (live ERP data goes stale)
    # Dangerous (HITL) requests never reach here — they 409'd above,
    # and pipeline answers that needed the tool never get cached.
    state = snapshot.values
    if response.answer != FALLBACK_ANSWER and not state.get("need_tool"):
        await cache.store(body.message, response.answer, response.sources)

    return response


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    user: dict = Depends(get_current_user),
):
    """Answer a question through the CRAG graph, streaming tokens over SSE.

    Same pipeline as POST /chat — cache gate, CRAG graph, cache fill —
    but instead of returning one JSON block it pushes each generated
    token as a separate server-sent event:

        data: {"kind": "started", "cached": false}
        data: {"kind": "token",   "text": "Error"}
        data: {"kind": "token",   "text": " Code"}
        ...
        data: {"kind": "sources", "sources": [...]}
        data: {"kind": "done"}

    SECURITY (why danger is checked here, before any stream):
    Once the response headers are sent you cannot raise a 409 mid-stream.
    So a dangerous request is refused BEFORE the stream opens — same
    status code and meaning as POST /chat, but earlier. Streaming never
    weakens HITL: refusal still comes from the pure hitl helper.
    """
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    cache = get_cache(user["role"])

    # ── CACHE GATE (same as /chat) ──────────────────────────────
    # On a hit there is nothing to generate — "stream" the whole cached
    # answer as a single self-contained event, instantly.
    entry, _similarity = await cache.lookup(body.message)
    if entry is not None and entry.answer.strip():

        async def _cached_stream():
            yield sse_frame({"kind": "started", "cached": True})
            yield sse_frame({
                "kind": "answer",
                "answer": entry.answer,
                "sources": entry.sources,
                "cached": True,
            })
            yield sse_frame({"kind": "done"})

        return StreamingResponse(_cached_stream(), media_type="text/event-stream")

    # ── HITL REFUSAL BEFORE STREAMING (see docstring for the why) ──
    # A dangerous request must NOT be streamed: once headers are sent we
    # cannot raise a 409 mid-stream. Unlike the old pure pre-check, we let
    # the GRAPH create the paused thread first (check_hitl is node 1 and
    # interrupt()s BEFORE any LLM/retrieve work, so this is cheap), then
    # refuse with the REAL thread_id so the frontend can /chat/resume it.
    _dangerous, label = is_dangerous(body.message)
    if _dangerous:
        graph = get_crag_graph()
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        await graph.ainvoke(_build_initial_state(body.message, user["role"]), config=config)
        snapshot = await graph.aget_state(config)
        if not snapshot.next:
            raise HTTPException(
                status_code=500,
                detail="Graph did not pause for approval despite a dangerous request.",
            )
        raise HTTPException(
            status_code=409,
            detail={
                "status": "needs_approval",
                "thread_id": thread_id,
                "action": build_action_summary(body.message, label),
                "message": "This request requires human approval before it can be acted on.",
            },
        )

    # ── TOKEN-SINK WIRING ───────────────────────────────────────
    # A queue travels in the graph CONFIG. The generate node streams
    # tokens into it; this endpoint pumps them out to the client. The
    # graph and the HTTP stream thus run CONCURRENTLY on one loop.
    graph = get_crag_graph()
    thread_id = str(uuid.uuid4())
    sink: asyncio.Queue = asyncio.Queue()
    config = {
        "configurable": {
            "thread_id": thread_id,
            "token_sink": sink,  # generate node pushes {"kind":"token",...}
        }
    }
    initial_state = _build_initial_state(body.message, user["role"])
    task = asyncio.create_task(graph.ainvoke(initial_state, config=config))

    async def _stream():
        yield sse_frame({"kind": "started", "cached": False})

        # ── PUMP: consume the queue while the graph runs ──────────
        # ASYNC LESSON (check-then-await race):
        # `while not (task.done() and sink.empty()): await sink.get()`
        # LOOKS right but is buggy: the condition is only tested BEFORE
        # the await. If the graph emits its final token and then finishes
        # while we're parked in `await sink.get()`, nothing will ever
        # wake us up. FIX: await BOTH the token future and the task
        # (FIRST_COMPLETED) — whichever fires first wakes us. This is a
        # reusable pattern whenever you merge two async event sources.
        tokens: list[str] = []
        while True:
            get_future = asyncio.ensure_future(sink.get())
            _done, _pending = await asyncio.wait(
                {get_future, task}, return_when=asyncio.FIRST_COMPLETED
            )
            if get_future in _done:
                item = get_future.result()
                if item["kind"] == "token":
                    tokens.append(item["text"])
                    yield sse_frame({"kind": "token", "text": item["text"]})
                continue  # task still running → keep consuming

            # Only the graph task completed. Cancel the parked get(),
            # drain any tokens already buffered, then stop.
            get_future.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await get_future
            while not sink.empty():
                item = sink.get_nowait()
                if item["kind"] == "token":
                    tokens.append(item["text"])
                    yield sse_frame({"kind": "token", "text": item["text"]})
            break

        # Propagate a graph failure as an SSE error event (headers are
        # already sent, so a plain exception would just abort mid-stream).
        try:
            result = await task
        except Exception as exc:  # pragma: no cover - network/model failure
            yield sse_frame({"kind": "error", "message": str(exc)})
            return

        # ── CACHE FILL (same rules as /chat) ─────────────────────
        # Build the answer the same way the JSON path does. If the graph
        # finished with NO tokens and NO answer (e.g. retrieval retries
        # exhausted on a query like a bare greeting), substitute the
        # FALLBACK_ANSWER — mirroring `_to_response` — so the client is
        # never left with an empty reply. An empty string must never be
        # cached (it's not a real success).
        answer = "".join(tokens) if tokens else (result.get("answer") or "")
        if not answer.strip():
            answer = FALLBACK_ANSWER
        sources = _build_sources(result)
        if answer != FALLBACK_ANSWER and not result.get("need_tool"):
            await cache.store(body.message, answer, sources)

        # If nothing was streamed token-by-token (e.g. the graph ended on a
        # non-generating path with a final answer, or an empty result was
        # substituted with the fallback above), send the FULL answer as a
        # single event. The client renders this exactly like a cache hit.
        if not tokens:
            yield sse_frame({"kind": "answer", "answer": answer, "sources": sources})
        yield sse_frame({"kind": "sources", "sources": sources})
        yield sse_frame({"kind": "done"})

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.post("/resume", response_model=ApprovalResponse)
async def resume(
    body: ApprovalRequest,
    user: dict = Depends(get_current_user),
):
    """Resume a HITL-paused chat with the human's decision.

    Only admin/expert roles should be allowed to approve dangerous actions
    (RBAC enforced via get_current_user + a role check below).
    """
    if user["role"] not in ("admin", "expert"):
        raise HTTPException(status_code=403, detail="Only admin/expert can approve actions")

    graph = get_crag_graph()
    config = {"configurable": {"thread_id": body.thread_id}}

    # The value passed here becomes the return value of interrupt() inside
    # check_hitl. check_hitl maps "approved" → proceed, else → blocked.
    decision = "approved" if body.approve else "rejected"
    await graph.ainvoke(Command(resume=decision), config=config)

    snapshot = await graph.aget_state(config)
    if snapshot.next:
        raise HTTPException(
            status_code=409,
            detail="Graph did not finish after resume; thread may be in an inconsistent state.",
        )

    # The answer lives in the full graph STATE, not in ainvoke's return
    # value (ainvoke returns only the last node's dict, which for a
    # multi-node run is empty). Read it from the final checkpoint.
    state_vals = snapshot.values
    return ApprovalResponse(
        status="answered" if body.approve else "rejected",
        answer=(state_vals.get("answer") or "").strip(),
        thread_id=body.thread_id,
    )


def _build_sources(state_values: dict) -> list[dict]:
    """Extract the citable sources from final graph state (shared helper).

    Used by BOTH response builders (_to_response for JSON, the stream
    endpoint for the SSE "sources" event) so citations are identical
    regardless of delivery format.
    """
    sources = []
    for doc in state_values.get("docs", []):
        payload = doc.get("payload", {})
        if doc.get("rerank_score", -999) > 0:
            text = redact_pii(doc.get("text", ""))
            sources.append({
                "text": text,
                "source": payload.get("source"),
                "page": payload.get("page"),
                "rerank_score": doc.get("rerank_score"),
            })
    return sources


def _to_response(state_values: dict) -> ChatResponse:
    """Convert final graph state into the API response (with citations)."""
    answer = (state_values.get("answer") or "").strip()
    if not answer:
        return ChatResponse(answer=FALLBACK_ANSWER, sources=[])

    return ChatResponse(answer=answer, sources=_build_sources(state_values))
