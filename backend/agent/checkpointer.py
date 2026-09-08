"""
agent/checkpointer.py
─────────────────────
Sets up LangGraph's PostgreSQL checkpointer (AsyncPostgresSaver).

CONCEPT (Checkpointing — the foundation of HITL):
For human-in-the-loop to work, the graph's state must SURVIVE between
two separate HTTP requests:
  1. First request:  user asks a dangerous thing → graph PAUSES (interrupt).
  2. Later request:  human approves → graph RESUMES from the saved state.
Between those two calls the state must live in something durable. The
checkpointer saves a snapshot of AgentState to a table in PostgreSQL on
every node step, so we can resume any paused thread later.

WHY PostgreSQL (not memory)? A memory checkpointer is wiped on restart
and won't survive multiple workers. Postgres is the durable "Data Tier"
we built in Phase 3.5 — another reason we did 3.5/3.6 BEFORE Phase 6.

REUSABLE PATTERN:
    graph.compile(checkpointer=<saver>)          # enables pause/resume
    await graph.ainvoke(state,
        config={"configurable": {"thread_id": "..."}})

THREE SUBTLETIES in this file:
1. Schema DDL (CREATE INDEX CONCURRENTLY) cannot run inside a transaction
   block, so we apply migrations on a dedicated AUTOCOMMIT connection at
   import time (sync — before the async event loop exists).
2. The async pool (AsyncConnectionPool) CANNOT be created at import time
   because it needs a running event loop. So we create it lazily on first
   call to get_checkpointer().
3. The AsyncPostgresSaver wraps the lazy pool. graph.compile(checkpointer=...)
   receives the saver wrapper and creates the pool on first ainvoke().
"""

import psycopg
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from config import settings


# ── Step 1: Apply schema with an AUTOCOMMIT sync connection ─────
# Runs once at import time, before the event loop is up.
# CREATE INDEX CONCURRENTLY requires autocommit.
def _apply_schema(conninfo: str) -> None:
    """Create checkpoint tables on an autocommit connection."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS checkpoint_migrations (v INTEGER PRIMARY KEY)"
            )
            current = cur.execute(
                "SELECT MAX(v) FROM checkpoint_migrations"
            ).fetchone()
            current_version = current[0] if current else -1
            for v, migration in enumerate(PostgresSaver.MIGRATIONS):
                if v > current_version:
                    cur.execute(migration)
                    cur.execute(
                        "INSERT INTO checkpoint_migrations (v) VALUES (%s)", (v,)
                    )


# NOTE: _apply_schema is NOT called here (at import) — it's deferred into
# get_checkpointer() so the app doesn't crash when Postgres is down.


# ── Step 2: Lazy ASYNC pool + saver ────────────────────────────
# AsyncConnectionPool requires a running event loop. We can't create it at
# module import (no loop exists yet). Instead we use a lazy singleton:
# get_checkpointer() creates the pool+saver on first call (during a request,
# when the loop is running) and caches it for subsequent calls.
#
# IMPORTANT: the schema setup (_apply_schema) is ALSO deferred here on
# purpose. Running it at import time meant the whole app crashed if
# Postgres was temporarily down (User often stops the docker containers to
# free RAM). By deferring, `import main` always succeeds; the need for
# Postgres only surfaces when the graph (which requires a checkpointer to
# do HITL) is actually invoked.
_async_pool = None       # created lazily
_checkpointer = None     # created lazily
_schema_applied = False  # ensures we only apply schema once


def get_checkpointer() -> AsyncPostgresSaver:
    """Return (or create) the lazy async checkpointer singleton.

    On first call during a live request (event loop running), applies the
    schema (idempotent) and creates the AsyncConnectionPool +
    AsyncPostgresSaver. Subsequent calls return the same cached instance.
    """
    global _async_pool, _checkpointer, _schema_applied
    if _checkpointer is None:
        if not _schema_applied:
            _apply_schema(settings.database_url)
            _schema_applied = True
        _async_pool = AsyncConnectionPool(
            settings.database_url, min_size=1, max_size=8, open=None,
        )
        _checkpointer = AsyncPostgresSaver(_async_pool)
    return _checkpointer