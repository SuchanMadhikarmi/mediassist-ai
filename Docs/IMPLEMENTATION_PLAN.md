# Implementation Plan — MediAssist AI (Unified 14-Phase Plan)

## How This Works
Each phase has:
1. **The Goal** — What we're building
2. **The Files** — Exact files to create/modify
3. **The Concepts** — What to learn before coding
4. **The Steps** — Exact implementation order
5. **The Checkpoint** — How to verify it works

---

## Phase 1: Infrastructure (Docker Compose) ✅ DONE

### Goal
Get Qdrant, Ollama, and Phoenix running locally with a shared network.

### Files
```
projFDE/
├── docker-compose.yml
├── .env
├── .env.example
└── data/
    └── pdfs/          (empty dir for uploaded PDFs)
```

### Completed
- Phoenix runs via Docker Compose (healthcheck uses Python urllib — image has no curl/sh)
- Qdrant: existing standalone container (NOT in compose)
- Ollama: existing bare-metal (NOT in compose)
- `.env` + `.env.example` configured
- `.gitignore` created

---

## Phase 2: Backend Foundation (FastAPI) ✅ DONE

### Goal
A running FastAPI app with proper project structure, config, and logging.

### Files
```
backend/
├── main.py                 # FastAPI app + CORS
├── config.py               # Pydantic Settings from .env
├── routes/
│   ├── __init__.py
│   └── health.py           # GET /health (pings qdrant/ollama/phoenix)
└── .venv/                  # Python virtual environment
```

### Completed
- FastAPI app with CORS middleware (localhost:5173)
- Pydantic Settings reads from `.env` automatically
- Health endpoint returns status of all 3 services
- Server: `uvicorn main:app --reload --port 8000`

---

## Phase 3: Enterprise Security (JWT + PII + RBAC) ✅ DONE

### Goal
JWT authentication, PII redaction middleware, and RBAC enforcement.

### Files
```
backend/
├── security/
│   ├── __init__.py
│   ├── models.py           # Role enum, LoginRequest, TokenResponse, User
│   ├── auth.py             # JWT creation/verification, password hashing
│   ├── pii_redactor.py     # Regex PII stripping (EMAIL/SSN/PHONE/CREDIT_CARD/ZIP)
│   └── rbac.py             # require_role factory (FastAPI dependency)
├── routes/
│   ├── auth.py             # POST /login, mock users (admin/admin123, nurse1/nurse123)
│   └── demo.py             # TEMP: /demo/whoami, /demo/admin-only, /demo/redact
```

### Completed
- JWT = HS256, sub/role/iat/exp claims
- Bcrypt password hashing (constant-time comparison)
- PII redaction runs before AI processing
- RBAC dependency factory: `Depends(require_role(Role.ADMIN))`
- Verified: unauth→401, viewer→403, PII strips correctly

---

## Phase 3.5: PostgreSQL + SQLAlchemy ORM 🆕

### Goal
Add a relational database as the Data Tier for all structured data.

### Concepts to Learn
- SQLAlchemy ORM (Python ↔ PostgreSQL bridge)
- Alembic (database migrations — schema version control)
- Connection pooling
- ORM relationships (one-to-many)

### Files
```
projFDE/
├── docker-compose.yml              # ADD postgres service
├── backend/
│   ├── database.py                 # NEW — SQLAlchemy engine + session factory
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py                 # User ORM model
│   │   ├── document.py             # Document metadata ORM model
│   │   ├── prediction.py           # Prediction log ORM model
│   │   ├── audit_log.py            # Audit trail ORM model
│   │   └── model_registry.py       # ML model versions + metrics
│   ├── migrations/                  # Alembic migrations directory
│   │   ├── env.py
│   │   └── versions/
│   └── seed.py                     # Seed script (mock data for dev)
├── .env                            # ADD DATABASE_URL=postgresql://...
└── .env.example                    # ADD same
```

### PostgreSQL Tables
```sql
-- users (replaces mock dict in routes/auth.py)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'expert', 'end_user')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- documents (metadata for ingested PDFs)
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(255) NOT NULL,
    uploaded_by UUID REFERENCES users(id),
    chunk_count INTEGER,
    rbac_label VARCHAR(20) NOT NULL,
    file_size_bytes BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- predictions (ML inference log)
CREATE TABLE predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    input_data JSONB NOT NULL,
    predicted_output VARCHAR(50) NOT NULL,
    confidence DECIMAL(5,4),
    model_version VARCHAR(50) NOT NULL,
    inference_time_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- audit_log (every important action)
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    details JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- model_registry (tracks trained ML models)
CREATE TABLE model_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name VARCHAR(100) NOT NULL,
    version VARCHAR(50) NOT NULL,
    artifact_path VARCHAR(500),
    metrics JSONB,
    hyperparameters JSONB,
    training_data_hash VARCHAR(64),
    trained_by UUID REFERENCES users(id),
    trained_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);
```

### Checkpoint
```bash
docker compose up -d  # PostgreSQL starts
alembic upgrade head  # Tables created
python seed.py        # Mock users inserted
curl http://localhost:8000/health  # Shows postgres: connected
```

---

## Phase 3.6: 3 Roles + Registration + CRUD 🆕

### Goal
Expand from 2 roles to 3, add user registration, full CRUD on 3 entities, search/filter/pagination.

### Roles
| Role | Permissions | Dashboard |
|------|------------|-----------|
| **admin** | Manage users, view all predictions, view audit logs, approve HITL | Admin Dashboard |
| **expert** | View assigned predictions, approve/override predictions | Expert Review Panel |
| **end_user** | Register, submit prediction inputs, view own predictions only | User Portal |

### Files
```
backend/
├── routes/
│   ├── auth.py                     # MODIFY — add registration, logout, refresh token
│   ├── users.py                    # NEW — CRUD for user management (admin only)
│   ├── documents.py                # NEW — CRUD for document metadata
│   ├── predictions.py              # NEW — CRUD for prediction logs
│   └── audit.py                    # NEW — audit log viewer (admin/expert)
├── schemas/
│   ├── __init__.py
│   ├── user.py                     # UserCreate, UserUpdate, UserResponse
│   ├── document.py                 # DocumentResponse
│   ├── prediction.py               # PredictionCreate, PredictionResponse
│   └── pagination.py               # PaginatedResponse generic
└── dependencies.py                 # shared FastAPI dependencies (get_db, pagination)
```

### Key Endpoints
```
POST   /api/auth/register          — public, creates end_user
POST   /api/auth/login             — returns access + refresh tokens
POST   /api/auth/logout            — invalidates refresh token
POST   /api/auth/refresh           — get new access token

GET    /api/users                  — admin: list all users (paginated, searchable)
POST   /api/users                  — admin: create user
PUT    /api/users/{id}             — admin: update user
DELETE /api/users/{id}             — admin: soft-delete user

GET    /api/documents              — list documents (filtered by RBAC)
POST   /api/documents              — admin: upload + ingest PDF
PUT    /api/documents/{id}         — admin: update metadata
DELETE /api/documents/{id}         — admin: delete document + vectors

GET    /api/predictions            — admin/expert: all, end_user: own only
POST   /api/predictions            — end_user: submit prediction input
PUT    /api/predictions/{id}/review — expert: approve/override prediction
DELETE /api/predictions/{id}       — admin: delete prediction record

GET    /api/audit                  — admin/expert: view audit trail (paginated)
```

### Pagination Response Format
```json
{
  "items": [...],
  "total": 156,
  "page": 1,
  "per_page": 20,
  "pages": 8
}
```

### Checkpoint
```bash
# Register
curl -X POST http://localhost:8000/api/auth/register \
  -d '{"username":"user1","email":"u@x.com","password":"Pass123!"}'

# Login as admin
curl -X POST http://localhost:8000/api/auth/login \
  -d '{"username":"admin","password":"admin123"}'

# List users (admin only)
curl http://localhost:8000/api/users -H "Authorization: Bearer <token>"
```

---

## Phase 4: AI Engine — Ingestion ⬜ NEXT

### Goal
PDF parsing → chunking → embedding → Qdrant storage.

### Concepts to Learn
- What embeddings are (768-dimensional vectors)
- Cosine similarity
- Nomic Embed model
- PyMuPDF for PDF text extraction
- Recursive text splitting (chunking strategies)
- Qdrant collection creation with payload schema
- HNSW index parameters

### Files
```
backend/
├── ai_engine/
│   ├── __init__.py
│   ├── embeddings.py        # Nomic SentenceTransformer wrapper
│   ├── ingestion.py         # PDF parsing + chunking + Qdrant upload
│   └── reranker.py          # Cross-Encoder (stub for Phase 5)
└── routes/
    └── ingest.py            # POST /api/ingest (admin-only, file upload)
```

### Qdrant Collection
```python
# 768-dim Nomic embeddings, COSINE distance
# Payload: source, page, chunk_id, rbac_label, ingested_by, document_id
# Payload indexes: rbac_label (KEYWORD) for RBAC filtering
```

### Checkpoint
Upload a test PDF, verify chunks appear in Qdrant dashboard at http://localhost:6333/dashboard

---

## Phase 5: AI Engine — Retrieval ⬜

### Goal
Hybrid search (dense + sparse) with RRF fusion and Cross-Encoder re-ranking.

### Concepts to Learn
- BM25 (Okapi BM25) algorithm basics
- Reciprocal Rank Fusion math: `RRF_score(d) = Σ 1/(k + rank_i(d))`
- Cross-Encoder vs Bi-Encoder
- Score normalization

### Files
```
backend/
├── ai_engine/
│   ├── retrieval.py         # Hybrid search orchestration
│   └── reranker.py          # Cross-Encoder re-ranking (top 20 → top 5)
└── routes/
    └── chat.py              # POST /api/chat (basic, no streaming yet)
```

### Pipeline
```
Query → Embed (Nomic)
    → Dense search Qdrant (vector similarity)
    → Sparse search BM25 (keyword match)
    → RRF fusion (k=60)
    → Cross-Encoder re-rank top 20 → top 5
    → Return context documents
```

### Checkpoint
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "What does error 4012 mean?"}'
# Should return answer with citations
```

---

## Phase 6: Agentic Workflows (LangGraph CRAG) ⬜

### Goal
CRAG with tool calling and human-in-the-loop.

### Concepts to Learn
- LangGraph StateGraph API
- Conditional edges (branching logic)
- Tool calling (LLM deciding to use external tools)
- Checkpointing (saving/resuming graph state)
- HITL patterns (pause → notify → resume)

### Files
```
backend/
├── agent/
│   ├── __init__.py
│   ├── state.py             # AgentState TypedDict
│   ├── nodes.py             # retrieve, grade_relevance, reformulate, check_tool, query_erp, generate, grade_faithfulness, check_hitl
│   ├── graph.py             # LangGraph CRAG state machine
│   ├── tools.py             # ERP mock (queries PostgreSQL)
│   └── hitl.py              # HITL checkpoint logic
```

### CRAG Pattern
```
User Query → Retrieve → Grade Docs → (bad? reformulate → retry)
    → (good?) Grade Sufficiency → (need data? call ERP tool)
    → Generate Answer → Grade Faithfulness → (hallucinating? regenerate)
    → Return to User
    → (dangerous action? HITL pause → wait for approval → resume)
```

### Checkpoint
```bash
# Test normal RAG
curl -X POST http://localhost:8000/api/chat \
  -d '{"message": "What does error 4012 mean?"}'

# Test tool calling
curl -X POST http://localhost:8000/api/chat \
  -d '{"message": "What is the status of order 1?"}'

# Test HITL
curl -X POST http://localhost:8000/api/chat \
  -d '{"message": "Delete all failed orders"}'
# Should return HITL pending notification
```

---

## Phase 6.5: ML Model Training 🆕

### Goal
Train 2 models on Bank Marketing dataset, evaluate properly, save as artifacts.

### Dataset: Bank Marketing (UCI)
- 45,211 records, 16 features
- Binary classification: will client subscribe to term deposit? (yes/no)
- Class imbalance: 88% no / 12% yes
- Mix of categorical (job, marital, education, contact, month) + numerical (age, balance, duration, campaign)
- No missing values, well-documented

### Models
| Model | Role | Why |
|-------|------|-----|
| Logistic Regression | Baseline | Interpretable, standard baseline, outputs probabilities |
| XGBoost | Main model | Industry standard for tabular data, handles mixed types, feature importance |

### Concepts to Learn
- Train/validation/test split strategies (stratified)
- Feature preprocessing (OneHotEncoder + StandardScaler)
- Data leakage prevention (fit on training data only)
- Class imbalance handling (SMOTE or class weights)
- Hyperparameter tuning
- Evaluation metrics: precision, recall, F1, confusion matrix, ROC-AUC
- Model serialization (joblib)

### Files
```
backend/
├── ml/
│   ├── __init__.py
│   ├── data_loader.py       # Downloads/loads Bank Marketing dataset
│   ├── preprocessing.py     # Fit transformers on training data only
│   ├── train.py             # Trains both models, saves artifacts
│   ├── evaluate.py          # Generates comparison table + plots
│   ├── predictor.py         # Loads artifacts, runs inference
│   └── models/              # Saved model artifacts
│       ├── logistic_regression_v1.pkl
│       └── xgboost_v1.pkl
└── data/
    └── bank_marketing/      # Raw + processed dataset
        ├── bank-full.csv
        └── preprocessing_metadata.json
```

### Training Pipeline
```
1. Load data (bank-full.csv)
2. Stratified split: 70% train, 15% val, 15% test
3. Fit preprocessors on TRAINING DATA ONLY (prevent data leakage)
4. Handle imbalance with SMOTE on training data only
5. Train baseline (Logistic Regression)
6. Train main model (XGBoost with hyperparameter tuning)
7. Evaluate both on TEST SET (never used during training)
8. Save artifacts as .pkl files
9. Register models in PostgreSQL model_registry table
```

### Evaluation Output
```
Model Comparison Table:
┌─────────────────────┬─────────────────┬──────────────┐
│ Metric              │ Logistic Reg.   │ XGBoost      │
├─────────────────────┼─────────────────┼──────────────┤
│ Accuracy            │ 0.891           │ 0.912        │
│ Precision (macro)   │ 0.784           │ 0.853        │
│ Recall (macro)      │ 0.723           │ 0.812        │
│ F1-score (macro)    │ 0.752           │ 0.832        │
│ ROC-AUC             │ 0.901           │ 0.943        │
│ Confusion Matrix    │ [[3890, 234]    │ [[3952, 172] │
│                     │  [412,  246]]   │  [301, 357]] │
└─────────────────────┴─────────────────┴──────────────┘
```

### Checkpoint
```bash
python backend/ml/train.py          # Trains both models
python backend/ml/evaluate.py       # Generates comparison report
ls backend/ml/models/               # Two .pkl files exist
```

---

## Phase 6.6: ML Inference Endpoint 🆕

### Goal
Expose model inference via API, validate input, return confidence, log to PostgreSQL.

### Concepts to Learn
- Input validation (Pydantic Field constraints)
- Model loading from artifact
- Preprocessing at inference time (must match training preprocessing)
- Confidence/probability extraction
- Prediction logging

### Files
```
backend/
├── ml/
│   └── predictor.py         # MODIFY — load model, validate, return prediction + confidence
├── routes/
│   └── predict.py           # NEW — POST /api/predict endpoint
```

### Input Validation
```python
class PredictionInput(BaseModel):
    age: int = Field(ge=18, le=100)
    job: str  # must be one of valid categories
    marital: str  # married, single, divorced
    education: str  # primary, secondary, tertiary, unknown
    default: str  # yes, no
    balance: float
    housing: str  # yes, no
    loan: str  # yes, no
    contact: str  # cellular, telephone, unknown
    day: int = Field(ge=1, le=31)
    month: str  # jan..dec
    duration: int = Field(ge=0)
    campaign: int = Field(ge=1)
    pdays: int
    previous: int = Field(ge=0)
    poutcome: str  # success, failure, unknown, other
```

### Endpoint
```
POST /api/predict
Authorization: Bearer <token> (any role)

Request:  {"age": 35, "job": "admin.", "marital": "married", ...}
Response: {
    "prediction": "yes",
    "confidence": 0.8734,
    "model_version": "xgboost_v1.0",
    "prediction_id": "uuid-here"
}
```

### On Every Prediction
1. Validate input (reject out-of-range/invalid values)
2. Preprocess (same transformers used in training)
3. Run inference
4. Return prediction + confidence to user
5. Log to `predictions` table (input, output, confidence, model_version, user_id, timestamp)
6. Log to `audit_log` table

### Checkpoint
```bash
curl -X POST http://localhost:8000/api/predict \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"age":35,"job":"admin.","marital":"married","education":"secondary",...}'
# Returns prediction + confidence, logged to PostgreSQL
```

---

## Phase 7: LLMOps ⬜

### Goal
Semantic cache, A/B routing, circuit breaker, streaming, Phoenix tracing.

### Concepts to Learn
- FAISS for in-memory vector search
- Circuit breaker state machine (CLOSED/OPEN/HALF-OPEN)
- SSE protocol (text/event-stream)
- OpenTelemetry spans and traces
- Token-level streaming from Ollama

### Files
```
backend/
├── llmops/
│   ├── __init__.py
│   ├── cache.py             # FAISS semantic cache (threshold 0.95)
│   ├── router.py            # A/B test + fallback + circuit breaker
│   ├── streaming.py         # SSE streaming utilities
│   └── telemetry.py         # Phoenix/OpenTelemetry setup
└── routes/
    └── chat.py              # MODIFY — add SSE StreamingResponse
```

### Checkpoint
1. Ask same question twice → second should be cached (fast)
2. Monitor Phoenix at http://localhost:6006 → see traces
3. Stream a response → text appears token-by-token

---

## Phase 7.5: Reports + Dashboard Stats 🆕

### Goal
Admin dashboard with model usage stats, summary reports, export.

### Files
```
backend/
├── routes/
│   └── reports.py           # NEW — dashboard statistics endpoints
```

### Endpoints
```
GET /api/reports/dashboard       — admin: overview stats
GET /api/reports/model-stats     — admin/expert: model performance over time
GET /api/reports/user-activity   — admin: user action summary
GET /api/reports/export          — admin: export predictions as CSV
```

### Dashboard Stats
```json
{
  "total_users": 45,
  "total_documents": 12,
  "total_predictions": 1847,
  "predictions_today": 23,
  "model_accuracy_trend": [...],
  "predictions_by_model": {"xgboost": 1200, "logistic_regression": 647}
}
```

---

## Phase 8: React Frontend ⬜

### Goal
Login, streaming chat, PDF upload, citations, HITL approval, 3 role-based dashboards, prediction UI.

### Files
```
frontend/
├── src/
│   ├── App.tsx
│   ├── components/
│   │   ├── auth/
│   │   │   ├── Login.tsx
│   │   │   ├── Register.tsx
│   │   │   └── ProtectedRoute.tsx
│   │   ├── admin/
│   │   │   ├── AdminDashboard.tsx
│   │   │   ├── UserManagement.tsx
│   │   │   └── AuditLog.tsx
│   │   ├── expert/
│   │   │   ├── ExpertPanel.tsx
│   │   │   └── PredictionReview.tsx
│   │   ├── user/
│   │   │   ├── UserPortal.tsx
│   │   │   └── MyPredictions.tsx
│   │   ├── chat/
│   │   │   ├── ChatWindow.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   └── CitationCard.tsx
│   │   ├── shared/
│   │   │   ├── PdfUpload.tsx
│   │   │   ├── HitlApproval.tsx
│   │   │   ├── Pagination.tsx
│   │   │   ├── SearchFilter.tsx
│   │   │   └── Layout.tsx
│   │   └── prediction/
│   │       ├── PredictionForm.tsx
│   │       └── PredictionResult.tsx
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   ├── useChat.ts
│   │   └── usePagination.ts
│   └── lib/
│       ├── api.ts
│       ├── sse.ts
│       └── validation.ts
```

### Key Features
- Client-side form validation (required fields, data formats, password rules)
- DOM manipulation and dynamic content updates
- Async requests (Fetch API) — no page reloads
- Responsive layout (Tailwind: mobile + desktop)
- Role-based routing (ProtectedRoute component)
- SSE streaming consumption for chat
- PDF drag-and-drop upload with validation
- HITL approval buttons (approve/deny)
- Disclaimer on prediction results

### Checkpoint
1. Navigate to http://localhost:5173
2. Register as end_user, login
3. Submit prediction → see result with confidence
4. Login as admin → see dashboard with user/prediction stats
5. Upload PDF → see confirmation
6. Ask chat question → see streaming response
7. Ask for dangerous action → see HITL buttons

---

## Phase 9: Eval CI/CD ⬜

### Goal
Automated quality evaluation that blocks bad PRs.

### Files
```
backend/
├── eval/
│   ├── __init__.py
│   ├── judge.py             # LLM-as-a-Judge scorer
│   └── run_eval.py          # Run eval suite
├── data/
│   └── eval_golden.json     # Golden Q&A pairs
infra/
└── .github/
    └── workflows/
        └── eval-gate.yml    # GitHub Action
```

### Checkpoint
Run `python backend/eval/run_eval.py` locally and see a scoring report.

---

## Phase 10: Documentation ⬜

### Goal
Professional documentation with architecture diagrams, permission matrix, ML evaluation, bias discussion.

### Files
```
├── README.md
├── docs/
│   ├── ARCHITECTURE.md      # UPDATE with 3-tier + PostgreSQL + ML
│   ├── LEARNING_COMPANION.md # UPDATE with ML concepts
│   ├── IMPLEMENTATION_PLAN.md # This file
│   ├── PERMISSION_MATRIX.md  # University-required permission matrix
│   ├── ML_EVALUATION.md      # Model comparison + bias discussion
│   ├── SECURITY.md           # Security measures documentation
│   └── diagrams/
│       ├── system-overview.mermaid
│       ├── data-flow.mermaid
│       └── ml-pipeline.mermaid
```

### Permission Matrix (University Requirement)
```
| Feature / Operation            | Admin | Expert | End User |
|-------------------------------|-------|--------|----------|
| Create user accounts          | Yes   | No     | No       |
| Delete users                  | Yes   | No     | No       |
| Upload documents (PDFs)       | Yes   | No     | No       |
| Delete documents              | Yes   | No     | No       |
| Submit prediction input       | Yes   | Yes    | Yes      |
| View all predictions          | Yes   | Yes    | No       |
| View own predictions only     | Yes   | Yes    | Yes      |
| Approve/override prediction   | Yes   | Yes    | No       |
| View model logs/statistics    | Yes   | Yes    | No       |
| View audit trail              | Yes   | Yes    | No       |
| Export reports                | Yes   | No     | No       |
| Use AI chat (RAG)             | Yes   | Yes    | Yes      |
| Manage HITL approvals         | Yes   | Yes    | No       |
```

---

## Build Order Summary

```
Phase 1:     docker-compose.yml + services              ✅ DONE
Phase 2:     FastAPI skeleton + health endpoint          ✅ DONE
Phase 3:     Security (JWT, PII, RBAC)                   ✅ DONE
Phase 3.5:   PostgreSQL + SQLAlchemy + ORM Models        🆕
Phase 3.6:   3 Roles + Registration + CRUD               🆕
Phase 4:     Ingestion (PDF → Qdrant)                    ⬜ NEXT
Phase 5:     Retrieval (Hybrid search + RRF)             ⬜
Phase 6:     LangGraph (CRAG + Tools + HITL)             ⬜
Phase 6.5:   ML Training (2 models, evaluation)          🆕
Phase 6.6:   ML Inference Endpoint + Logging             🆕
Phase 7:     LLMOps (Cache + Streaming + Phoenix)        ⬜
Phase 7.5:   Reports + Dashboard Stats                   🆕
Phase 8:     React Frontend (3 dashboards)               ⬜
Phase 9:     Eval CI/CD                                  ⬜
Phase 10:    Documentation + Permission Matrix           ⬜
```

Each phase builds on the previous one. No phase requires skipping ahead.
