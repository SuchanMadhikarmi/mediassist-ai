# Learning Companion — Deep-Dive Explanations

## Table of Contents
1. [Three-Tier Architecture](#1-three-tier-architecture)
2. [Container Networking Explained](#2-container-networking)
3. [Relational Databases (PostgreSQL)](#3-relational-databases)
4. [Vector Databases Explained](#4-vector-databases)
5. [Embeddings Explained](#5-embeddings)
6. [RAG Explained](#6-rag)
7. [Hybrid Search & RRF](#7-hybrid-search)
8. [Re-ranking](#8-re-ranking)
9. [LangGraph State Machines](#9-langgraph)
10. [JWT Authentication](#10-jwt)
11. [PII Redaction](#11-pii)
12. [RBAC](#12-rbac)
13. [CRUD, Search, Filter & Pagination](#13-crud)
14. [Circuit Breakers](#14-circuit-breakers)
15. [Semantic Caching](#15-semantic-cache)
16. [SSE Streaming](#16-sse)
17. [OpenTelemetry](#17-opentelemetry)
18. [Machine Learning Classification](#18-machine-learning)
19. [LLM-as-a-Judge](#19-llm-judge)

---

## 1. Three-Tier Architecture

### What It Is
Software is split into three physical layers, each with one job:

```
┌──────────────────────────────┐
│  PRESENTATION TIER           │  React frontend (browser)
│  "What the user sees"        │  Renders UI, handles clicks,
│                              │  shows data. NO business rules.
├──────────────────────────────┤
│  APPLICATION TIER            │  FastAPI backend
│  "The brain / the rules"     │  Validates input, applies business
│  (also called Business Logic)│  logic, controls access, calls DBs.
├──────────────────────────────┤
│  DATA TIER                   │  PostgreSQL + Qdrant
│  "Where data lives"          │  Stores rows (relational) + vectors.
└──────────────────────────────┘
```

### Why the University Requires It
A proper 3-tier split forces **separation of concerns**:
- Business rules live in ONE place (the application tier) → easy to fix bugs
- You can swap the presentation tier (React → mobile app) without touching logic
- You can swap the database without rewriting logic

**Anti-pattern to avoid:** Putting a business rule in the frontend (e.g. "only admins can ingest"). A savvy user could call the API directly and skip the check. Rules must always be enforced by the app tier.

---

## 2. Container Networking

### The Problem
You have 5 different services that need to talk to each other:
- FastAPI needs to reach Qdrant
- FastAPI needs to reach Ollama
- FastAPI needs to reach Phoenix
- React dev server needs to reach FastAPI

Without Docker, you'd install each service directly on your machine, manually configure ports, and pray nothing conflicts.

### Docker's Solution
Docker Compose creates a **virtual network** where each container gets:
- A **hostname** (its service name in docker-compose.yml)
- An **IP address** on the virtual network
- Only **exposed ports** accessible from outside

```yaml
# docker-compose.yml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"    # REST API (host:container)
    # Other containers can reach this as "qdrant:6333"
    
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    # Other containers can reach this as "ollama:11434"
```

**Key insight:** The `ports` mapping has two parts:
- **Left side (6333):** What your host machine uses (browser, scripts)
- **Right side (6333):** What the container listens on internally

When FastAPI connects to Qdrant, it uses `http://qdrant:6333` — Docker's DNS resolves "qdrant" to the container's IP.

### Healthchecks
```yaml
qdrant:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:6333/health"]
    interval: 10s
    timeout: 5s
    retries: 3
```
This tells Docker: "Don't consider Qdrant 'ready' until the health endpoint responds. If it fails 3 times in a row, restart it."

---

## 3. Relational Databases (PostgreSQL)

### Why a Relational Database?
We have structured, interrelated data (users, documents, predictions, audit logs) that needs:
- **Relationships:** "This document was uploaded by this user"
- **Constraints:** "Username must be unique", "Role must be one of 3 values"
- **Atomicity:** "Write the prediction log AND the audit entry together, or not at all"

Qdrant (a vector DB) cannot do any of this well. PostgreSQL is the required RDBMS for the university — it is our **primary** store; Qdrant is only a specialized vector index for RAG.

### Rows, Tables, Keys — The Core Idea
```
users
┌────┬──────────┬──────────────────────┬──────────────┐
│ id │ username │ password_hash        │ role         │
├────┼──────────┼──────────────────────┼──────────────┤
│ 1  │ admin1   │ $2b$12$y9N... (bcrypt)│ admin        │
│ 2  │ nurse1   │ $2b$12$...           │ end_user     │
└────┴──────────┴──────────────────────┴──────────────┘

Predictions belong to a user (foreign key):
predictions.user_id  →  users.id
```

- **Primary key (PK):** unique ID of a row (users.id)
- **Foreign key (FK):** a reference to another table's PK — this is what creates relationships
- **Index:** a speed structure so lookups don't scan the whole table

### How We Talk to It Without Raw SQL
SQLAlchemy ORM lets us write **Python objects** instead of SQL strings:
```python
user = User(username="nurse1", role=Role.END_USER)
db_session.add(user)
db_session.commit()
```
SQLAlchemy translates this to `INSERT INTO users ...`. Benefits: type safety, no manual string-concatenation SQL (which is how **SQL injection** happens), and it works across DBs.

### JSONB — A Column Inside Postgres That Behaves Like a Dict
ML prediction inputs have many different features. Instead of 20 columns, we store:
```python
input_data: {"age": 42, "job": "admin.", "balance": 2500, "duration": 180}
```
JSONB keeps it flexible AND queryable (e.g. `WHERE input_data->>'job' = 'admin.'`).

**Concept you'll need for your viva:** *What is an ORM? Why use one over raw SQL?*

---

## 4. Vector Databases

### The Fundamental Concept
A vector database stores data as **vectors** (arrays of floating-point numbers) and finds **similar** vectors efficiently.

**Analogy:** Imagine you have a library of 10,000 books. A traditional database indexes by title, author, ISBN. A vector database indexes by **meaning**. When you search "books about lonely people in cities," it finds novels that match the *concept*, not just the keywords.

### How Text Becomes a Vector
```
Input: "Error 4012 means the transaction was declined"
        ↓
Embedding Model (Nomic): "I understand this means a payment failed"
        ↓
Output: [0.023, -0.156, 0.892, ..., 0.445]  (768 numbers)
```

This 768-dimensional vector captures the **semantic meaning** of the text. Similar texts produce similar vectors.

### Qdrant's Architecture
Qdrant uses **HNSW (Hierarchical Navigable Small World)** for fast similarity search:

```
Level 2:  A -------- B -------- C
          |          |          |
Level 1:  A --- D --- B --- E -- C
          |    |     |    |     |
Level 0:  A - D - F - B - E - G - C

Query: Find closest to vector X
1. Start at entry point (top level)
2. Navigate to nearest neighbor
3. Go down a level, repeat
4. At bottom level, collect K nearest neighbors
```

**Why not brute force?** For 1 million vectors, brute force = 1 million comparisons. HNSW = ~100 comparisons. That's the difference between 10ms and 10 seconds.

---

## 5. Embeddings

### What Is an Embedding Model?
A neural network trained to convert text into vectors where:
- **Similar meanings → similar vectors** (cosine similarity close to 1)
- **Different meanings → different vectors** (cosine similarity close to 0)

### Why Nomic Embed Specifically?
- **768 dimensions:** Good balance of precision vs speed
- **Open source:** Runs locally, no API calls
- **MTEB benchmark:** Top performer for its size class
- **Fast:** ~50ms per text chunk on CPU

### Cosine Similarity
```
similarity(A, B) = (A · B) / (||A|| * ||B||)

Where:
- A · B = dot product (sum of element-wise multiplication)
- ||A|| = magnitude (Euclidean norm)

Result: -1 (opposite) to 1 (identical)
Typical threshold for "similar": > 0.7
```

---

## 6. RAG (Retrieval-Augmented Generation)

### The Problem with Pure LLMs
Ask ChatGPT: "What does error 4012 mean in our POS system?"
Response: "I don't have specific information about your POS system's error codes."

LLMs are trained on public data. They know nothing about your internal documents.

### RAG's Solution
Instead of asking the LLM directly:
1. **Retrieve** relevant documents from your knowledge base
2. **Augment** the prompt with those documents
3. **Generate** an answer based on the retrieved context

```
User: "What does error 4012 mean?"
    ↓
RAG System:
1. Search Qdrant for "error 4012"
2. Find: "Error 4012: Transaction declined due to insufficient funds"
3. Build prompt:
   "Context from company manuals:
    Error 4012: Transaction declined due to insufficient funds.
    This occurs when the customer's card balance is below the transaction amount.
    Resolution: Ask customer to use alternative payment method."
   
   Question: "What does error 4012 mean?"
    ↓
LLM: "Error 4012 indicates a transaction was declined due to insufficient funds.
      The customer's card balance is below the transaction amount. You should ask
      the customer to use an alternative payment method."
```

**Key insight:** The LLM doesn't "know" about error 4012. It's **reading** your documents and **summarizing** them. This is why citations work — you can trace back to the exact source.

---

## 7. Hybrid Search & RRF

### Why Not Just One Search Type?

**Dense search (vector):** 
- Finds semantic similarity
- Great for: "How do I process refunds?" → finds "return merchandise procedure"
- Bad for: Can miss exact keyword matches

**Sparse search (BM25):**
- Finds keyword matches
- Great for: "Error 4012" → finds documents containing "4012"
- Bad for: Can't understand synonyms or paraphrasing

### Hybrid Search = Best of Both Worlds
Run both searches in parallel, merge results.

### Reciprocal Rank Fusion (RRF)
The math for merging results from different search engines:

```
RRF_score(d) = Σ 1/(k + rank_i(d))

Where:
- d = document
- rank_i(d) = rank of d in search engine i
- k = constant (typically 60)
```

**Why this works:** A document ranked #1 in dense search AND #3 in sparse search gets:
```
RRF = 1/(60+1) + 1/(60+3) = 0.0164 + 0.0159 = 0.0323
```

A document ranked #1 in only one search:
```
RRF = 1/(60+1) + 1/(60+∞) = 0.0164 + 0 = 0.0164
```

Multi-source evidence gets higher scores. This is **exactly** what Google does.

---

## 8. Re-ranking

### The Problem
After hybrid search, you have 20 candidate documents. But they're ranked by search score, not by **relevance to the query**.

### The Solution: Cross-Encoder
A Cross-Encoder takes **(query, document) pairs** and outputs a relevance score:

```
Cross-Encoder("What does error 4012 mean?", "Error 4012: insufficient funds")
→ Score: 0.95 (highly relevant)

Cross-Encoder("What does error 4012 mean?", "Chapter 1: Introduction to POS systems")
→ Score: 0.12 (not relevant)
```

**Why not use this for all search?** Because Cross-Encoder is O(n²) — it must evaluate every query-document pair. For 10,000 documents, that's 10,000 neural network calls. Too slow.

**The pipeline:**
1. BM25 + Dense → top 20 candidates (fast)
2. Cross-Encoder re-ranks 20 → top 5 (slow but accurate)

---

## 9. LangGraph State Machines

### Why State Machines for AI?

A simple function chain:
```
retrieve() → grade() → answer()
```

But what if grading fails? What if you need to retry? What if you need human approval?

LangGraph lets you define a **graph** where:
- **Nodes** are functions (retrieve, grade, answer, call_tool)
- **Edges** are conditional (if relevant → answer, if not → retry)
- **State** is passed between nodes (TypedDict)

```python
from langgraph.graph import StateGraph

# Define state
class AgentState(TypedDict):
    query: str
    documents: list
    relevance_score: float
    answer: str

# Build graph
graph = StateGraph(AgentState)
graph.add_node("retrieve", retrieve_documents)
graph.add_node("grade", grade_relevance)
graph.add_node("answer", generate_answer)
graph.add_node("retry", reformulate_query)

# Define edges
graph.add_edge("retrieve", "grade")
graph.add_conditional_edges(
    "grade",
    lambda state: "answer" if state["relevance_score"] > 0.7 else "retry"
)
graph.add_edge("retry", "retrieve")  # Loop back
graph.add_edge("answer", END)
```

### CRAG (Corrective RAG)
The specific pattern we're implementing:
1. **Retrieve** documents
2. **Grade** relevance (Corrective step)
3. If bad → **Reformulate** query and retry (max 2x)
4. If good → **Answer** with citations
5. **Grade** faithfulness (another Corrective step)
6. If hallucinating → regenerate

---

## 10. JWT Authentication

### What Is a JWT?
A JSON Web Token is a self-contained credential:

```
Header.Payload.Signature

eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiYWRtaW4xIiwicm9sZSI6ImFkbWluIn0.abc123
```

**Header:** Algorithm used (HS256)
**Payload:** Claims (user_id, role, expiration)
**Signature:** HMAC of header + payload using a secret key

### Why JWT Over Sessions?
- **Stateless:** Server doesn't store anything. Token carries all info.
- **Scalable:** Any server can validate the token without shared memory.
- **Revocation problem:** Can't easily invalidate a JWT before expiration. (We solve this with short TTLs.)

### The Flow
```
1. User sends credentials to POST /login
2. Server validates credentials, creates JWT with claims:
   {user_id: "admin1", role: "admin", exp: 3600}
3. Server returns JWT to client
4. Client stores JWT in memory (not localStorage for security)
5. Client sends JWT in Authorization header: "Bearer <token>"
6. Server validates signature and expiration on every request
```

---

## 11. PII Redaction

### Why Redact Before AI Processing?
- **Compliance:** HIPAA, GDPR, CCPA require PII protection
- **Security:** Even if AI is local, PII in logs could leak
- **Best practice:** Strip PII before it reaches the LLM context

### What We Redact
```python
PII_PATTERNS = {
    "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
    "phone": r'\b(?:\+1)?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
    "credit_card": r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
}

# Input:  "Contact john@email.com or call 555-123-4567"
# Output: "Contact [EMAIL_REDACTED] or call [PHONE_REDACTED]"
```

### When It Happens
PII redaction runs as **middleware** on every request, BEFORE the query reaches the AI engine. The LLM never sees raw PII.

---

## 12. RBAC (Role-Based Access Control)

### The Concept
Not everyone should access everything. RBAC assigns **roles** to users, and **permissions** to roles.

```
End User:  Can ask questions, run predictions, see their own predictions
Expert:    Can do everything End User can + review/approve HITL actions, upload docs
Admin:     Can do everything + manage users, view audit logs, full reports
```

**Rule:** *never* grant permissions directly to a user — grant them to a **role**. This is the "R" in RBAC (Role-Based) and it keeps the permission matrix small.

### How It Works with Qdrant (Data-Level RBAC)
Every document stored in Qdrant gets an `rbac_label` in its payload:

```json
{
  "text": "Error 4012: insufficient funds",
  "rbac_label": "admin",  // Only admins can see this
  "source": "manual.pdf",
  "page": 42
}
```

When an End User queries Qdrant, the filter ensures they only see documents with `rbac_label` matching their role (or public docs). Admins see everything. This means security is enforced **inside the data store**, not only in the API — even if an End User crafted a request, the query returns nothing.

---

## 13. CRUD, Search, Filter & Pagination

### CRUD — The Four Basic Data Operations
Every database-backed app is built from these four verbs:

| Verb | Meaning | HTTP Method | SQL |
|------|---------|-------------|-----|
| **C**reate | Make a new record | POST | INSERT |
| **R**ead | Fetch record(s) | GET | SELECT |
| **U**pdate | Modify a record | PUT/PATCH | UPDATE |
| **D**elete | Remove a record | DELETE | DELETE |

University requirement: full CRUD on **3+ entities** (users, documents, prediction logs).

### Search, Filter, Pagination
As data grows, you can't dump all rows at once. Three standard query params:

```
GET /users?search=ali     → search "ali" in name/email
GET /users?role=admin     → filter by role
GET /users?page=2&size=10 → page 2, 10 rows per page
```

- **Search:** `WHERE name ILIKE '%ali%'`
- **Filter:** `WHERE role = 'admin'`
- **Pagination:** `LIMIT 10 OFFSET 20` + a `total` count so the UI can draw page numbers

**Why pagination matters:** fetching 45,211 bank-marketing records to show 10 is wasteful and slow. `LIMIT/OFFSET` fetches only what the user sees.

---

## 14. Circuit Breakers

### The Problem
User asks a question → Ollama is overloaded → 30-second wait → timeout error → terrible UX.

### The Solution
A circuit breaker monitors failures and trips when thresholds are exceeded:

```
CLOSED (normal):
  → Request goes to primary model
  → If success: reset failure count
  → If failure: increment failure count
  → If failures >= threshold: OPEN circuit

OPEN (broken):
  → All requests go to fallback model
  → After cooldown period: HALF-OPEN

HALF-OPEN (testing):
  → Send one test request to primary
  → If success: CLOSED
  → If failure: OPEN
```

**Why is this critical?** Because LLM inference can hang indefinitely. Without a circuit breaker, one bad model takes down your entire system.

---

## 15. Semantic Caching

### The Problem
Two users ask similar questions:
- "What does error 4012 mean?"
- "Explain error code 4012"

Without caching: 2 LLM calls (~10 seconds each)
With semantic caching: 1 LLM call + 1 vector similarity lookup (~100ms)

### How It Works
```python
# When answering a question:
1. Embed the query → vector
2. Search in-memory FAISS index for similar past queries
3. If cosine_similarity > 0.95: return cached answer (instant)
4. If no match: call LLM, cache the result with the query vector
```

**Why 0.95 threshold?** Too low (0.8) = wrong answers returned. Too high (0.99) = cache misses. 0.95 catches rephrased versions of the same question.

---

## 16. SSE (Server-Sent Events) Streaming

### The Problem
LLM generates 500 tokens. Without streaming, user waits 10 seconds seeing nothing. With streaming, they see text appear word-by-word.

### How SSE Works
```
Client: GET /api/chat (with Accept: text/event-stream)
Server: 
  event: token
  data: "Error"
  
  event: token  
  data: " 4012"
  
  event: token
  data: " means"
  
  event: done
  data: {"citations": [...], "trace_id": "abc123"}
```

**Protocol:** HTTP with `Content-Type: text/event-stream`. Server holds connection open and sends events as the LLM generates tokens.

---

## 17. OpenTelemetry

### The Three Pillars of Observability
1. **Logs:** What happened (discrete events)
2. **Metrics:** How much/often (numbers over time)
3. **Traces:** What path did a request take (the full story)

### LLM-Specific Traces
```
Trace: user_abc123 asked "What is error 4012?"
├── Span: PII Redaction (2ms)
├── Span: Semantic Cache Check (5ms) — MISS
├── Span: Query Embedding (45ms)
├── Span: Dense Search Qdrant (12ms) — 20 results
├── Span: Sparse Search Qdrant (8ms) — 20 results
├── Span: RRF Fusion (1ms)
├── Span: Cross-Encoder Re-ranking (150ms) — top 5
├── Span: Document Grading (30ms) — score: 0.92
├── Span: Answer Generation (3200ms) — 187 tokens
├── Span: Faithfulness Check (280ms) — score: 0.95
└── Span: Cache Store (2ms)
Total: 3705ms
```

**Phoenix** renders this as a waterfall chart so you can see exactly where time is spent.

---

## 18. Machine Learning Classification

### The Goal
Given a row of structured features (the Bank Marketing dataset), predict a **class label**: will the client subscribe to the premium product? (`yes`/`no`). This is **supervised binary classification**.

### The Dataset (Bank Marketing)
- 45,211 customer records
- 16 features: age, job, marital, education, balance, loan, contact, duration, campaign, previous...
- Target column: `y` = subscribed to a term deposit?

### The Two Models We Compare
| Model | Role | Why |
|-------|------|-----|
| **Logistic Regression** | Baseline | Simple, fast, interpretable, outputs clean probabilities |
| **XGBoost** | Main | Gradient-boosted trees — state of the art for tabular data |

The university requires a baseline **plus** at least one compared model with precision/recall/F1/confusion matrix for each.

### The Golden Rule: No Data Leakage
Split FIRST, preprocess AFTER:
```python
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
scaler.fit(X_train)      # scaler learns mean/std from TRAIN ONLY
X_train = scaler.transform(X_train)
X_test = scaler.transform(X_test)   # test transformed with TRAIN's scaler
```
If the scaler sees test data before training, the model has "seen the answers" — test scores will lie (look better than real-world performance).

### The Metrics You Must Explain
For each model we compute:

```
              Predicted NO   Predicted YES
Actual NO     TN            FP
Actual YES    FN            TP
```

- **Precision = TP / (TP + FP)** — of those we said "yes", how many were right? (precision-cares-about-false-positives)
- **Recall = TP / (TP + FN)** — of all actual "yes", how many did we catch?
- **F1 = harmonic mean of precision + recall** — balance between the two
- **Accuracy = (TP+TN) / total** — can mislead with imbalanced classes
- **Macro-F1** — average F1 over each class; robust when `yes` is rare (imbalance!)

### The Artifact (.joblib)
Training is expensive → do it ONCE, save the model to disk, load at API startup:

```python
joblib.dump(xgb_model, "ml/models/xgboost_v1.joblib")
```
At runtime the API loads the artifact (no retraining per request):
```python
model = joblib.load("ml/models/xgboost_v1.joblib")
prob = model.predict_proba([row])[0][1]   # → confidence
```

### Prediction Logging (University Requirement)
Every inference must be stored for auditability:
```
input_data, predicted_output, confidence, model_version, user_id, timestamp  → predictions table
```

**Salary vs. bag vs. candy (memorize this):** *Precision* = "of what the model said yes to, how much was gold?" (bag). *Recall* = "of all the gold there is, how much did the model find?" (net). There are videos with cats/dogs, but the bag/net analogy is what stays.

---

## 19. LLM-as-a-Judge

### The Problem
How do you know if your AI answers are good? Manual review doesn't scale.

### The Solution
Use a (stronger) LLM to evaluate your (weaker) LLM's answers:

```python
judge_prompt = """
Rate this answer on a scale of 1-5 for:
1. Faithfulness: Is the answer grounded in the provided context?
2. Relevance: Does the answer address the question?
3. Completeness: Is the answer thorough?

Context: {retrieved_documents}
Question: {user_query}
Answer: {generated_answer}

Output JSON: {"faithfulness": 4, "relevance": 5, "completeness": 3}
"""
```

### The Golden Dataset
```json
{
  "question": "What does error 4012 mean?",
  "expected_answer": "Error 4012 indicates a transaction declined due to insufficient funds.",
  "expected_sources": ["error_codes_manual.pdf#page=42"],
  "min_faithfulness": 4,
  "min_relevance": 4
}
```

Run this dataset against your API, average the scores, and you have a **quality gate** for CI/CD.

---

*These concepts will become concrete as you build each module. The theory here is reference material — come back to it when something doesn't make sense during implementation.*
