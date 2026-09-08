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
from ai_engine.llm import grade_sufficiency as grade_sufficiency_judge
from ai_engine.llm import grade_faithfulness as grade_faithfulness_judge
from langgraph.types import interrupt
from agent.state import AgentState
from agent.tools import extract_order_number, query_erp
from agent.hitl import is_dangerous, build_action_summary


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


# ── Node 2.5: grade_sufficiency ────────────────────────────────
async def grade_sufficiency(state: AgentState) -> dict:
    """Decide whether the retrieved docs are ENOUGH to answer, or whether
    we need to call an external tool for LIVE data (ERP lookup).

    CONCEPT (Sufficiency): relevance says "on topic", sufficiency says
    "do we have everything needed?" A question like "status of order
    ORD-1003" is relevant to the company's docs but the SPECIFIC live
    status is NOT in any PDF — so we need the tool.

    IMPORTANT: unlike grade_docs (which returned {} and let the edge
    re-derive), this node does REAL async work (an LLM judge call) whose
    verdict MUST be stored so the conditional edge can route on it.

    Reads:  query, docs
    Writes: need_tool (bool)
    """
    docs = state.get("docs", [])

    # If there are no docs at all, we clearly can't answer — call a tool
    # or (if no tool matches) we'll fall through to generate which says so.
    if not docs:
        print("[grade_sufficiency] No docs — requesting tool lookup.")
        return {"need_tool": True}

    # Ask the LLM judge whether the docs are sufficient.
    verdict = await grade_sufficiency_judge(query=state["query"], docs=docs)
    need_tool = (verdict == "no")
    print(f"[grade_sufficiency] verdict={verdict} need_tool={need_tool}")
    return {"need_tool": need_tool}


# ── Node 2.6: query_erp ────────────────────────────────────────
def query_erp_node(state: AgentState) -> dict:
    """Execute the ERP tool to fetch LIVE order data and store it in state.

    CONCEPT (Tool calling / Part 2 — executing the tool):
    THIS is the security-critical part. Our CODE (not the LLM) decides to
    run query_erp(), and our CODE validates the input via the regex helper.
    The LLM never executes anything — we do, then hand the result back.

    Reads:  query
    Writes: tool_result (the live order data)
    """
    order_number = extract_order_number(state["query"])
    if order_number:
        result = query_erp(order_number)
        if result is not None:
            print(f"[query_erp] Found {order_number}: {result['status']}")
            return {"tool_result": result}

    # Order not found / no order in query — store a clear note instead.
    print("[query_erp] No matching order found.")
    return {
        "tool_result": {
            "error": f"No order found for '{order_number or 'the query'}'. "
                     "Tell the user you could not find the order."
        }
    }


# ── Conditional edge after grade_sufficiency ────────────────────
def decide_tool(state: AgentState) -> str:
    """Decide whether to call the ERP tool or go straight to generation.

    Returns:
        "query_erp" — docs insufficient, go fetch live data.
        "generate"  — docs are enough, answer directly.
    """
    if state.get("need_tool"):
        return "query_erp"
    return "generate"


# ── Node 2.7: check_hitl ───────────────────────────────────────
def check_hitl(state: AgentState) -> dict:
    """Detect dangerous requests and PAUSE the graph for human approval.

    CONCEPT (HITL / human-in-the-loop):
    If the user requests a dangerous/irreversible action, we must not let
    the agent just proceed. We:
      1. Detect danger with a keyword scan (hitl.py).
      2. Call interrupt(...) — THIS IS THE MAGIC. It STOPS execution right
         here, returns control to our API, and saves the full graph state
         (via the Postgres checkpoint). The returned value from interrupt
         is the human's decision — available when we RESUME.
      3. If not dangerous, we sail through with requires_approval=False.

    NOTE on interrupts and state writes:
    The dict we return BEFORE/AFTER interrupt matters. When we first hit
    interrupt, execution halts — our returned updates are NOT yet written.
    On resume, this node runs again, `interrupt` gives us the approval,
    and THEN we return the final updates (which DO get applied).

    Reads:  query
    Writes: requires_approval, action_summary, approval
    """
    dangerous, action_label = is_dangerous(state["query"])

    if not dangerous:
        print("[check_hitl] Not dangerous — proceed.")
        return {
            "requires_approval": False,
            "action_summary": "",
            "approval": "",
        }

    # Dangerous action detected. Pause and wait for human approval.
    action_summary = build_action_summary(state["query"], action_label)
    print(f"[check_hitl] DANGEROUS — pausing for approval: {action_summary}")

    # This call suspends the graph. It returns the human's resume value.
    decision = interrupt(action_summary)

    # ── We're here only AFTER the human resumes us ──────────────
    # decision is whatever the API passed to resume (e.g. "approved"/"rejected").
    approved = (str(decision).strip().lower() == "approved")
    print(f"[check_hitl] Resume received: decision={decision!r} approved={approved}")
    return {
        "requires_approval": False,     # pause is over now
        "action_summary": action_summary,
        "approval": "approved" if approved else "rejected",
    }


# ── Conditional edge after check_hitl ──────────────────────────
def decide_hitl(state: AgentState) -> str:
    """Route after a HITL pause is resolved.

    CONCEPT (TEACHABLE nuance):
    After resume, check_hitl sets requires_approval=False (the pause is
    over). So we CANNOT use requires_approval to decide routing — it's
    False both for "never dangerous" and "dangerous but now resolved".
    Instead we use `action_summary`: a non-empty summary means this WAS a
    dangerous request that went through HITL. Its outcome lives in
    `approval`.

    Returns:
        "proceed"      — not dangerous at all: normal RAG flow.
        "approved"     — dangerous BUT a human APPROVED it → confirm + END.
        "blocked"      — dangerous and NOT approved → emit a safe refusal.
    """
    # A non-empty action_summary marks this as a dangerous request that
    # went through HITL. If there's no summary, nothing was dangerous.
    was_dangerous = bool(state.get("action_summary"))

    if not was_dangerous:
        return "proceed"

    # Dangerous: a human approved it → confirm (see approved_action).
    if state.get("approval") == "approved":
        return "approved"

    # Dangerous and not approved → safe refusal.
    return "blocked"


# ── Node 2.8: blocked_action ───────────────────────────────────
def blocked_action(state: AgentState) -> dict:
    """Produce a SAFE refusal when a dangerous action was rejected.

    CONCEPT (HITL — the 'rejected' path):
    When the human rejects (or never approves) the dangerous action, we must
    NOT execute anything. Instead we write a clear refusal message into
    `answer` and route straight to END — skipping generate entirely.

    Reads:  query, action_summary
    Writes: answer (the refusal message)
    """
    summary = state.get("action_summary", "")
    print(f"[blocked_action] Refusing dangerous action: {summary}")
    return {
        "answer": (
            "❌ Action not executed. A human did not approve this dangerous "
            "action. If you believe this is a mistake, contact an admin or expert."
        )
    }


# ── Node 2.9: approved_action ──────────────────────────────────
def approved_action(state: AgentState) -> dict:
    """Emit a clear confirmation when a dangerous action was APPROVED.

    CONCEPT (HITL — the 'approved' path, and WHY it differs from RAG):
    A destructive request (delete orders, refund, wipe data) is NOT a
    documentation question — there are no manuals about "how to delete an
    order". Routing an approved destructive action through `retrieve` would
    therefore find nothing and produce an empty / fallback answer, which is
    confusing for the approving human ("I clicked approve, why is it blank?").

    So, mirroring `blocked_action`, we short-circuit to a direct confirmation
    and route to END — skipping the pointless RAG search. A real ERP-backed
    system would replace the text below with an actual API call that deletes
    the order and returns the result; the HITL *flow* stays identical.

    Reads:  query, action_summary, approval
    Writes: answer (the confirmation message)
    """
    action_label = state.get("action_summary", "").split("'")[1] \
        if "'" in state.get("action_summary", "") else "the requested action"
    print(f"[approved_action] Executing approved action: {action_label}")
    return {
        "answer": (
            f"✅ Action approved and executed: the request to "
            f"'{action_label}' has been completed. "
            "No further steps are required. If you need a report of "
            "exactly what changed, ask an expert to pull the audit log."
        )
    }


# ── Node 3: generate ────────────────────────────────────────────
async def generate(state: AgentState, config: dict | None = None) -> dict:
    """Call Ollama to produce a cited answer from the retrieved context.

    Now also feeds LIVE data (tool_result) into the context so the answer
    can reference real ERP data when a tool was called.

    STREAMING (Phase 7, Step 2):
    LangGraph passes the run `config` as the second argument to any node
    that declares it. If the API layer tucked an asyncio.Queue into
    `config["configurable"]["token_sink"]`, we stream tokens into it
    WHILE ALSO accumulating the full answer into state — so the
    faithfulness gate below still grades the real, complete answer.
    Without a sink, behavior is unchanged (plain one-shot generation).

    Reads:  query, docs, tool_result   (+ config for the optional sink)
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

    configurable = (config or {}).get("configurable", {})
    sink = configurable.get("token_sink")

    if sink is not None:
        # Stream mode: tokens flow to the HTTP route; we keep the full text.
        from llmops.streaming import stream_answer_into_sink

        answer = await stream_answer_into_sink(
            query=state["query"],
            docs=llm_docs,
            sink=sink,
            tool_result=state.get("tool_result"),
        )
    else:
        answer = await generate_answer(
            query=state["query"],
            docs=llm_docs,
            # Pass live ERP data if the tool ran (None otherwise).
            tool_result=state.get("tool_result"),
        )
    # Each generation counts as an "attempt". This bounds the faithfulness
    # loop (decide_faithful reads retries >= MAX_RETRIES to stop). It also
    # bounds the whole graph for any path, preventing infinite loops.
    return {"answer": answer, "retries": state.get("retries", 0) + 1}


# ── Node 3.5: grade_faithfulness ───────────────────────────────
async def grade_faithfulness(state: AgentState) -> dict:
    """Check whether the generated answer is grounded in the context.

    CONCEPT (Faithfulness grading):
    Uses the same "LLM-as-judge" pattern as sufficiency. After we generate
    an answer, we ask a judge LLM whether the answer's claims are SUPPORTED
    by the docs + tool data, or whether the model hallucinated extra facts.

    We do real async work here (an LLM call), so the verdict MUST be stored
    in state — a conditional edge reads it to decide: regenerate or finish.

    Reads:  query, docs, answer, tool_result
    Writes: is_faithful (bool)
    """
    # If there's no answer yet, there's nothing to check — treat as faithful
    # so the graph doesn't loop pointlessly.
    if not state.get("answer"):
        print("[grade_faithfulness] No answer to grade — finish.")
        return {"is_faithful": True}

    verdict = await grade_faithfulness_judge(
        query=state["query"],
        docs=state["docs"],
        answer=state["answer"],
        tool_result=state.get("tool_result"),
    )
    is_faithful = (verdict == "yes")
    print(f"[grade_faithfulness] verdict={verdict} is_faithful={is_faithful}")
    return {"is_faithful": is_faithful}


# ── Conditional edge after grade_faithfulness ──────────────────
def decide_faithful(state: AgentState) -> str:
    """Decide whether to accept the answer or regenerate it.

    Returns:
        "generate"     — not faithful & we still have retries left → retry.
        "__end__"      — faithful (or out of retries) → done.
    """
    is_faithful = state.get("is_faithful", False)
    retries = state.get("retries", 0)

    # Accept a faithful answer. Also stop if we've run out of retries so we
    # never loop forever (the retries counter is shared with the retrieval
    # loop, which is fine — both are "how many times we tried").
    if is_faithful or retries >= MAX_RETRIES:
        return "__end__"

    # Not faithful and we can still try again → regenerate.
    return "generate"


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
