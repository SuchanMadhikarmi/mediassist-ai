# MediAssist AI

> **Everything in this repo is a learning artifact** — every layer is explained in `Docs/`
> with the *why* behind each decision. Built to show how a real AI product ships end to end:
> retrieval, generation, security, deployment, monitoring, and human oversight.

A **multi-tier, AI-powered clinical support platform** built 100% on free
and open-source software. Staff ask questions about product manuals and
error codes in plain English, get **cited, streamed answers** powered by
RAG + a self-correcting LangGraph agent with human-in-the-loop safety. A
separate **ML service** predicts whether a client will subscribe to a
premium service, with every prediction logged for the audit trail.

Built as a university **Track B** portfolio project — the "boring 80%"
(reusable PostgreSQL + RBAC + CRUD foundation) plus the AI 20%.

---

## What this project teaches you

This is a **Forward Deployed Engineering (FDE) starter kit**: not just a model,
but the entire system around it that a client would actually use in production.

| If you're a… | You'll learn how to… |
|---|---|
| **AI/ML engineer** | build RAG + CRAG, cite sources, grade retrieval & faithfulness, log every prediction |
| **Full-stack dev** | wire React → FastAPI → PostgreSQL/Qdrant/RBAC, stream SSE tokens to the browser |
| **DevOps engineer** | containerize with Compose (Postgres, Qdrant, Phoenix), add CI/CD, trace every request |
| **Student** | assemble a complete, viva-ready portfolio with 3-tier architecture + RDBMS + ML baseline |

**Key concepts you'll actually be able to explain:** hybrid search + RRF,
cross-encoder re-ranking, corrective RAG, human-in-the-loop checkpoints,
JWT + data-level RBAC, SMOTE + class-imbalance handling, LLM-as-a-judge,
semantic caching, circuit breakers, and OpenTelemetry tracing.

---

## Highlights

- **3-tier architecture** — React (Vite) → FastAPI → PostgreSQL + Qdrant
- **3 roles with RBAC** — Admin / Expert / End User, enforced in every route
- **RAG chatbot** — hybrid search (dense + BM25, RRF fusion), cross-encoder
  re-ranking, cited answers over SSE (live token streaming)
- **CRAG agent (LangGraph)** — retrieval grading, faithfulness grading with
  retry, self-correction, and **HITL approval** for dangerous actions
- **ML prediction** — Logistic Regression (baseline) vs XGBoost (active),
  artifacts + model registry, confidence + audit-logged inference
- **LLMOps** — semantic cache, A/B model routing with circuit breakers,
  OpenTelemetry tracing into **Arize Phoenix**
- **Testing / evals** — 67 deterministic pytest checks (CI gate) + a
  golden-set live eval with an LLM-as-judge (quality gate)

## Tech stack (100% free & open source)

| Tier | Technology |
|------|------------|
| Presentation | React 18 (Vite 6) + Tailwind 3.4, zero UI libraries |
| Application | FastAPI (Python 3.12), LangGraph 0.2.72 |
| Data | PostgreSQL (users, predictions, audit, registry) + Qdrant (vectors) |
| ML | scikit-learn + XGBoost, artifacts via joblib |
| LLM / RAG | Ollama (qwen3.5:4b, llama3.1:8b, nomic-embed-text), BM25 + cross-encoder |
| Observability | OpenTelemetry → Arize Phoenix |
| Infra | Docker Compose (Postgres, Qdrant, Phoenix) |

---

## Quickstart

Requirements: Docker + Python 3.12 + Node 22 + Ollama.

```bash
# 1. Infrastructure (PostgreSQL, Qdrant, Arize Phoenix)
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # create/apply schema
python seed.py                # idempotent demo users + ERP mock orders
uvicorn main:app --port 8000  # API on :8000

# 3. Frontend (separate terminal)
cd frontend
npm install
npm run dev                   # UI on :5173 (proxies /api /chat to :8000)
```

Open http://localhost:5173 and log in with one of the demo accounts:

| Role | Username | Password |
|------|----------|----------|
| Admin | `admin`   | `admin123` |
| Expert | `expert1` | `expert123` |
| End user | `nurse1` | `nurse123` |

> `python seed.py` is idempotent — safe to run repeatedly (skips existing users).

### Tests & evals (Phase 9)

```bash
cd backend
.venv/bin/python -m pytest           # 67 deterministic checks — CI gate (headless, ~2s)
.venv/bin/python -m eval.run_eval    # golden-set eval vs the LIVE stack (Ollama must be up)
```

Every push/PR also runs `backend-tests` + `frontend-build` in GitHub Actions
(`.github/workflows/ci.yml`).

---

## Feature tour by role

| Role | What they can do |
|------|------------------|
| **Admin** | user CRUD, PDF upload/delete, audit trail, dashboard `/api/stats`, review/delete predictions, chat |
| **Expert** | list all predictions, review/override them, audit + stats, chat |
| **End user** | submit predictions, see their own predictions, chat |
| Everyone | register an end-user account, HITL approval on their own actions |

Full operation-level matrix: `Docs/PERMISSION_MATRIX.md`.

---

## Project structure

```
├── backend/
│   ├── main.py            # FastAPI app + wiring
│   ├── routes/            # auth, users, docs, ingest, predictions, stats, audit, chat
│   ├── agent/             # LangGraph CRAG: nodes, HITL, checkpointer, ERP tool
│   ├── llmops/            # semantic cache, router/circuit-breaker, streaming, telemetry
│   ├── security/          # JWT auth, RBAC, PII redaction
│   ├── models/ schemas/   # SQLAlchemy ORM + Pydantic schemas
│   ├── ml/                # training pipeline, predictor, artifacts
│   ├── tests/             # 67 deterministic pytest checks
│   └── eval/              # golden-set live eval + LLM-as-judge
├── frontend/              # React (Vite + Tailwind), role-based dashboards
├── docs/ (Docs/)          # see below
├── .github/workflows/     # CI/CD
└── docker-compose.yml     # postgres + qdrant + phoenix
```

## Documentation

| Doc | What it answers |
|-----|-----------------|
| [`Docs/ARCHITECTURE.md`](Docs/ARCHITECTURE.md) | Why every component exists + full data flows |
| [`Docs/PERMISSION_MATRIX.md`](Docs/PERMISSION_MATRIX.md) | Who can do what, at the **API level** |
| [`Docs/ML_EVALUATION.md`](Docs/ML_EVALUATION.md) | Model comparison, metrics, bias discussion |
| [`Docs/SECURITY.md`](Docs/SECURITY.md) | AuthN, authZ, PII, HITL safety, audit trail |
| [`Docs/LEARNING_COMPANION.md`](Docs/LEARNING_COMPANION.md) | Concept explanations, reuse patterns |
| [`Docs/IMPLEMENTATION_PLAN.md`](Docs/IMPLEMENTATION_PLAN.md) | Phase plan (10 phases) |
| [`Docs/PROGRESS.md`](Docs/PROGRESS.md) | Ongoing build log |
| [`Docs/diagrams/`](Docs/diagrams/) | Architecture as code (Mermaid) |

## License

University / personal educational project — not for production use.