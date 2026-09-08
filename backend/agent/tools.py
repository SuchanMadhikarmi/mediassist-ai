"""
agent/tools.py
──────────────
ERP mock tools — functions the agent can call to get LIVE data
that is NOT stored in the document (PDF) corpus.

CONCEPT (Tool calling / Part 1 — the TOOL itself):
A "tool" is just a plain Python function with a name, inputs, and an
output. It knows how to go get real data. In a real system this would
call an ERP HTTP API; here it queries our PostgreSQL erp_orders table
(the Data Tier we built in Phase 3.5).

The LLM does NOT execute this. Our Python code (in the query_erp graph
node) calls it and feeds the result back to the LLM. This separation is
the security boundary — only functions WE expose can ever run.
"""

import re

from sqlalchemy.orm import Session

from database import SessionLocal
from models import ErpOrder

# The tool "schema" that describes this tool to the LLM (Phase 6 concept 4).
# The LLM reads this to decide WHEN to call the tool and WHAT arguments
# to provide. This is the translation layer between the LLM and our code.
ERP_TOOL_SCHEMA = {
    "name": "query_erp",
    "description": (
        "Look up the current status/amount/product of a customer order in the "
        "ERP system by its order number (e.g. 'ORD-1003'). Use this ONLY when "
        "the user asks about LIVE order data that is not in the documents."
    ),
    "parameters": {
        "order_number": {
            "type": "string",
            "description": "The order number, like ORD-1003",
        }
    },
}


def query_erp(order_number: str) -> dict | None:
    """Query the live ERP order table. Returns a dict or None if not found.

    A plain function — reusable and testable on its own, completely
    decoupled from LangGraph. This is what makes 'tools' portable: the
    same function could be called by ANY agent framework, a unit test,
    or an API route.
    """
    # Normalize: accept "1003", "ORD1003", "ord-1003" as well as "ORD-1003".
    order_number = order_number.strip().upper()
    if not order_number.startswith("ORD-"):
        order_number = "ORD-" + order_number

    db: Session = SessionLocal()
    try:
        order = (
            db.query(ErpOrder)
            .filter(ErpOrder.order_number == order_number)
            .first()
        )
        if order is None:
            return None
        # Return a CLEAN dict (shape we want the LLM to see) — not the ORM
        # object, so we control exactly what reaches the model.
        return {
            "order_number": order.order_number,
            "customer_name": order.customer_name,
            "status": order.status,
            "amount": order.amount,
            "product": order.product,
        }
    finally:
        db.close()


def extract_order_number(query: str) -> str | None:
    """Naive helper: pull an order number out of free-text user query.

    Matches "ORD-1003" / "ORD1003" (prefixed), or a bare 4-digit number
    following the word "order" (e.g. "status of order 1002"). This is a
    simple heuristic. (In a full system, the LLM would extract the
    argument via the tool schema; for learning, a regex is enough and
    keeps the flow explicit and debuggable.)
    """
    q = query.upper()
    # Prefixed form wins first: "ORD-1003" or "ORD1003".
    m = re.search(r"ORD-?\d+", q)
    if m:
        return m.group(0)
    # Fallback: the word "order" followed by a 4-digit number → "ORD-<num>".
    m = re.search(r"ORDER\s+(\d{4})", q)
    if m:
        return "ORD-" + m.group(1)
    return None
