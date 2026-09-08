# ============================================================
# backend/llmops/telemetry.py
# OpenTelemetry tracing → Arize Phoenix (Phase 7, Step 4).
#
# CONCEPT — the three pillars of observability (reuse everywhere):
#   Logs    = "something happened"            (our [llm] print() lines)
#   Metrics = "how many / how much"           (request counts, average latency)
#   Traces  = "the PATH one request took through the whole system"
#
# CONCEPT — span vs trace:
#   Span   = ONE unit of work (an endpoint call, an HTTP request to Ollama,
#            a retrieval). Carries: name, start/end time, status, and a dict
#            of attributes (key=value metadata like model=llama3.1:8b).
#   Trace  = the TREE of spans for a single request. The ROOT span is the
#            entry point (our FastAPI endpoint); CHILD spans are each piece
#            of work it triggered. Phoenix's UI draws this tree with per-span
#            timings — precisely how we answer "why was that 6 seconds?"
#
# CONCEPT — how a trace actually gets from code to Phoenix (the plumbing):
#
#   code ──spans──> OpenTelemetry SDK ──BatchSpanProcessor──> OTLP HTTP exporter
#                    (this module wires it)                     │
#                                                               ▼
#                                              Phoenix container
#                                              POST /v1/traces (localhost:6006)
#
# We wire the SDK BY HAND (Provider + Processor + Exporter) instead of using
# arize-phoenix-otel's register() convenience. WHY: register() hides exactly
# these three steps; understanding them means you can wire ANY collector
# (Phoenix, Jaeger, Tempo, Datadog...) from memory. It also keeps our pinned
# otel 1.29.0 stack untouched instead of force-upgrading to 1.44 (the dry-run
# showed register() would upgrade the SDK and risk breaking our 0.50b0
# instrumentors). The manual wiring is ~10 lines and does the same job.
#
# Two kinds of spans come out of this file:
#   1. AUTO — FastAPI endpoint spans + httpx child spans (Ollama/Qdrant
#      calls) appear with ZERO code in our routes. Instrumentation is a
#      one-line opt-in per library.
#   2. MANUAL — business-meaning spans we place where it matters (see
#      chat_span_ctx() used in routes/chat.py).
# ============================================================

import contextlib

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from config import settings

# OpenInference semantic-convention attribute NAMES (exact strings, chosen
# over installing the openinference-semantic-conventions package so we stay
# lean). Phoenix recognizes them and renders these spans as its special
# LLM/agent panels instead of generic spans.
OIF_SPAN_KIND = "openinference.span.kind"
OIF_INPUT = "openinference.input.value"
OIF_OUTPUT = "openinference.output.value"
OIF_KIND_CHAIN = "CHAIN"   # a chain/agent step in the trace

_configured = False


# ── Public API ───────────────────────────────────────────────────
def configure_telemetry(app) -> None:
    """IDEMPOTENT startup hook: build the SDK pipeline + auto-instrument.

    Called ONCE from main.py after `app` exists. Anything after this
    point in the process automatically produces spans.

    The 4 moving parts (learn these — they are EVERY tracing setup):
      1. TracerProvider  — the SDK's root object for the process.
      2. SpanProcessor   — the scheduler: batches finished spans.
      3. Exporter        — ships batches to the collector (Phoenix).
      4. Instrumentation — hooks into libraries so spans happen for free.
    """
    global _configured
    if _configured:
        return

    # 1. Provider — one per process. Set() makes it the SDK global default
    #    so ANY library using the OTel API lands in our pipeline.
    #    Resource = attributes describing the SERVICE that produced spans.
    #    Phoenix reads `openinference.project.name` and files every span
    #    from this process under that project in its UI (clean separation).
    provider = TracerProvider(
        resource=Resource.create(
            {"openinference.project.name": "mediassist"}
        )
    )
    trace.set_tracer_provider(provider)

    # 3 + 2. Exporter → Phoenix's OTLP/HTTP receiver (single-port container
    #    mode: the UI port 6006 ALSO serves /v1/traces). BatchSpanProcessor
    #    sits in front: it buffers spans and exports them in batches, so we
    #    get ONE HTTP call per N spans instead of N calls for N spans.
    exporter = OTLPSpanExporter(endpoint=f"{settings.phoenix_url}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))

    # 4. Auto-instrumentation (the runtime opt-in per dependency).
    #    FastAPI: each endpoint call becomes a ROOT span (name = "POST /chat").
    #    httpx:   each outgoing HTTP call (→ Ollama, → Qdrant) becomes a child.
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()

    _configured = True
    print(f"[telemetry] OTel active → exported to {settings.phoenix_url}/v1/traces")


def get_tracer() -> trace.Tracer:
    """Return the app tracer, bound to the provider from configure_telemetry.

    IMPORTANT (otel ordering trap): call this AT REQUEST TIME, not at module
    import. A tracer obtained before configure_telemetry() ran would be bound
    to the SDK's default no-op provider and emit NOTHING. Calling lazily
    guarantees it grabs the real provider every time.
    """
    return trace.get_tracer("mediassist", "0.1.0")


@contextlib.contextmanager
def chat_span_ctx(query: str, role: str):
    """MANUAL span wrapping one CRAG graph run — the business context that
    auto-instrumentation cannot see.

    Opens a child span under the current (FastAPI) root span, pre-fills it
    with attributes that make the trace readable in Phoenix, yields so the
    caller fills in outcome attributes, then closes it.

    USAGE:
        with chat_span_ctx(query, role) as span:
            result = await graph.ainvoke(state, config)
            span.set_attribute("chat.answer_length", len(result.get("answer", "")))
    """
    span = get_tracer().start_span(
        "chat.crag_run",
        attributes={
            OIF_SPAN_KIND: OIF_KIND_CHAIN,   # Phoenix renders as an agent step
            OIF_INPUT: query,
            "chat.role": role,
            "chat.query_length": len(query),
        },
    )
    try:
        yield span
    except Exception as exc:
        span.record_exception(exc)   # failure shows ON the span (not lost)
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
        raise
    finally:
        span.end()