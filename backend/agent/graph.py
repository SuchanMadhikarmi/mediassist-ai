"""
agent/graph.py
──────────────
Builds and compiles the LangGraph CRAG (Corrective RAG) graph.

This file is pure wiring — it connects nodes with edges and compiles
the graph into a runnable object. No business logic lives here.

Graph structure (Phase 6 — tool calling + sufficiency + faithfulness + HITL):
    START ──→ check_hitl ──► [decide_hitl]
                                    │
                       ┌────────────┴────────────┐
                       ▼                         ▼
                   retrieve               blocked_action
                       │                         │
                       ▼                         ▼
                   grade_docs                   END
                       │
               [decide_route]
                       │
           ┌────────────┼────────────┐
           ▼            ▼            ▼
     grade_suff    reformulate     END
           │            │
           ▼            └──→ retrieve (loop)
     [decide_tool]
           │
    ┌──────┴──────┐
    ▼             ▼
 query_erp    generate
    │             │
    └───────► generate
                  │
           [decide_faithful]
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
    generate (loop)          END

Notes:
  - "check_hitl" is FIRST (Phase 7 security fix): EVERY request passes the
    HITL gate before any retrieval, so dangerous queries can NEVER bypass
    approval — even if they retrieve no docs (the old bug: it only ran on
    the retrieval-success path).
  - "grade_docs" routes by RECALL (did we retrieve anything relevant?).
  - "grade_sufficiency" routes by COMPLETENESS (do we need live data?).
  - "query_erp" is the tool node — fetches live ERP data into state.
  - "blocked_action" emits a safe refusal when a dangerous action is rejected.
  - "grade_faithfulness" routes by GROUNDEDNESS (did the answer hallucinate?).
"""

from langgraph.graph import StateGraph, START, END

from agent.state import AgentState
from agent.checkpointer import get_checkpointer
from agent.nodes import (
    retrieve,
    grade_docs,
    grade_sufficiency,
    query_erp_node,
    generate,
    grade_faithfulness,
    reformulate,
    check_hitl,
    blocked_action,
    approved_action,
    decide_route,
    decide_tool,
    decide_faithful,
    decide_hitl,
)


def build_crag_graph():
    """Construct and compile the CRAG state machine (call ONLY inside an
    event loop — it creates the async Postgres checkpointer).

    Returns:
        A compiled LangGraph that can be invoked with an initial AgentState.
    """
    graph = StateGraph(AgentState)

    # ── Add nodes ────────────────────────────────────────────────
    graph.add_node("retrieve", retrieve)
    graph.add_node("grade_docs", grade_docs)
    graph.add_node("grade_sufficiency", grade_sufficiency)
    graph.add_node("query_erp", query_erp_node)
    graph.add_node("generate", generate)
    graph.add_node("grade_faithfulness", grade_faithfulness)
    graph.add_node("check_hitl", check_hitl)
    graph.add_node("blocked_action", blocked_action)
    graph.add_node("approved_action", approved_action)
    graph.add_node("reformulate", reformulate)

    # ── Wire edges ───────────────────────────────────────────────
    # Entry point: FIRST pass through the HITL safety gate.
    # WHY at the start (bug found in the Phase 7 live test):
    #   check_hitl used to sit only on the retrieval-SUCCESS path. A
    #   dangerous query with NO matching docs exited via reformulate→END
    #   and NEVER reached check_hitl — HITL bypassed. Placing it before
    #   retrieval guarantees EVERY request passes the gate, and we never
    #   waste retrieval/LLM compute on a request we're about to pause.
    graph.add_edge(START, "check_hitl")

    # After the safety gate: approved/not-dangerous → retrieve;
    # rejected → safe refusal (no generation at all).
    graph.add_conditional_edges(
        "check_hitl",
        decide_hitl,
        {
            "proceed":  "retrieve",
            "approved": "approved_action",
            "blocked":  "blocked_action",
        },
    )

    graph.add_edge("retrieve", "grade_docs")

    # After grading, decide where to go (the conditional edge).
    graph.add_conditional_edges(
        "grade_docs",          # from this node
        decide_route,          # call this function to decide
        {
            "generate":    "grade_sufficiency",  # relevant docs found → are they enough?
            "reformulate": "reformulate",   # no relevant docs, retry
            "__end__":     END,             # retries exhausted
        },
    )

    # After checking sufficiency, decide whether to call the tool.
    # With check_hitl now at START, both branches go straight to generate
    # (or to the safe refusal path already handled above).
    graph.add_conditional_edges(
        "grade_sufficiency",
        decide_tool,
        {
            "query_erp": "query_erp",   # docs not enough → fetch live data
            "generate":  "generate",    # docs enough → answer directly
        },
    )

    # After the tool fetches live data, answer (safety already gated).
    graph.add_edge("query_erp", "generate")

    # A rejected or approved dangerous action is final — no generation, straight to end.
    graph.add_edge("blocked_action", END)
    graph.add_edge("approved_action", END)

    # After generating, check whether the answer is grounded (faithful).
    graph.add_edge("generate", "grade_faithfulness")

    # Decide: faithful → done; not faithful → regenerate (loop).
    graph.add_conditional_edges(
        "grade_faithfulness",
        decide_faithful,
        {
            "generate": "generate",  # not faithful & retries left → try again
            "__end__":  END,          # faithful (or retries exhausted) → done
        },
    )

    # After reformulating, go back to retrieve (the loop).
    graph.add_edge("reformulate", "retrieve")

    # ── Compile ──────────────────────────────────────────────────
    # The checkpointer enables:
    #   - HITL pause/resume (interrupt + resume across HTTP requests)
    #   - per-thread graph runs (thread_id in config)
    #
    # get_checkpointer() is a LAZY singleton: it creates the async pool on
    # first call. Because AsyncConnectionPool needs a running event loop,
    # we must call this inside a running app, not at module import.
    compiled = graph.compile(checkpointer=get_checkpointer())
    return compiled


# ── Lazy module-level singleton ────────────────────────────────
# Cannot be built at import time (async checkpointer needs a loop), so we
# build it lazily on first use and cache it. Routes must call
# get_crag_graph() instead of importing a module-level object.
_crag_graph = None


def get_crag_graph():
    """Return (or lazily build & cache) the compiled CRAG graph."""
    global _crag_graph
    if _crag_graph is None:
        _crag_graph = build_crag_graph()
    return _crag_graph
