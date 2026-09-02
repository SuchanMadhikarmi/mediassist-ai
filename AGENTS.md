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
- **Phase 0: COMPLETED** — Architecture docs written
- **Phase 1: COMPLETED** — Infrastructure running
- **Phase 2: COMPLETED** — Backend foundation running
- **Phase 3: COMPLETED** — Enterprise Security (JWT + PII + RBAC)
- **Phase 4: COMPLETED** — Ingestion (PDF → Qdrant)
- **Phase 5: COMPLETED** — Retrieval (Hybrid Search + RRF + re-ranking)
- **Phase 3.5: COMPLETED** — PostgreSQL + SQLAlchemy + ORM Models (5 tables: users, documents, predictions, audit_log, model_registry). Alembic migration applied, seed script run, /health shows postgres:up
- **Phase 3.6: COMPLETED** — 3 Roles (admin/expert/end_user) + DB-backed registration/login/refresh + CRUD on users/documents/predictions/audit + search/filter/pagination + data-level RBAC. Endpoints under /api/auth/*, /api/users, /api/documents, /api/predictions, /api/audit
- **Phase 6: NEXT (finish remaining ~60%)** — LangGraph TOOLS + HITL + faithfulness grading, now on top of real PostgreSQL
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
Phase 6:   Agentic Workflows (LangGraph CRAG)        ⬜ NEXT
Phase 6.5: ML Training (2 models, evaluation)        🆕
Phase 6.6: ML Inference Endpoint + Prediction Logging 🆕
Phase 7:   LLMOps (Cache + Streaming + Phoenix)       ⬜
Phase 7.5: Reports + Dashboard Stats                  🆕
Phase 8:   React Frontend (3 role-based dashboards)   ⬜
Phase 9:   Eval CI/CD                                 ⬜
Phase 10:  Documentation + Permission Matrix          ⬜
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
Phase 6:     LangGraph (CRAG + Tools + HITL)  ← NEXT (finish tools/HITL/faithfulness)
Phase 6.5-6.6: ML Training + Inference
Phase 7:     LLMOps (Cache + Streaming + Phoenix)
Phase 7.5:   Reports + Dashboard
Phase 8:     React Frontend
Phase 9:     Eval CI/CD
Phase 10:    Documentation
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
