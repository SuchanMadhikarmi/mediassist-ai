# ============================================================
# backend/llmops/router.py
# A/B model routing + circuit breaker (Phase 7, Step 3).
#
# TWO reusable patterns live here:
#
#  1. A/B ROUTING  — pick WHICH model answers a query.
#  2. CIRCUIT BREAKER — decide whether a model is WORTH calling.
#
# WHY BOTH?
# We have two Ollama models with a classic trade-off:
#     qwen  (4b)  = fast, cheap, good for simple questions
#     llama (8b)  = smarter, slower, for complex questions
# But "smarter model" is useless if Ollama is FAILING. The circuit
# breaker is the resilience net that lets us fail FAST (and fall back
# to the other model) instead of hanging on a dead service.
#
# These two are THE reusable production patterns — the exact same
# ideas microservices use (Netflix Hystrix, resilience4j). Every
# distributed project eventually needs both. Learn the PATTERN.
# ============================================================

import time

from config import settings


# ════════════════════════════════════════════════════════════════
# 1. CIRCUIT BREAKER
# ════════════════════════════════════════════════════════════════
#
# CONCEPT (3 states, like a fuse):
#   CLOSED    — normal. Every call proceeds; count CONSECUTIVE failures.
#   OPEN      — too many failures. REFUSE immediately (fail fast), do NOT
#               attempt. Wait a cooldown before we'll even try again.
#   HALF-OPEN — after cooldown, allow ONE probe call. If it works we
#               CLOSE (healthy again); if it fails we OPEN again.
#
# Why "consecutive"? A single blip shouldn't open the circuit — only a
# sustained problem. So we reset the counter on ANY success.
class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = settings.breaker_failure_threshold,
        cooldown_seconds: float = settings.breaker_cooldown_seconds,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds

        self.state = "CLOSED"      # closed / open / half-open
        self.consecutive_failures = 0
        self.opened_at: float | None = None  # when we flipped to OPEN

    @property
    def allow_call(self) -> bool:
        """Should a call to this model be attempted right now?"""
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            # Is the cooldown up? If so, allow a single HALF-OPEN probe.
            if self.opened_at and (time.time() - self.opened_at) >= self.cooldown_seconds:
                self.state = "HALF_OPEN"
                return True
            return False           # still cooling down → refuse (fail fast)
        # HALF_OPEN: we already let one probe through (see below). Only one
        # call is allowed while half-open; any SECOND attempt is refused so
        # we don't flood the service while uncertain.
        return False

    def on_success(self):
        """A call succeeded → the model works → heal the circuit."""
        self.consecutive_failures = 0
        if self.state in ("HALF_OPEN", "OPEN"):
            self.state = "CLOSED"   # fully healthy again
            self.opened_at = None

    def on_failure(self):
        """A call failed → count it; if too many, open the circuit."""
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.state = "OPEN"
            self.opened_at = time.time()
            print(
                f"[router] {self.name} breaker OPEN after "
                f"{self.consecutive_failures} failures (cooldown "
                f"{self.cooldown_seconds}s)"
            )


# ════════════════════════════════════════════════════════════════
# 2. A/B ROUTING POLICY
# ════════════════════════════════════════════════════════════════
#
# CONCEPT (routing is a POLICY, not magic):
# Routing = a pure function:  query string → model name.
# Here the signal is naive "complexity" = a weighted length + novelty
# heuristic. In production the signal might be user tier, cost budget,
# latency SLO, or an LLM classifier. The SHAPE (function returning a
# resource name) is what you reuse.
def estimate_complexity(query: str) -> float:
    """Cheap, model-free heuristic for 'how hard is this question?'.

    Returns a float score; HIGHER = more complex. The heuristic:
      +1 per word          (long questions have more requirements)
      +5 if 'how do i' / 'explain' (asks for a PROCEDURE, not a fact)
      +3 if 'compare'/'why'/'difference'  (needs reasoning, not lookup)

    NOTE this is deliberately crude (we optimise for speed + zero LLM
    cost). Swap for a smarter classifier later without changing callers
    — that's the point of hiding the policy behind this function.
    """
    q = query.strip().lower()
    score = float(len(q.split()))          # word count
    if any(phrase in q for phrase in ("how do i", "how do you", "explain")):
        score += 5
    if any(word in q for word in ("compare", "difference", "why", "steps", "troubleshoot")):
        score += 3
    return score


def choose_model(query: str) -> str:
    """A/B route a query to the fast model or the smart model.

    Signal = estimated complexity. Above the threshold → smart model.
    The threshold is configurable (routing_complexity_threshold) so we
    can tune cost/latency without touching code.
    """
    complexity = estimate_complexity(query)
    if complexity > settings.routing_complexity_threshold:
        return settings.fallback_model      # smart (llama3.1:8b)
    return settings.primary_model           # fast  (qwen3.5:4b)


# ════════════════════════════════════════════════════════════════
# 3. THE ROUTER: combines both patterns per model
# ════════════════════════════════════════════════════════════════
#
# One breaker PER MODEL (not one global). A failure on qwen opens only
# qwen's breaker → we can still fall back to llama. This is the crux:
# the breaker protects a *resource*, and each resource gets its own.
class Router:
    def __init__(self):
        self.breakers: dict[str, CircuitBreaker] = {}

    def _breaker(self, model: str) -> CircuitBreaker:
        if model not in self.breakers:
            self.breakers[model] = CircuitBreaker(name=model)
        return self.breakers[model]

    def pick_model(self, query: str) -> str:
        """Choose the best model for `query`, but never one that is
        currently tripped (OPEN / HALF_OPEN with no probe slot).

        FALLBACK LOGIC (the resilience payoff):
        1. Ask A/B routing for the ideal model.
        2. If that one's circuit is healthy → use it.
        3. If it's tripped, fall back to the OTHER model (if healthy).
        4. If BOTH are tripped → return the ideal anyway; the breaker &
           the caller's own retry/failure handling will deal with it
           (fail fast, and POP the circuit problem to the logs).
        """
        ideal = choose_model(query)
        other = settings.fallback_model if ideal == settings.primary_model else settings.primary_model

        if self._breaker(ideal).allow_call:
            return ideal
        if self._breaker(other).allow_call:
            print(f"[router] {ideal} tripped → falling back to {other}")
            return other
        print(f"[router] both models tripped → returning ideal ({ideal}) anyway")
        return ideal

    # ── Feedback hooks: the caller MUST report the outcome so the
    #    breaker can track health. This is the whole point — a breaker
    #    with no feedback is just a guess. ──
    def on_success(self, model: str):
        self._breaker(model).on_success()

    def on_failure(self, model: str):
        self._breaker(model).on_failure()


# Module-level singleton (like get_cache / get_crag_graph). Shared across
# the app so failure counts are accumulated app-wide, not per-request.
_router: Router | None = None


def get_router() -> Router:
    global _router
    if _router is None:
        _router = Router()
    return _router


# ════════════════════════════════════════════════════════════════
# Standalone self-test:  python llmops/router.py
# Shows CLOSED → OPEN → (cooldown) → HALF_OPEN → CLOSED, plus A/B picks.
# ════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # Circuit breaker demonstrations
    cb = CircuitBreaker(name="demo", failure_threshold=3, cooldown_seconds=0.1)

    print(f"initial state={cb.state} allow={cb.allow_call}")
    cb.on_failure(); cb.on_failure()
    print(f"after 2 fails state={cb.state} allow={cb.allow_call} (still closed/failing)")
    cb.on_failure()
    print(f"after 3 fails state={cb.state} allow={cb.allow_call} (OPEN → refuse)")

    cb.on_success()
    print(f"after success state={cb.state} allow={cb.allow_call} (heals)")

    # Cooldown → HALF_OPEN probe
    cb2 = CircuitBreaker(name="demo2", failure_threshold=1, cooldown_seconds=0.0)
    cb2.on_failure()
    print(f"demo2 OPEN (cooldown=0) → next call allows HALF_OPEN probe: {cb2.allow_call}")
    cb2.on_success()
    print(f"probe succeeded → state={cb2.state} (CLOSED again)")

    # A/B routing demo
    print("\n— A/B routing —")
    for q in [
        "hi",                                    # simple → qwen
        "What does error 4012 mean?",            # moderate
        "How do I troubleshoot a failed server order and why does it retry?",  # complex → llama
    ]:
        print(f"  complexity={estimate_complexity(q):7.1f}  model={choose_model(q)!r:<14}  {q}")
