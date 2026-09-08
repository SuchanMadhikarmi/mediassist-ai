"""
agent/hitl.py
─────────────
Human-in-the-Loop (HITL) helpers for the CRAG graph.

CONCEPT (HITL):
Some user requests imply a DANGEROUS / irreversible action (delete an
order, cancel a subscription, refund money, remove records). We must NOT
let the agent just do it automatically. Instead we pause the graph and
ask a human (admin / expert) for approval before proceeding.

This module is small and pure — it only decides WHETHER an action is
dangerous and builds a human-readable summary. The actual pausing
(interrupt) and resuming happens in the graph node / our API layer.

GENERAL PATTERN (reuse in any approval workflow):
    1. DETECT:   scan the user request for dangerous-action keywords.
    2. SUMMARIZE: build a short, human-readable description of what will be done.
    3. PAUSE:    the graph node calls interrupt(...) with that summary.
    4. APPROVE:  a human says yes/no; the graph resumes with that decision.
    5. ROUTE:    approved → act; rejected → do nothing (say "cancelled").
"""

import re

# Dangerous action keywords. A request containing these triggers HITL.
# Keep this obvious and simple for LEARNING. In production you'd use an
# LLM classifier to detect intent (more robust than keywords), but the
# *structure* of HITL stays identical regardless of how you detect danger.
DANGEROUS_PATTERNS = {
    "delete_orders": r"\b(delete|remove|drop)\b.*\b(order|orders|records?)\b",
    "cancel_order": r"\b(cancel)\b.*\b(order|subscription)\b",
    "refund": r"\b(refund|reimburse)\b",
    "delete_users": r"\b(delete|remove)\b.*\b(user|account|users)\b",
    "wipe_data": r"\b(wipe|clear|purge|delete_all|drop)\b.*\b(data|database|all)\b",
}


def is_dangerous(query: str) -> tuple[bool, str]:
    """Detect whether a query requests a dangerous action.

    Returns:
        (is_dangerous: bool, action_label: str)
        action_label is the *kind* of dangerous action (e.g. "delete_orders"),
        or "" if nothing dangerous was found.
    """
    q = query.lower()
    for label, pattern in DANGEROUS_PATTERNS.items():
        if re.search(pattern, q):
            return True, label
    return False, ""


def build_action_summary(query: str, action_label: str) -> str:
    """Build a short, human-readable description of the pending action.

    This is what the approving human sees. In a real system you'd enrich
    it with live data (e.g. exactly which order numbers will be deleted),
    but for learning the user's own words are enough.
    """
    return f"Execute dangerous action '{action_label}' requested by user: {query!r}"
