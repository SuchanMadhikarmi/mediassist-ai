# MediAssist AI — Architecture Deep-Dive

> **MediAssist AI** — A Multi-Tier AI-Powered Clinical Support System with RAG-Based Document Query and Machine Learning Prediction

## What Are We Actually Building?

We're building an **internal AI assistant plus a machine-learning prediction service** for a company that sells WebPOS (Web-based Point of Sale) systems to clinics and hospitals. Think of it like an internal ChatGPT **that also predicts client behavior**. The system has two distinct AI engines:

**Engine 1 — RAG Assistant (the "chatbot"):**
1. Three roles log in: **Admin, Domain Expert, End User**
2. Ask questions like "What does error code 4012 mean?" or "How do I process a refund?"
3. Upload 200-page PDF contracts for analysis
4. Get **cited, accurate, streaming answers** — not hallucinated garbage
5. Can take actions (like deleting a queue) but only with human approval (HITL)

**Engine 2 — ML Prediction (the "forecaster"):**
1. Users submit structured inputs (age, job, balance, duration...)
2. A trained **XGBoost / Logistic Regression** model predicts an outcome (e.g. "will this client subscribe to premium service?")
3. Every prediction is **logged to PostgreSQL** with confidence, model version, user, and timestamp
4. Admins view model usage statistics on a dashboard

**Why is this a million-dollar project?** Because every SaaS company (Palantir, OpenAI, Salesforce, etc.) needs exactly this pattern: secure, auditable, RAG-powered AI that works on their internal documents **plus** a transparent, logged ML prediction service. You're building the template.

---

## The Full System — One Diagram

```
┌───────────────────────────────────────────────────────────────────────────┐
│                    PRESENTATION TIER (Client Browser)                     │
│  React + Tailwind CSS                                                     │
│  Login/Register · Chat UI (streaming) · PDF Upload · HITL Approval        │
│  Admin Dashboard · Expert Review Panel · User Prediction Portal           │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │ HTTPS (Fetch API / EventSource)
┌───────────────────────────────────▼───────────────────────────────────────┐
│                    APPLICATION TIER (FastAPI — Python 3.12)                │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────────────┐  │
│  │ JWT Auth +  │  │ PII Redactor │  │ RBAC (3 roles + data-level      │  │
│  │ Roles       │  │ (pre-AI)     │  │  labels in payloads/filters)    │  │
│  └──────┬──────┘  └──────┬───────┘  └───────────────┬─────────────────┘  │
│         │                │                          │                      │
│  ┌──────▼────────────────▼──────────────────────────▼─────────────────┐  │
│  │                    BUSINESS LOGIC LAYER                            │  │
│  │  · CRUD (users, documents, predictions) · Auth + Roles             │  │
│  │  · Search / Filter / Pagination        · Reports + Dashboard stats │  │
│  │  · File upload validation · Server-side validation on every input  │  │
│  └──────┬──────────────────────────┬──────────────────┬───────────────┘  │
│         │                          │                  │                    │
│  ┌──────▼────────┐        ┌───────▼───────┐   ┌──────▼──────────────┐   │
│  │ RAG ENGINE    │        │ ML INFERENCE  │   │ LLMOps              │   │
│  │ LangGraph     │        │ Service       │   │ Cache/Stream/       │   │
│  │ CRAG Agent    │        │ (XGBoost +    │   │ Circuit Breaker/    │   │
│  │ (Phase 6)     │        │  LogisticReg) │   │ Phoenix Telemetry   │   │
│  └──────┬────────┘        └──────┬───────┘   └──────┬──────────────┘   │
└─────────┼────────────────────────┼──────────────────┼────────────────────┘
          │                        │                  │
┌─────────▼────────┐  ┌────────────▼─────────┐  ┌─────▼───────────┐
│ DATA TIER        │  │ DATA TIER            │  │   OLLAMA        │
│ QDRANT (vectors) │  │ POSTGRESQL (RDBMS)   │  │   LLM models    │
│  document chunks │  │  users · documents   │  │   + embeddings  │
│  + metadata      │  │  predictions · audit │  │   (2 LLMs)      │
│  (RAG storage)   │  │  model_registry      │  └─────────────────┘
└──────────────────┘  └──────────────────────┘
                              │
                      ┌───────▼───────┐
                      │   PHOENIX     │
                      │  Traces+Evals │
                      └───────────────┘
```

**Three tiers (university requirement):**
- **Presentation** — React in the browser. Renders UI only; business logic never lives here.
- **Application** — FastAPI. All business rules, validation, auth, RBAC, inference orchestration.
- **Data** — Qdrant (vectors) + PostgreSQL (relational). PostgreSQL is the required RDBMS primary store; Qdrant is a specialized vector index for RAG.

---

## Phase 0: Why Each Component Exists

### 1. Docker Compose — The Orchestrator

**What:** A YAML file that says "start these 5 containers, connect them on a network, share these ports."

**Why not run things directly?** Because:
- Qdrant needs a specific version of Rust compiled
- Ollama needs GPU/CPU access configured
- Phoenix needs specific Python dependencies
- Your FastAPI app needs its own venv

Docker makes every component **isolated, reproducible, and portable**. Your machine, your teammate's machine, production — all identical.

**What you'll learn:** Container networking, volumes, healthchecks, dependency ordering.

---

### 2. Qdrant — The Vector Database

**What:** A database that stores text as mathematical vectors (arrays of numbers) and finds similar ones.

**Why not just use SQL?** When you ask "What does error 4012 mean?", SQL can only match exact strings. Qdrant understands *meaning*. "Error 4012" and "transaction declined code 4012" have different text but similar meanings — Qdrant finds both.

**How it works:**
1. Your PDF text gets chunked into paragraphs
2. Each paragraph gets converted to a 768-dimensional vector (Nomic Embed)
3. Vectors are stored in Qdrant with metadata (source PDF, page number, RBAC labels)
4. At query time, your question becomes a vector, Qdrant finds the nearest neighbors

**What you'll learn:** Vector similarity, HNSW indexing, payload filtering for security.

---

### 3. Ollama — The LLM Runtime

**What:** Runs LLMs locally on your machine. No API keys, no bills, no data leaving your computer.

**Why two models?**
- `qwen3.5:4b` — Fast (4 billion parameters), good for simple Q&A. ~2GB RAM.
- `llama3.1:8b` — Slower but smarter (8 billion parameters). ~5GB RAM.

**The A/B testing idea:** Route 50% of queries to each model, log which one performs better. Over time, you get data-driven model selection.

**The circuit breaker idea:** If qwen3.5 is overloaded (long queue), automatically switch to llama3.1. If both are down, return a graceful error instead of crashing.

**What you'll learn:** LLM inference, token limits, model routing patterns.

---

### 4. Arize Phoenix — The Observability Layer

**What:** An OpenTelemetry-compatible tracing system for LLM applications.

**Why is this critical?** In production, when a user asks "Why did the AI say X?", you need to see:
- What query came in
- What documents were retrieved
- What prompt was sent to the LLM
- What the LLM returned
- How long each step took
- What the confidence scores were

Phoenix captures **every span** of every request as a trace.

**What you'll learn:** OpenTelemetry, LLM observability, span/trace concepts.

---

### 5. FastAPI — The Backend API

**Why FastAPI specifically?**
- Native async (critical for streaming + concurrent LLM calls)
- Auto-generated OpenAPI docs
- Pydantic validation (request/response schemas)
- WebSocket + SSE support for streaming
- The industry standard for AI backends

**What you'll learn:** Async Python, middleware patterns, dependency injection.

---

### 6. LangGraph — The Agent Orchestrator

**What:** A library that lets you define AI workflows as **graphs** (state machines).

**Why not just a function chain?** Because real AI agents need:
- **Conditional branching:** If the retrieved docs are bad, try again (CRAG)
- **Tool calling:** Sometimes query the ERP database instead of Qdrant
- **Human-in-the-loop:** Pause execution, wait for approval, resume
- **State management:** Track what happened across steps

LangGraph gives you all of this as a directed graph.

**The CRAG (Corrective RAG) pattern:**
```
User Query
    ↓
Retrieve Documents from Qdrant
    ↓
Grade: Are these documents relevant? ──No──→ Reformulate Query → Re-retrieve
    ↓ Yes
Grade: Is this enough to answer? ──No──→ Call ERP Tool (live data)
    ↓ Yes
Generate Answer with Citations
    ↓
Grade: Is this answer faithful to the documents? ──No──→ Regenerate
    ↓ Yes
Return to User
```

**What you'll learn:** State machines, agentic patterns, tool use, HITL.

---

### 7. React Frontend — The Client Portal

**Why React + Vite + Tailwind?**
- React: Component-based UI, massive ecosystem
- Vite: Instant dev server, fast builds
- Tailwind: Utility CSS, no custom stylesheets needed

**Key features:**
- SSE streaming (text appears word-by-word)
- PDF drag-and-drop upload
- Citation display (clickable, highlighted source text)
- HITL approval buttons (Approve/Deny for dangerous actions)

**What you'll learn:** SSE consumption, React state management, real-time UIs.

---

### 8. PostgreSQL — The Relational Data Tier

**What:** The required RDBMS that stores all *structured* data. It is the primary relational store (Qdrant is only a specialized vector index for RAG, not the primary store).

**Why do we need it alongside Qdrant?**
- Qdrant is great at "find similar vectors" but not at relationships, constraints, or relational queries.
- PostgreSQL handles business-critical structured data: users, roles, document metadata, prediction logs, audit logs, and the model registry.

**Tables:**
| Table | Purpose |
|-------|---------|
| `users` | id, username, email, password_hash (bcrypt), role, active flag, timestamps |
| `documents` | id, filename, uploaded_by (FK→users), chunk_count, rbac_label, file size, timestamps |
| `predictions` | id, user_id (FK→users), input_data (JSONB), output, confidence, model_version, timestamp |
| `audit_log` | id, user_id, action, details (JSONB), ip_address, timestamp |
| `model_registry` | id, model_name, version, artifact_path, metrics, hyperparameters, trained_at |

**Why JSONB for prediction input?** Predictions have variable feature shapes; JSONB stores them flexibly while still being queryable. The university requires *every* prediction (input, output, confidence, model version, user, timestamp) be logged — PostgreSQL's `predictions` table is exactly that.

**What you'll learn:** SQLAlchemy ORM, migrations (Alembic), relationships, JSONB, parameterised queries (SQL injection prevention).

---

### 9. Machine Learning — The Prediction Engine

**What:** A classification model trained on the **Bank Marketing** dataset (UCI) that predicts whether a client subscribes to a service (e.g. premium WebPOS package).

**Why two models?** The university requires a *baseline* plus at least one compared model:
- **Logistic Regression** — the baseline (simple, interpretable, outputs probabilities)
- **XGBoost** — the main model (industry standard for tabular data)

**Evaluation:** accuracy, precision, recall, F1, confusion matrix, ROC-AUC (macro-averaged due to class imbalance).

**Deployment:** the winning model is saved as a `.joblib` artifact and loaded once by the app (never retrained per request). Inference is exposed via `POST /api/predict`.

**Prediction logging:** every call writes to the `predictions` table (input, output, confidence, model_version, user_id, timestamp) so admins can monitor model usage.

**What you'll learn:** train/val/test splits, data leakage prevention, class imbalance (SMOTE), hyperparameter tuning, model serialization, inference endpoints with confidence.

---

## The Data Flow — End to End

### Flow 1: User Asks a Question

```
1. User types "What does error 4012 mean?" in chat
2. Frontend sends POST /api/chat with JWT + message
3. Backend middleware:
   a. Validates JWT → extracts role (admin/expert/end_user)
   b. PII Redaction → strips emails, SSNs, etc. from the query
   c. RBAC check → is this user allowed to access this data?
4. Semantic Cache check → have we answered this before? If yes, return cached.
5. Query enters LangGraph CRAG:
   a. Embed query with Nomic → vector
   b. Hybrid search Qdrant (dense + sparse, fused with RRF)
   c. Re-rank top 20 → top 5 with Cross-Encoder
   d. Grade relevance → if bad, reformulate and retry (max 2x)
   e. Grade sufficiency → if need live data, call ERP tool
   f. Generate answer with citations
   g. Grade faithfulness → regenerate if hallucinating
6. Stream response token-by-token via SSE to frontend
7. Phoenix logs the entire trace
8. Semantic Cache stores this Q&A pair
9. A/B Router logs which model answered
```

### Flow 2: User Uploads a PDF

```
1. Admin drags a 200-page contract PDF onto the upload area
2. Frontend sends POST /ingest with JWT + file (multipart)
3. Backend:
   a. Validates JWT + RBAC (only admins can ingest; RBAC gate 403 otherwise)
   b. Validates file type (.pdf) and size
   c. Extracts text from PDF (PyMuPDF)
   d. Recursive chunking (~500 chars, 50 overlap), cut at sentence boundaries
   e. Redacts PII from each chunk BEFORE embedding (compliance)
   f. Embeds each chunk with nomic-embed-text (768-dim) via Ollama
   g. Stores in Qdrant with metadata:
      - text: chunk content
      - source: filename
      - page: page number
      - doc_id: document UUID (groups all chunks of one PDF)
      - rbac_label: role tag from uploader (data-level RBAC)
      - chunk_index + ingested_by
4. Returns "Ingested N chunks from contract.pdf"
```

### Flow 3: Human-in-the-Loop (Delete Queue)

```
1. User asks "Delete all orders in the failed queue"
2. LangGraph agent decides this is a dangerous action
3. Agent creates a HITL checkpoint (stored in PostgreSQL audit/hitl table)
4. Graph PAUSES (state saved)
5. Frontend shows HITL notification: "Admin/Expert approval needed"
6. Admin/Expert clicks "Approve"
7. Frontend sends POST /api/hitl/approve with checkpoint_id
8. Backend resumes the LangGraph graph from the checkpoint
9. Graph executes the deletion
10. Returns confirmation to user
```

### Flow 4: ML Prediction

```
1. End User fills the prediction form (age, job, balance, duration...)
2. Frontend validates client-side, then POST /predict with JWT
3. Backend server-side validates every field (range/format/enum)
4. Preprocesses using the SAME transformers fitted during training
   (no data leakage: scalers/encoders were fit on training data only)
5. Loads the active model artifact (.joblib — already in memory)
6. Runs inference → prediction ("yes"/"no") + confidence (probability)
7. Logs to PostgreSQL `predictions` table:
   input_data (JSONB), predicted_output, confidence, model_version,
   user_id, timestamp
8. Returns {prediction, confidence, model_version, prediction_id}
9. Frontend shows result + confidence + ML disclaimer
```

---

## File Structure — Where Everything Lives

```
projFDE/
├── docker-compose.yml          # Module 1: Infrastructure
├── .env                        # Environment variables (never commit)
├── .env.example                # Template for .env
│
├── backend/                    # FastAPI application (APPLICATION TIER)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                 # FastAPI app entrypoint
│   │
│   ├── config.py               # Settings, env vars, constants
│   ├── database.py             # SQLAlchemy engine + session factory
│   ├── models/                 # ORM models (PostgreSQL tables)
│   │   ├── __init__.py
│   │   ├── user.py             # users table
│   │   ├── document.py         # documents table
│   │   ├── prediction.py       # predictions table (ML logging)
│   │   ├── audit_log.py        # audit_log table
│   │   └── model_registry.py   # model_registry table
│   ├── security/               # Module 2: Enterprise Security
│   │   ├── __init__.py
│   │   ├── auth.py             # JWT creation/validation
│   │   ├── rbac.py             # Role-based access control
│   │   ├── pii_redactor.py     # PII stripping middleware
│   │   └── models.py           # User, Token, Role models
│   │
│   ├── ai_engine/              # Module 3: AI Engine
│   │   ├── __init__.py
│   │   ├── ingestion.py        # PDF parsing, chunking, embedding
│   │   ├── retrieval.py        # Hybrid search, RRF, re-ranking
│   │   ├── reranker.py         # Cross-encoder re-ranking
│   │   └── embeddings.py       # Nomic embedding wrapper (via Ollama)
│   │
│   ├── agent/                  # Module 4: Agentic Workflows
│   │   ├── __init__.py
│   │   ├── graph.py            # LangGraph CRAG state machine
│   │   ├── nodes.py            # Graph node implementations
│   │   ├── tools.py            # ERP tool (queries PostgreSQL now)
│   │   ├── state.py            # AgentState TypedDict
│   │   └── hitl.py             # Human-in-the-loop logic
│   │
│   ├── llmops/                 # Module 5: LLMOps
│   │   ├── __init__.py
│   │   ├── cache.py            # Semantic cache (in-memory FAISS)
│   │   ├── router.py           # A/B test + fallback + circuit breaker
│   │   ├── streaming.py        # SSE streaming utilities
│   │   └── telemetry.py        # Phoenix/OpenTelemetry setup
│   │
│   ├── ml/                     # Module 6.5/6.6: ML Pipeline
│   │   ├── __init__.py
│   │   ├── data_loader.py      # Loads Bank Marketing dataset
│   │   ├── preprocessing.py    # Fit transformers on training data
│   │   ├── train.py            # Trains 2 models, saves artifacts
│   │   ├── evaluate.py         # Comparison table + metrics
│   │   ├── predictor.py        # Loads artifact, runs inference
│   │   └── models/             # Saved .joblib artifacts
│   │
│   ├── eval/                   # Module 9: Evaluation
│   │   ├── __init__.py
│   │   ├── judge.py            # LLM-as-a-Judge scorer
│   │   ├── golden_dataset.json # Test Q&A pairs with expected answers
│   │   └── run_eval.py         # Script to run eval suite
│   │
│   └── routes/                 # API endpoints
│       ├── __init__.py
│       ├── auth.py             # POST /login, /register
│       ├── users.py            # CRUD users (admin)
│       ├── documents.py        # CRUD document metadata
│       ├── predictions.py      # CRUD prediction logs
│       ├── chat.py             # POST /chat (retrieval; SSE in Phase 7)
│       ├── predict.py          # POST /predict (ML inference)
│       ├── ingest.py           # POST /ingest (PDF upload)
│       ├── hitl.py             # POST /hitl/approve, /hitl/pending
│       ├── reports.py          # GET /reports/* (dashboard stats)
│       └── health.py           # GET /health
│
├── frontend/                   # Module 8: React Frontend (PRESENTATION TIER)
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── components/
│   │   │   ├── auth/           # Login, Register, ProtectedRoute
│   │   │   ├── admin/          # AdminDashboard, UserManagement, AuditLog
│   │   │   ├── expert/         # ExpertPanel, PredictionReview
│   │   │   ├── user/           # UserPortal, MyPredictions
│   │   │   ├── chat/           # ChatWindow, MessageBubble, CitationCard
│   │   │   ├── shared/         # PdfUpload, HitlApproval, Pagination, Layout
│   │   │   └── prediction/     # PredictionForm, PredictionResult
│   │   ├── hooks/
│   │   │   ├── useAuth.ts
│   │   │   ├── useChat.ts
│   │   │   └── usePagination.ts
│   │   └── lib/
│   │       ├── api.ts
│   │       ├── sse.ts
│   │       └── validation.ts
│   └── index.html
│
├── infra/                      # Module 9: CI/CD
│   └── .github/
│       └── workflows/
│           └── eval-gate.yml   # GitHub Action for eval scoring
│
├── data/
│   ├── pdfs/                   # Uploaded PDFs (gitignored)
│   ├── bank_marketing/         # ML dataset (raw + processed)
│   └── eval_golden.json        # Golden dataset for evaluation
│
└── Docs/
    ├── ARCHITECTURE.md         # This file
    ├── IMPLEMENTATION_PLAN.md  # 14-phase build plan
    └── LEARNING_COMPANION.md   # Concept explanations
```

---

## Learning Path — What Each Phase Teaches

| Phase | What You Build | What You Learn | Industry Relevance |
|-------|---------------|----------------|-------------------|
| 1 | Docker Compose + services | Container networking, volumes, healthchecks | Every cloud deployment |
| 2 | FastAPI skeleton | Async Python, middleware, dependency injection | Backend engineering |
| 3 | JWT + PII + RBAC | Auth patterns, security middleware, compliance | Enterprise security |
| 3.5 | PostgreSQL + SQLAlchemy | RDBMS design, ORM, relationships, JSONB | Database engineering |
| 3.6 | 3 Roles + Registration + CRUD | RBAC at scale, CRUD APIs, search/filter/pagination | Enterprise apps |
| 4 | PDF → Vectors → Qdrant | Chunking strategies, embeddings, vector DBs | RAG fundamentals |
| 5 | Hybrid search + RRF + Re-ranking | Information retrieval, fusion algorithms | Search engineering |
| 6 | LangGraph CRAG + Tools + HITL | State machines, agentic AI, human oversight | AI agent architecture |
| 6.5 | ML Training (2 models) | Baseline + XGBoost, eval metrics, leakage | MLOps / data science |
| 6.6 | ML Inference + Prediction Logging | Model serialization, inference endpoints | MLOps / feature deployment |
| 7 | Cache + A/B + Circuit Breaker + Streaming | Resilience patterns, observability | ML Ops / LLMOps |
| 7.5 | Reports + Dashboard stats | Aggregation queries, visualization | BI / analytics |
| 8 | React streaming chat + role dashboards | SSE, real-time UIs, state management | Frontend engineering |
| 9 | LLM-as-Judge + GitHub Actions | Eval frameworks, CI/CD for AI | MLOps / quality gates |
| 10 | Documentation | Technical writing, architecture diagrams | Communication |

---

## Key Concepts You'll Master

1. **RAG (Retrieval-Augmented Generation)** — The #1 pattern in enterprise AI
2. **Vector Search** — How AI "understands" meaning
3. **Hybrid Search** — Combining semantic + keyword search
4. **RRF (Reciprocal Rank Fusion)** — Merging search results from multiple engines
5. **Re-ranking** — Using a small model to re-order search results for quality
6. **CRAG (Corrective RAG)** — Self-correcting retrieval pipeline
7. **Agent Tool Use** — LLMs calling external systems
8. **HITL (Human-in-the-Loop)** — Safety rails for AI actions
9. **Circuit Breakers** — Graceful degradation under load
10. **Semantic Caching** — Avoiding redundant LLM calls
11. **A/B Testing for LLMs** — Data-driven model selection
12. **LLM-as-a-Judge** — Automated quality evaluation
13. **OpenTelemetry for LLMs** — Full observability stack
14. **SSE Streaming** — Real-time token delivery
15. **PII Redaction** — Compliance before AI processing
16. **Data-Level RBAC** — Role labels enforced inside the vector store
17. **Machine Learning Classification** — Baseline vs. tuned model comparison
18. **Evaluation Metrics** — Accuracy, precision, recall, F1, confusion matrix
19. **Model Artifacts** — Serializing sklearn/XGBoost models to `.joblib`
20. **Prediction Logging** — Every inference stored for auditability
21. **Data Leakage Prevention** — Fit transformers on training data only
22. **Class Imbalance** — Macro-F1, SMOTE, stratified splits

---

## Production Scaling Notes (For Your Resume/Interviews)

This project is designed for **local development** ($0 cost). In production:

- **Ollama → vLLM or TGI:** For GPU-optimized serving with batching
- **Qdrant → Qdrant Cloud or Weaviate:** Managed vector DB with replication
- **PostgreSQL → Managed RDS/Cloud SQL:** Backups, failover, scaling
- **Docker → Kubernetes:** For auto-scaling, rolling deploys
- **XGBoost → Model registry (MLflow):** Versioned, governed deployments
- **In-memory cache → Redis:** Distributed semantic cache
- **Phoenix → Datadog/New Relic:** Enterprise observability
- **Single machine → Load balancer + multiple workers:** Horizontal scaling

---

## Cost Breakdown

| Component | Local Cost | Production Equivalent |
|-----------|-----------|----------------------|
| Qdrant | $0 (Docker) | $65/mo (Qdrant Cloud) |
| PostgreSQL | $0 (Docker) | $15/mo (small RDS/Cloud SQL) |
| Ollama | $0 (your CPU) | $0.50-2.00/1M tokens (vLLM) |
| Phoenix | $0 (Docker) | $100/mo (Datadog) |
| FastAPI | $0 | $20/mo (small VM) |
| React | $0 | $0 (static hosting) |
| **Total** | **$0** | **~$215/mo minimum** |

---

*Ready to continue building? Current state: Phases 1–5 + 4 complete. Next milestone: Phase 6 (LangGraph CRAG).*
