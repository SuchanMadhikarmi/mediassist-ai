# Security Documentation — MediAssist AI

> **Why this document exists:** security is a university showcase AND a
> real engineering concern. This doc maps every control to where it is
> enforced in code — so an examiner can verify each claim quickly.

## 1. Authentication (AuthN) — JWT

- **Password storage:** **bcrypt** via passlib (`security/auth.py`).
  Passwords are salted one-way hashes; the DB never contains plaintext
  (verified by `backend/tests/test_auth.py` — same password hashes to
  two different values).
- **Login flow:** `POST /api/auth/login` returns two JWTs signed HS256
  with a secret from `.env`:
  - **access token** (short-lived, 60 min) — sent as
    `Authorization: Bearer <token>` on every request;
  - **refresh token** (long-lived) — exchanged via `/refresh` for a new
    access token without re-entering credentials.
- **Every protected route declares a security dependency** that FastAPI
  resolves *before* the route body executes: `get_current_user` /
  `get_current_user_db` decode + validate the JWT.

## 2. Authorization (AuthZ) — RBAC

Two layers, both enforced in code:

- **Function-level RBAC** — route dependencies (`require_role`,
  `require_admin`, `require_staff`). An end user calling
  `GET /api/users` gets **403** before any logic runs
  (see `Docs/PERMISSION_MATRIX.md` for the full matrix).
- **Data-level RBAC** — *row*-level visibility:
  - documents are filtered by `rbac_label`
    (`routes/documents.py:_visible_labels`);
  - the Qdrant payloads carry the label too, so **the chat agent only
    retrieves chunks that role may read**;
  - predictions: staff see all, end_user sees only their own rows
    (`routes/predictions.py`).

## 3. Input validation & injection guards

- **Pydantic schemas** validate every request body and turn invalid input
  into **HTTP 422** at the boundary (e.g. `age=200`, `job="wizard"` are
  rejected before reaching SQL or the ML model). Tested in
  `backend/tests/test_validation.py`.
- SQL is built through the **SQLAlchemy ORM** (parameterised queries) —
  no string-concatenated SQL anywhere.

## 4. PII redaction

- A regex-based redactor (`security/pii_redactor.py`) masks **emails,
  phone numbers, SSNs, credit-card numbers, zip+4** with auditable
  markers (`[EMAIL_REDACTED]`).
- Applied to retrieved document text at answer time
  (`routes/chat.py:351`) — **before** anything is sent to the LLM —
  so Personal Identifiable Information cannot flow to Ollama.
  Deterministic and unit-tested (`backend/tests/test_redactor.py`).

## 5. Human-in-the-loop (HITL) safety

- `agent/hitl.py` scans every chat request for dangerous intents
  (delete/cancel/refund/wipe) with keyword patterns.
- When matched, `check_hitl` **pauses the graph** via LangGraph
  `interrupt()`, persists the checkpoint to PostgreSQL, and the API
  returns **HTTP 409 needs_approval** with a `thread_id`. The action
  resumes only with a human decision (`/chat/resume`).
- A rejected action writes a **safe refusal** — generation is skipped
  entirely; the agent does not execute.
- The HITL gate runs **before** retrieval (moved to graph START after a
  live-test bug where dangerous queries with no matching docs bypassed
  it). Regression-tested in `backend/tests/test_hitl.py`.

## 6. Audit trail

- Supporting actions across the system write to `audit_log`
  (user_id, action, details, timestamp) — login, uploads, CRUD,
  predictions, HITL decisions.
- Queryable via `GET /api/audit` (staff only) and surfaced on the Admin
  dashboard. Every ML prediction is additionally logged to `predictions`.

## 7. Cache & tenant isolation

- The semantic cache is **namespaced by role** (`get_cache(user["role"])`)
  so a cached answer cannot leak across roles.
- Failed/fallback answers and tool-driven (live-data) answers are **not
  cached** — a cached failure is worse than a slow correct one.

## 8. Transport & deployment posture

- CORS allow-list is limited to the local Vite origins
  (`main.py`), credentials-bearing requests only.
- Secrets (`jwt_secret_key`, DB URL) live in `.env` (gitignored);
  `.env.example` documents the shape. **Production must rotate the JWT
  secret** (the default is development-only).
- **Known demo trade-offs** (examiner honesty): bcrypt rounds and token
  lifetimes are demo defaults; the API is not yet TLS-terminated — behind
  the Vite dev proxy in dev, behind a reverse proxy with HTTPS in prod.

## 9. Verified by tests

| Concern | Test |
|---------|------|
| Passwords never stored plaintext | `tests/test_auth.py` |
| PII always masked | `tests/test_redactor.py` |
| HITL gate catches every danger pattern; safe queries pass | `tests/test_hitl.py` |
| Malformed input → 422, never reaches logic | `tests/test_validation.py` |
| Circuit breaker fail-fast (resilience) | `tests/test_router.py` |
| Live golden set incl. HITL + RBAC 403s | `eval/run_eval.py` |