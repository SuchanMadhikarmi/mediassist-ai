# ============================================================
# backend/tests/test_router.py
# Deterministic tests for the A/B router + circuit breaker
# (Phase 7, Step 3) and the resilience net in general.
#
# WHY THESE TESTS EXIST (the Phase 9 lesson):
# A circuit breaker is PURE LOGIC — no Ollama involved. It must be
# provably correct on every PR, headless, in seconds. If a future
# change to the breaker forgets the HALF_OPEN probe slot, these tests
# catch it BEFORE anything reaches a real LLM.
#
# This file is the "CI" half of Phase 9: cheap, fast, deterministic.
# ============================================================

import time

import pytest

from llmops.router import (
    CircuitBreaker,
    Router,
    choose_model,
    estimate_complexity,
    get_router,
)
from config import settings


# ─────────────────────────────────────────────────────────────
# 1. Complexity heuristic + A/B choice (pure functions)
# ─────────────────────────────────────────────────────────────
class TestComplexity:
    def test_simple_query_is_cheap(self):
        score = estimate_complexity("hi")
        assert score <= settings.routing_complexity_threshold
        assert choose_model("hi") == settings.primary_model  # fast model

    def test_procedural_query_is_complex(self):
        query = "How do I troubleshoot a failed server order and why does it keep retrying?"
        score = estimate_complexity(query)
        assert score > settings.routing_complexity_threshold
        assert choose_model(query) == settings.fallback_model  # smart model

    def test_reasoning_keywords_bump_score(self):
        assert estimate_complexity("why is this order delayed") > estimate_complexity("hi")

    def test_empty_query_exists(self):
        # Should not crash on empty input — partition edge.
        assert estimate_complexity("") == 0.0


# ─────────────────────────────────────────────────────────────
# 2. Circuit breaker state machine (CLOSED → OPEN → HALF_OPEN → CLOSED)
# ─────────────────────────────────────────────────────────────
class TestCircuitBreaker:
    def test_closed_allows_calls(self):
        cb = CircuitBreaker(name="t", failure_threshold=3)
        assert cb.state == "CLOSED"
        assert cb.allow_call is True

    def test_failures_below_threshold_keep_closed(self):
        cb = CircuitBreaker(name="t", failure_threshold=3)
        cb.on_failure()
        cb.on_failure()
        assert cb.state == "CLOSED"
        assert cb.allow_call is True  # single blip must NOT trip the circuit

    def test_threshold_open_blocks_calls(self):
        cb = CircuitBreaker(name="t", failure_threshold=3)
        for _ in range(3):
            cb.on_failure()
        assert cb.state == "OPEN"
        assert cb.allow_call is False  # fail fast — refuse the call

    def test_recovery_to_closed_on_success(self):
        cb = CircuitBreaker(name="t", failure_threshold=1)
        cb.on_failure()
        assert cb.state == "OPEN"
        cb.on_success()  # even an OPEN breaker heals on a reported success
        assert cb.state == "CLOSED"
        assert cb.consecutive_failures == 0

    def test_cooldown_triggers_single_half_open_probe(self):
        # failure_threshold=1 + cooldown 0 → after failure, next allow_call
        # should flip OPEN→HALF_OPEN and grant exactly ONE probe slot.
        cb = CircuitBreaker(name="t", failure_threshold=1, cooldown_seconds=0.0)
        cb.on_failure()
        assert cb.state == "OPEN"

        assert cb.allow_call is True   # cooldown up → one HALF_OPEN probe
        assert cb.state == "HALF_OPEN"
        assert cb.allow_call is False   # second attempt while half-open refused

    def test_pending_cooldown_still_refuses(self):
        cb = CircuitBreaker(name="t", failure_threshold=1, cooldown_seconds=30)
        cb.on_failure()
        assert cb.state == "OPEN"
        # cooldown 30s has NOT elapsed → still refused, no probe.
        assert cb.allow_call is False
        assert cb.state == "OPEN"  # did not flip to HALF_OPEN early

    def test_half_open_success_heals(self):
        cb = CircuitBreaker(name="t", failure_threshold=1, cooldown_seconds=0.0)
        cb.on_failure()
        cb.allow_call  # → HALF_OPEN
        cb.on_success()
        assert cb.state == "CLOSED"
        assert cb.allow_call is True


# ─────────────────────────────────────────────────────────────
# 3. Router: per-model breakers + fallback policy
# ─────────────────────────────────────────────────────────────
class TestRouter:
    def test_healthy_router_returns_ideal(self):
        r = Router()
        assert r.pick_model("hi") == settings.primary_model

    def test_tripped_ideal_falls_back_to_other(self):
        r = Router()
        ideal = settings.fallback_model
        # Simulate the smart model failing repeatedly → its breaker opens.
        for _ in range(settings.breaker_failure_threshold):
            r.on_failure(ideal)
        assert r.pick_model(ideal) == settings.primary_model  # fell back

    def test_both_tripped_returns_ideal_anyway(self):
        r = Router()
        for model in (settings.primary_model, settings.fallback_model):
            for _ in range(settings.breaker_failure_threshold):
                r.on_failure(model)
        # Both open → policy says return ideal; caller handles failure.
        assert r.pick_model("hi") == settings.primary_model

    def test_breaker_is_per_model(self):
        r = Router()
        # Fail ONLY the smart model.
        for _ in range(settings.breaker_failure_threshold):
            r.on_failure(settings.fallback_model)
        # The primary model's breaker must still be untouched.
        assert r._breaker(settings.primary_model).state == "CLOSED"

    def test_router_is_a_singleton(self):
        assert get_router() is get_router()