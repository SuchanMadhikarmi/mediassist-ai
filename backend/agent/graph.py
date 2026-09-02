"""
agent/graph.py
──────────────
Builds and compiles the LangGraph CRAG (Corrective RAG) graph.

This file is pure wiring — it connects nodes with edges and compiles
the graph into a runnable object. No business logic lives here.

Graph structure:
    START ──→ retrieve ──→ grade_docs ──→ [decide_route]
                                                │
                                    ┌───────────┼───────────┐
                                    ▼           ▼           ▼
                                generate   reformulate    END
                                    │           │
                                    ▼           └──→ retrieve (loop)
                                  END
"""

from langgraph.graph import StateGraph, START, END

from agent.state import AgentState
from agent.nodes import retrieve, grade_docs, generate, reformulate, decide_route


def build_crag_graph():
    """Construct and compile the CRAG state machine.

    Returns:
        A compiled LangGraph that can be invoked with an initial AgentState.
    """
    graph = StateGraph(AgentState)

    # ── Add nodes ────────────────────────────────────────────────
    graph.add_node("retrieve", retrieve)
    graph.add_node("grade_docs", grade_docs)
    graph.add_node("generate", generate)
    graph.add_node("reformulate", reformulate)

    # ── Wire edges ───────────────────────────────────────────────
    # Entry point: always start with retrieval.
    graph.add_edge(START, "retrieve")

    # After retrieval, grade the docs.
    graph.add_edge("retrieve", "grade_docs")

    # After grading, decide where to go (the conditional edge).
    graph.add_conditional_edges(
        "grade_docs",          # from this node
        decide_route,          # call this function to decide
        {
            "generate":    "generate",      # relevant docs found
            "reformulate": "reformulate",   # no relevant docs, retry
            "__end__":     END,             # retries exhausted
        },
    )

    # After generating an answer, we're done.
    graph.add_edge("generate", END)

    # After reformulating, go back to retrieve (the loop).
    graph.add_edge("reformulate", "retrieve")

    # ── Compile ──────────────────────────────────────────────────
    compiled = graph.compile()
    return compiled


# Module-level singleton — build once, import everywhere.
crag_graph = build_crag_graph()
