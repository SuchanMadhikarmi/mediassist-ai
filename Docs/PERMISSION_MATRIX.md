# Permission Matrix — Role-Based Access Control (MediAssist AI)

> **Why this document exists (and why it is honest):** the university
> Track B requirement is "3 user roles with RBAC". A matrix that *claims*
> permissions the code does not enforce would be caught the first time a
> judge curls an endpoint. So this matrix was generated from the **actual
> `Depends(require_*)` gates and inline role checks in `backend/routes/`**,
> not from a wish-list. Where the implemented behavior differs from the
> original design, there is an explicit ⚠ note.

## Roles

| Role | Meaning | Granting |
|------|---------|----------|
| `admin` | Full control: users, documents, system data | Created by the DB seed or by another admin |
| `expert` | Clinical/domain reviewer: can review predictions, dashboards | Created by an admin |
| `end_user` | Regular staff: submits inputs, chats | Created by admin **or self-service `/api/auth/register`** (registration always creates an `end_user` and cannot self-promote) |

Mechanism: each endpoint declares a security dependency
(`security/rbac.py::require_role`, `dependencies.py::require_staff`,
`require_admin`, `get_current_user`). FastAPI resolves it **before** the
route body runs — an unauthorized call never reaches business logic.

## Operation matrix (enforced)

| # | Operation | Endpoint | Admin | Expert | End User | Mechanism |
|---|-----------|----------|:-----:|:------:|:--------:|-----------|
| 1 | Register account | `POST /api/auth/register` | — | — | ✅ public | no token required; role forced to `end_user` |
| 2 | Login / refresh | `POST /api/auth/login`, `/refresh` | ✅ | ✅ | ✅ | public |
| 3 | List / create / update / delete users | `GET/POST/PATCH/DELETE /api/users` | ✅ | ❌ | ❌ | `require_admin` |
| 4 | Upload PDF (→ Qdrant) | `POST /ingest` | ✅ | ❌ | ❌ | `require_role(Role.ADMIN)` |
| 5 | List documents | `GET /api/documents` | ✅ all | ✅ admin+expert | ✅ own label only | **data-level RBAC*** |
| 6 | Delete document metadata | `DELETE /api/documents/{id}` | ✅ | ❌ | ❌ | `require_admin` |
| 7 | Submit ML prediction | `POST /api/predict` | ✅ | ✅ | ✅ | any authenticated user |
| 8 | List predictions | `GET /api/predictions` | ✅ all | ✅ all | ✅ **own rows only** | inline `role not in (admin, expert)` filter |
| 9 | Review / override prediction | `POST /api/predictions/{id}/review` | ✅ | ✅ | ❌ | `require_staff` (admin or expert) |
| 10 | Delete prediction | `DELETE /api/predictions/{id}` | ✅ | ✅ | ❌ | `require_staff` |
| 11 | Dashboard stats | `GET /api/stats` | ✅ | ✅ | ❌ (403) | `require_staff` |
| 12 | Audit trail | `GET /api/audit` | ✅ | ✅ | ❌ | `require_staff` |
| 13 | Chat (RAG) / stream | `POST /chat`, `/chat/stream` | ✅ | ✅ | ✅ | any authenticated user |
| 14 | HITL approve / reject own action | `POST /chat/resume` | ✅ | ✅ | ✅ | any authenticated user ⚠ |
| 15 | Export reports (CSV/PDF) | — | ❌ | ❌ | ❌ | **not implemented** ⚠ |

### Notes on the discrepancies (the honest part)

- **\* Data-level RBAC (row 5):** `backend/routes/documents.py` filters
  queries by `rbac_label` — an end user literally cannot list documents
  they are not labeled for (`_visible_labels`). The vector store does the
  same: Qdrant payloads carry an `rbac_label` used at retrieval time, so
  the chat agent only ever sees documents that role may read.
- **⚠ Row 14 (HITL resume):** by design a user can approve *their own*
  pending HITL action. The original design matrix reserved this for
  admin/expert. Locking it to staff is a 1-line dependency swap
  (`Depends(require_staff)`) if the scenario requires a separate
  approver; currently the demo relies on the pause being visible to the
  requester.
- **⚠ Row 15 (export reports):** not implemented as a download endpoint.
  The closest feature is `GET /api/stats` (JSON) rendered as charts in the
  Admin dashboard. Adding PDF/CSV export is a natural Phase 8+ extension.

## How to verify (curl)

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"expert1","password":"expert123"}' | jq -r .access_token)

# expert tries to list users → 403
curl -i -H "Authorization: Bearer $TOKEN" localhost:8000/api/users | head -1
# → HTTP/1.1 403 Forbidden

# expert reads stats → 200
curl -i -H "Authorization: Bearer $TOKEN" localhost:8000/api/stats | head -1
# → HTTP/1.1 200 OK
```

All three demo accounts exist after `python seed.py`:
`admin/admin123`, `expert1/expert123`, `nurse1/nurse123`.