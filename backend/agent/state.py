"""
agent/state.py
──────────────
Shared state that flows through every node in the LangGraph CRAG graph.

Every node reads what it needs and writes back what it changed.
LangGraph passes this dict between nodes automatically.
"""

from typing import TypedDict


class AgentState(TypedDict):
    """State passed between nodes in the CRAG graph.

    Fields:
        query:      The user's question (may be rewritten by reformulate).
        rbac_label: The user's role (used for RBAC filtering in retriever).
        docs:       Retrieved chunks from Qdrant (list of dicts with 'text',
                    'payload', 'rerank_score').
        answer:     Final LLM-generated answer (written by generate node).
        retries:    How many times we've retried retrieval (caps loops).
    """

    query: str
    rbac_label: str
    docs: list
    answer: str
    retries: int
