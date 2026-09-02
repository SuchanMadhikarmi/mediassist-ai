# ============================================================
# backend/database.py
# SQLAlchemy engine + session factory — the CORE of the Data Tier.
#
# This is the single source of truth for "how do I talk to PostgreSQL".
# Every model imports Base from here; every route gets a DB session
# via the get_db() dependency.
#
# WHY a single file for this:
#   - engine = how to connect (URL + pool config). Created ONCE, reused.
#   - SessionLocal = a factory that makes short-lived sessions per request.
#   - Base = the declarative base every ORM model inherits from.
#   - get_db() = FastAPI dependency that hands a session to an endpoint
#     and ALWAYS closes it (even on error). This is the reusable pattern.
#
# GENERALIZABLE: this exact structure is copy-pasted into ~every SQLAlchemy
# FastAPI project. Change only the DATABASE_URL.
# ============================================================

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings

# --- Engine ---------------------------------------------------------------
# create_engine() builds the connection layer:
#   - database_url  : "postgresql://user:pass@host:port/db"
#   - pool_pre_ping : test the connection before handing it out (avoids
#                     using stale/broken DB connections after idle time)
#   - pool_size     : how many connections to keep open. Small for dev.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# --- Session factory ------------------------------------------------------
# SessionLocal is NOT a session itself — it's a factory (callable) that
# produces a new Session when called. We never share sessions across
# requests (that causes race conditions). One request = one session.
SessionLocal = sessionmaker(
    bind=engine,   # which engine to use
    autocommit=False,
    autoflush=False,
)


# --- Declarative base -----------------------------------------------------
# Every ORM model inherits from Base. SQLAlchemy uses it to track which
# classes map to tables so it can run CREATE TABLE (via metadata) or let
# Alembic introspect them for migrations.
class Base(DeclarativeBase):
    """DeclarativeBase gives our models metadata & the ability to be
    discovered by Alembic (autogenerate detection)."""
    pass


# --- FastAPI dependency ---------------------------------------------------
def get_db():
    """Yield a DB session to an endpoint, guaranteed to close.

    FastAPI 'yield' dependencies run their teardown AFTER the response
    is sent, so session.close() always executes — even if the endpoint
    raised an exception. This prevents connection leaks.

    Usage:
        def read_users(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
