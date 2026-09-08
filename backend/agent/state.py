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
        need_tool:  Set by grade_sufficiency — True if the docs are NOT
                    enough and we must call an external tool (ERP lookup).
        tool_result: Data returned by a tool call (e.g. ERP order lookup).
                     None until a tool runs. Federation source for generate.
        is_faithful: Set by grade_faithfulness — whether the answer is
                     grounded in the docs (drives the regenerate loop).
        requires_approval: Set by check_hitl — True if a dangerous action
                     was requested and a human must approve before we act.
        action_summary: Human-readable description of the pending action
                     (shown to the approving human).
        approval:   The human's decision after HITL resume: "approved",
                     "rejected", or "" (no decision yet / not applicable).
    """

    query: str
    rbac_label: str
    docs: list
    answer: str
    retries: int
    need_tool: bool
    tool_result: dict | None
    is_faithful: bool
    requires_approval: bool
    action_summary: str
    approval: str
