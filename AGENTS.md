# MediAssist AI — Project Context

## Project Name
**MediAssist AI** — A Multi-Tier AI-Powered Clinical Support System with RAG-Based Document Query and Machine Learning Prediction

## User Goal
This is a **learning-first** project. The user (Suchan) is building a university portfolio project to master full-stack development, AI engineering, and machine learning. Every line of code must be **explained gradually** — no vibe coding. The user wants to understand the WHY behind every decision so they can build independent projects and explain everything in a viva.

## The Problem We're Solving
A company that sells WebPOS/ERP systems to clinics and hospitals needs:
1. **An AI assistant** — staff ask questions about error codes/manuals, upload PDF contracts, get cited, secure, streaming answers
2. **An ML prediction system** — predict whether clients will subscribe to premium services based on interaction patterns

## Tech Stack (100% Free & Open Source)
- **Frontend:** React (Vite) + Tailwind CSS
- **Backend:** FastAPI (Python 3.12)
- **Vector DB:** Qdrant (Docker) — document embeddings for RAG
- **RDBMS:** PostgreSQL — users, predictions, audit logs, model registry
- **LLM:** Ollama (qwen3.5:4b + llama3.1:8b) — for RAG chatbot
- **Embeddings:** Nomic Embed (768-dim) — via sentence-transformers
- **ML Models:** XGBoost + Logistic Regression — trained on Bank Marketing dataset
- **Agent:** LangGraph (CRAG pattern)
- **Observability:** Arize Phoenix (Docker)
- **Infra:** Docker Compose

## University Requirements (Track B)
- 3-tier architecture (Presentation → Application → Data)
- RDBMS compulsory (PostgreSQL)
- 3 user roles with RBAC: Admin / Expert / End User
- CRUD on 3+ entities
- Search, filter, pagination
- Reports/dashboard with model usage stats
- File upload with validation
- ML: baseline + 2 models compared, precision/recall/F1/confusion matrix
- Model saved as artifact (.pkl), inference endpoint with confidence
- Every prediction logged in DB (input, output, confidence, model_version, user, timestamp)
- Git repo with regular commits
- Client-side validation, async requests, responsive layout

## Key Architecture Decisions
- **Hybrid search:** Dense (Nomic) + Sparse (BM25) fused with RRF
- **Re-ranking:** Cross-Encoder on top 20 → top 5
- **CRAG:** Self-correcting retrieval (grade docs, retry if bad)
- **HITL:** Graph pauses for admin/expert approval on dangerous actions
- **Security:** JWT + PII redaction middleware + RBAC labels in Qdrant
- **LLMOps:** Semantic cache (FAISS), A/B routing, circuit breaker, Phoenix tracing
- **ML Pipeline:** Bank Marketing dataset → Logistic Regression (baseline) + XGBoost → joblib artifacts → inference endpoint → PostgreSQL prediction log

## Current Status
- **READ `Docs/PROGRESS.md` FIRST every session** — it is the authoritative
  continuation log: where we are, what's left, and the exact teaching methodology.
- **Phase 0: COMPLETED** — Architecture docs written
- **Phase 1: COMPLETED** — Infrastructure running
- **Phase 2: COMPLETED** — Backend foundation running
- **Phase 3: COMPLETED** — Enterprise Security (JWT + PII + RBAC)
- **Phase 4: COMPLETED** — Ingestion (PDF → Qdrant)
- **Phase 5: COMPLETED** — Retrieval (Hybrid Search + RRF + re-ranking)
- **Phase 3.5: COMPLETED** — PostgreSQL + SQLAlchemy + ORM Models (5→6 tables incl. erp_orders). Alembic migrations applied, seed script run.
- **Phase 3.6: COMPLETED** — 3 Roles (admin/expert/end_user) + DB-backed registration/login/refresh + CRUD on users/documents/predictions/audit + search/filter/pagination + data-level RBAC. Role enum admin/expert/end_user (+viewer alias). Chat now requires JWT.
- **Phase 6: COMPLETED** — LangGraph CRAG fully done: Step A (ERP mock tool + sufficiency grading), Step B (faithfulness grading), Step C (HITL with Postgres checkpointing via AsyncPostgresSaver + /chat/resume endpoint). Verified with stubbed LLM + API tests. Live LLM end-to-end test still pending (Ollama down).
- **Phase 6.5: COMPLETED** — `backend/ml/` (data_loader, preprocessing, train, predictor). Real UCI `bank-full.csv` (45,211 rows, 88/12 imbalance). Pipeline: stratified 70/15/15 split → preprocessor fitted on TRAIN only → SMOTE on TRAIN only → LR (AUC 0.901) + XGBoost (AUC 0.9236, BEST). Artifacts in `backend/ml/models/`. BOTH models registered in `model_registry` (xgboost active). Detail in `Docs/PROGRESS.md` §5.6.
- **Phase 6.6: COMPLETED** — `POST /api/predict` (JWT) + Pydantic input validation (422 gate) + dual logging (`predictions` + `audit_log`), live end-to-end verified (valid 200 → logged; invalid 422 → not logged; lazy model load = 458ms→39ms). Detail in `Docs/PROGRESS.md` §5.6.
- **Phase 7.5: COMPLETED** — `GET /api/stats` (staff-only) aggregation endpoint: totals (predictions/users/documents/orders/models), GROUP BY breakdowns (users-by-role, predictions-by-model, predictions-by-output, audit-by-action), quality metrics (avg_confidence, avg_inference_time_ms, positive_rate), model registry with metrics, recent activity (audit JOIN user), 7-day prediction trend (`date_trunc`). Live-verified: real numbers correct, end_user → 403, auto-traced in Phoenix. Data feed for Phase 8 dashboards. Detail in `Docs/PROGRESS.md` §5.8.
- **Phase 8: COMPLETED** — Full React frontend in `frontend/` (Vite 6 + React 18 + Tailwind 3.4, zero UI libs). Hash router + role→VIEWS RBAC map in `App.jsx`; own libs: `api.js` (fetch+JWT+401→login), `auth.js`, `sse.js` (POST-SSE via fetch ReadableStream — EventSource can't POST), `validation.js` (Pydantic parity). Screens: 3 role dashboards (AdminDashboard from `/api/stats` w/ CSS bar charts + model cards + activity + trend; UsersPane CRUD; DocsPane PDF upload; AuditPane; PredictionsTable w/ staff review + search/pagination; PredictForecast 16-field ML form; ChatWindow w/ live token streaming + citations + HITL approval card). Vite proxy `/api`,`/chat`,`/ingest`,`/health`→:8000. Verified: build + proxy login/stats + SSE first-frame through proxy. Open http://localhost:5173 (admin/admin123, expert1/expert123, nurse1/nurse123). Detail in `Docs/PROGRESS.md` §5.9.
- **Phase 9: COMPLETED** — Eval CI/CD. CI gate = `backend/tests/` **67 headless pytest checks** (router/breaker, HITL danger, Pydantic 422-gate, SSE framing, password hashing, PII redaction) run via `.venv/bin/python -m pytest` from `backend/` (pytest 8.3.4 in requirements.txt). Quality gate = `backend/eval/` golden-set live eval: `.venv/bin/python -m eval.run_eval` logs in as admin, plays 6 cases (RAG/cache/fallback/tool/HITL approve/HITL reject) against the LIVE stack, scores 5/5 hard PASS + `judge.py` LLM-as-judge (5/5 grounded) + writes `data/eval_report.json` (exit 0 only if all hard cases pass; the ERP `tool` case is `soft` — corpus has only 2 points so it legitimately warns). `.github/workflows/ci.yml`: backend-tests + frontend-build on every push/PR; `live-eval` job is manual + self-hosted. Detail in `Docs/PROGRESS.md` §5.10.
- **Chat endpoints paths:** `/chat` (JSON), `/chat/stream` (SSE tokens), `/chat/resume` (HITL approve/reject). NOT `/api/chat` (old PROGRESS curl examples are outdated).
- **Ollama is UP** (restarted for Phase 7 live tests; qwen + nomic loaded). As of 2026-09-06 (night): **postgres + qdrant UP, uvicorn RUNNING on port 8000** (detached via setsid), **phoenix UP** (needed for Phase 7 Step 4), **Vite dev server RUNNING on :5173** (detached from `frontend/`), swap empty.
- **Phase 4-5: COMPLETED** (done earlier: ingestion + hybrid retrieval)

## Phase Plan (14 phases total)
```
Phase 1:   Infrastructure (Docker Compose)           ✅ DONE
Phase 2:   Backend Foundation (FastAPI)              ✅ DONE
Phase 3:   Enterprise Security (JWT + PII + RBAC)    ✅ DONE
Phase 3.5: PostgreSQL + SQLAlchemy + ORM Models      ✅ DONE
Phase 3.6: 3 Roles + Registration + CRUD             ✅ DONE
Phase 4:   Ingestion (PDF → Qdrant)                  ✅ DONE
Phase 5:   Retrieval (Hybrid Search + RRF)           ✅ DONE
Phase 6:   Agentic Workflows (LangGraph CRAG)        ✅ DONE
Phase 6.5: ML Training (2 models, evaluation)        ✅ DONE (trained + registered)
Phase 6.6: ML Inference Endpoint + Prediction Logging ✅ DONE (live-verified)
Phase 7:   LLMOps (Cache + Streaming + Router + Phoenix) ✅ DONE
Phase 7.5: Reports + Dashboard Stats                  ✅ DONE (GET /api/stats)
Phase 8:   React Frontend (3 role-based dashboards)   ✅ DONE (frontend/)
Phase 9:   Eval CI/CD                                 ✅ DONE (via `backend/tests/` pytest 67 checks + `backend/eval/` golden-set + `judge.py` LLM-as-judge + `.github/workflows/ci.yml`)
Phase 10:  Documentation + Permission Matrix          ✅ DONE (README.md + `Docs/PERMISSION_MATRIX.md` + `Docs/ML_EVALUATION.md` + `Docs/SECURITY.md` + `Docs/diagrams/*.mermaid` + ARCHITECTURE.md index). **ALL 10 PHASES COMPLETE.**
```

## RESOURCE CONSTRAINT — CRITICAL (audited 2026-08-27)
- **15GB total RAM, ~13GB used** by: Win11 VM (4.8GB), Brave (~2.5GB), VS Code (~1.5GB), Ollama model, opencode
- **Swap is 100% full (4GB)** — system must NOT swap-thrash or it freezes
- **Known Ollama models already downloaded** in `~/.ollama`:
  - `qwen3.5:4b` (3.4GB) — primary model, supports tools + thinking
  - `llama3.1:8b` (4.9GB) — fallback model, supports tools
  - `nomic-embed-text` (137M, 768-dim) — embedding model
- **RULES:**
  - Run only ONE large LLM in RAM at a time when VM is on
  - Ollama API = `http://localhost:11434` (standard)
  - Qdrant API = `http://localhost:6333` (existing container)
  - PostgreSQL = `http://localhost:5432` (container, added Phase 3.5)
  - If RAM pressure appears, tell the user to close the Win11 VM first
- **Disk:** 32GB free, 82% full — keep model downloads/images lean

## Build Order
```
Phase 1-3:   DONE (Infrastructure + Backend + Security)
Phase 3.5-3.6: DONE (PostgreSQL + 3 Roles + CRUD)
Phase 4-5:   DONE (Ingestion + Retrieval)
Phase 6:     LangGraph (CRAG + Tools + HITL)  ✅ DONE
Phase 6.5:   ML Training (2 models, eval, artifacts)  ✅ DONE (predictor + registry done)
Phase 6.6:   ML Inference Endpoint + Prediction Logging  ✅ DONE (live-verified)
Phase 7:     LLMOps (Cache + Streaming + Router + Phoenix)  ✅ DONE (Steps 1-4)
Phase 7.5:   Reports + Dashboard Stats  ✅ DONE (GET /api/stats)
Phase 8:     React Frontend (3 role-based dashboards)  ✅ DONE (frontend/)
Phase 9:     Eval CI/CD  ✅ DONE (pytest 67 + golden-set eval + ci.yml)
Phase 10:    Documentation  ✅ DONE (README + permission/RBAC + ML eval + security + mermaid diagrams) — ALL PHASES COMPLETE
```

## Current Running State (as of 2026-08-27)
- Phoenix: docker container `phoenix`, healthy, UI at http://localhost:6006
- Qdrant: standalone container `qdrant`, at http://localhost:6333
- Ollama: bare-metal, at http://localhost:11434 (models: qwen3.5:4b, llama3.1:8b, nomic-embed-text)
- PostgreSQL: docker container `postgres`, at http://localhost:5432 (db medassist, user medassist)
- FastAPI: run via `uvicorn main:app --port 8000` from `backend/` (venv active)
- `.env` + `.env.example` exist; `docker-compose.yml` manages phoenix + postgres
- NOTE: `/health` pings ollama with a 3s timeout which can make the health check slow (~10s+). Not a server fault — the fast auth/CRUD endpoints respond immediately.

## Teaching Philosophy (REUSABLE TEMPLATE — the user's core goal)
The user's #1 goal: learn concepts+code so deeply that building ANY future client project feels "finger-click" easy. Every phase MUST be explained as a GENERALIZABLE pattern, not a one-off hack.

### The "Boring 80%" Reusable Stack (build once, reuse everywhere)
This is the boring-but-essential foundation present in ~every client project:
1. **Data tier** — PostgreSQL + SQLAlchemy ORM (+ Alembic migrations)
2. **API layer** — FastAPI routers, Pydantic schemas, dependencies
3. **AuthN** — JWT (access/refresh tokens), password hashing (bcrypt)
4. **AuthZ/RBAC** — role-based access control dependency factory
5. **CRUD** — generic Create/Read/Update/Delete per entity + search/filter/pagination
6. **Observability** — request logging, audit trail

When building a NEW client project: copy this foundation, rename entities, swap business logic. This is WHY we do Phase 3.5/3.6 BEFORE finishing the AI-specific Phase 6 — the DB/RBAC/CRUD layer is transferable to every project, AI or not.

### Why Phase 3.5/3.6 before finishing Phase 6
Phase 6 (LangGraph HITL + tools) DEPENDS on PostgreSQL:
- HITL checkpointing persists to the DB
- ERP mock tool queries PostgreSQL for live data
Building Phase 6 without the DB means building on sand and redoing it. So:
- Do the reusable data/CRUD/auth foundation first (3.5 + 3.6)
- Then finish Phase 6 cleanly on top of a real database

### Reusable Principles (reaffirm on every phase)
- Explain concept → WHY → implement → verify → link to bigger picture
- Every feature = a pattern you'll re-use, so learn the PATTERN, not the paste
- Never skip ahead; each phase builds on the previous

## Teaching Approach
- Explain concept → implement → verify → link back to bigger picture
- Never write code without explaining WHY
- Never skip to next phase until current is solid
- Run lint/typecheck after every change
- Never commit unless explicitly asked
- Project directory: `/home/suchan/personal/projFDE`

## Important Files
- `AGENTS.md` — This file (project context for AI agents)
- `Docs/ARCHITECTURE.md` — Full system design
- `Docs/LEARNING_COMPANION.md` — Concept explanations
- `Docs/IMPLEMENTATION_PLAN.md` — Step-by-step build plan
- `.env` + `.env.example` — Environment variables
- `docker-compose.yml` — Infrastructure definition
- `backend/` — FastAPI application
- `frontend/` — React application (Phase 8)
