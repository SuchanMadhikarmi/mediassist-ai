# ============================================================
# backend/tests/test_hitl.py
# Deterministic tests for the HITL danger gate (Phase 6, Step C).
#
# WHY: is_dangerous() is the SECURITY gate before an agent acts. A
# regression here ("oops, now 'delete order' passes through") would let
# an LLM execute destructive actions without human approval. These tests
# pin the exact behavior so any future change is forced to keep it.
# ============================================================

import pytest

from agent.hitl import DANGEROUS_PATTERNS, build_action_summary, is_dangerous


# ─────────────────────────────────────────────────────────────
# 1. Every dangerous pattern MUST be detected
# ─────────────────────────────────────────────────────────────
class TestDangerDetection:
    @pytest.mark.parametrize(
        ("query", "expected_label"),
        [
            ("Please delete all orders from last month", "delete_orders"),
            ("delete order ORD-1003", "delete_orders"),
            ("Cancel the subscription for Oak Tree", "cancel_order"),
            ("issue a refund to the customer", "refund"),
            ("Refund my last invoice", "refund"),
            ("delete user nurse1", "delete_users"),
            ("remove that account from the system", "delete_users"),
            ("wipe the entire database", "wipe_data"),
            ("DROP all data immediately", "wipe_data"),
        ],
    )
    def test_dangerous_trigger(self, query, expected_label):
        should_alert, label = is_dangerous(query)
        assert should_alert is True
        assert label == expected_label

    # Case-insensitivity: matching runs on the lowercased query
    def test_matching_is_case_insensitive(self):
        assert is_dangerous("DELETE ALL ORDERS NOW")[0] is True

    # False-positive guard: innocent queries must NOT trip the gate
    @pytest.mark.parametrize(
        "query",
        [
            "What is the status of order ORD-1003?",
            "Explain how refunds work in the system",
            "how do I reset my password",
            "Show me a list of users",
            "Is the database healthy?",
        ],
    )
    def test_safe_queries_pass(self, query):
        should_alert, label = is_dangerous(query)
        assert should_alert is False
        assert label == ""

    def test_empty_query_is_safe(self):
        assert is_dangerous("") == (False, "")


# ─────────────────────────────────────────────────────────────
# 2. Action summary (what the approving human sees)
# ─────────────────────────────────────────────────────────────
class TestActionSummary:
    def test_summary_mentions_label_and_query(self):
        summary = build_action_summary("delete order ORD-1003", "delete_orders")
        assert "delete_orders" in summary
        assert "ORD-1003" in summary

    def test_all_patterns_have_a_human_readable_summary(self):
        for label in DANGEROUS_PATTERNS:
            summary = build_action_summary("some query", label)
            assert label in summary