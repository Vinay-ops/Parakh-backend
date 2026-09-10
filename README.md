# Parakh Backend

Backend for the **Parakh** product-label inspection app. It accepts package-label
images, stores them, records inspections, and (once the ML model is integrated)
persists extracted product information and compliance results.

```
Flutter Android App
        ↓ HTTPS
FastAPI Backend (Python)
        ↓
Supabase
 ├── Auth (Supabase Auth)
 ├── PostgreSQL (database)
 └── Storage (Supabase Storage)

Later (ML team):
FastAPI ──> ML Service ──> model
```

- **Language / framework:** Python 3.10+, FastAPI.
- **Database:** Supabase PostgreSQL (via SQLAlchemy 2 + psycopg2).
- **Authentication:** Supabase Auth only. The backend never issues its own JWT.
- **Storage:** Supabase Storage only (service-role credentials, backend-side).
- **Schema management:** Alembic migrations (see `migrations/`).

---

## Architecture

```
main.py                    FastAPI app, config validation, error handlers
api/                       Routers: auth, scan, inspections, complaints, dashboard, profile
services/                  Business logic: auth (Supabase), image (Supabase Storage),
                           inspection, complaint, ml (interface placeholder)
database/                  SQLAlchemy engine/session + models
schemas/                   Pydantic request/response models
middleware/                get_current_user (Supabase token validation)
migrations/                Alembic migrations (production schema)
tests/                     End-to-end API tests (Supabase mocked)
```

All user-owned data is scoped to the authenticated Supabase user id derived
from the validated access token — never from client-supplied values.

---

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in real values
```

### Local development without a full Supabase project

The backend is strict about configuration and will **fail fast** if required
environment variables are missing (there is no silent SQLite/local-storage
fallback). For local development you can point `DATABASE_URL` at a local
SQLite file and use any placeholder Supabase values, but features that call
Supabase Auth/Storage (login, scan upload) require a real project. The test
suite mocks Supabase entirely, so `pytest` needs no network access.

```bash
export DATABASE_URL=sqlite:///./parakh.db
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_ANON_KEY=<anon key>
export SUPABASE_SERVICE_ROLE_KEY=<service role key>
```

Run:

```bash
python -m alembic upgrade head      # create the schema
uvicorn main:app --reload           # local dev
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `SUPABASE_URL` | yes | Supabase project URL (e.g. `https://xyz.supabase.co`) |
| `SUPABASE_ANON_KEY` | yes | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | yes | Supabase service-role key — **backend only, never expose to Flutter** |
| `DATABASE_URL` | yes | PostgreSQL connection string for SQLAlchemy (Supabase pooler settings recommended) |
| `ALLOWED_ORIGINS` | no | Comma-separated exact browser origins for CORS. Mobile clients don't need it; leave empty in production |
| `MAX_IMAGE_SIZE_MB` | no | Scan image size limit (default `10`) |
| `SUPABASE_STORAGE_BUCKET` | no | Storage bucket name (default `product-images`) |

No `JWT_SECRET`/`JWT_TTL_MINUTES` are used — Supabase issues and validates
tokens. No local-upload variables are used in production.

## Supabase setup

1. **Auth:** enable Email provider (Dashboard → Authentication → Providers).
   Create users from the Auth dashboard or the Admin API — there is no
   registration endpoint in this backend (login only).
2. **Database:** run `python -m alembic upgrade head` with `DATABASE_URL`
   pointing at the Supabase PostgreSQL connection string. The initial migration
   creates `profiles`, `inspections`, `extracted_information`,
   `compliance_results`, and `complaints`, with foreign keys to
   `auth.users.id` and to `inspections.id`. `auth.users` itself is managed by
   Supabase; the migration only references it.
3. **Storage:** create a bucket named `product-images` (or set
   `SUPABASE_STORAGE_BUCKET`), **public-read** so Flutter can display the
   returned image URLs directly. Files are uploaded by the backend with the
   service-role key under `<user_id>/<random>.png|jpg|webp`.

> The service-role key must never be embedded in or returned to the Flutter
> app. All Supabase calls that need elevated access happen server-side.

## Authentication flow

```
Flutter ──> Supabase Auth (direct, or via POST /api/auth/login)
        ──> receives Supabase access token
        ──> sends: Authorization: Bearer <supabase_access_token>
        ──> FastAPI validates the token with Supabase (GET /auth/v1/user)
        ──> derives user_id and authorizes the request
```

- **Login:** `POST /api/auth/login` proxies to Supabase
  (`grant_type=password`) and returns the Supabase session
  (`access_token`, `refresh_token`, `expires_in`, `token_type`, `user_id`,
  `email`). Flutter may instead call Supabase Auth directly and just send the
  resulting token — both work, because the backend only ever validates the
  Supabase token.
- **Session check:** `GET /api/auth/me` returns the authenticated user for the
  presented token — use it to verify/restore sessions.
- There is **no registration endpoint**. Accounts are provisioned in Supabase.

## API endpoints

All endpoints return the envelope:

```json
{ "success": true, "data": {}, "message": "..." }
```

Errors:

```json
{ "success": false, "data": null, "message": "...", "error_code": "..." }
```

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | no | Liveness + DB connectivity (503 `DB_UNAVAILABLE` if down) |
| POST | `/api/auth/login` | no | Supabase login proxy → session |
| GET | `/api/auth/me` | bearer | Current user from token |
| POST | `/api/scan` | bearer | Upload image → inspection (ML pending) |
| POST | `/api/inspections` | bearer | Create manual inspection |
| GET | `/api/inspections` | bearer | List (filters/pagination, user-scoped) |
| GET | `/api/inspections/{inspection_id}` | bearer | Inspection detail |
| GET | `/api/inspections/{inspection_id}/extracted-info` | bearer | Extracted product info (404 until ML) |
| GET | `/api/inspections/{inspection_id}/compliance` | bearer | Compliance summary + rules |
| POST | `/api/complaints` | bearer | Create complaint |
| GET | `/api/complaints` | bearer | List complaints (user-scoped) |
| GET | `/api/complaints/{complaint_id}` | bearer | Complaint detail |
| PATCH | `/api/complaints/{complaint_id}` | bearer | Update complaint (status: `OPEN`, `UNDER_REVIEW`, `RESOLVED`, `REJECTED`) |
| GET | `/api/dashboard` | bearer | Real aggregate statistics |
| GET | `/api/profile` | bearer | Profile (auto-created) |
| PATCH | `/api/profile` | bearer | Update profile (identity fields are not client-updatable) |

See the **Flutter API integration** section below for request/response shapes.

## Production deployment

Standard Python/FastAPI deployment:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

- The app **fails fast** at startup if `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
  `SUPABASE_SERVICE_ROLE_KEY`, or `DATABASE_URL` are missing.
- Apply the schema first: `python -m alembic upgrade head`.
- Health checks: `GET /api/health` (returns `503` while the database is
  unreachable).
- CORS: leave `ALLOWED_ORIGINS` unset for mobile-only deployments; set exact
  origins only if a browser client exists.

## Flutter API integration

Authorization header for every authenticated call:

```
Authorization: Bearer <supabase_access_token>
```

Key contracts:

- **Login** `POST /api/auth/login` — body `{"email", "password"}` → data:
  `{"access_token", "refresh_token", "expires_in", "token_type", "user_id", "email"}`.
- **Scan** `POST /api/scan` — multipart form: `image` (JPEG/PNG/WebP,
  ≤ `MAX_IMAGE_SIZE_MB`, magic bytes verified), optional `product_name`,
  `product_category` → data: `{"inspection_id", "image_url", "status",
  "ml_pending"}`. Until ML is integrated, `status` is `PENDING_ML` and
  `ml_pending` is `true`; `GET .../extracted-info` returns `404
  NO_EXTRACTED_INFO` and `GET .../compliance` returns an empty `rules` list.
- **Inspections list** `GET /api/inspections?status=&category=&date_from=
  &date_to=&page=&page_size=` → `{"items": [...], "total", "page",
  "page_size"}`.
- **Compliance** `GET /api/inspections/{id}/compliance` →
  `{"inspection_id", "status", "score", "rules": [{"rule_name", "status",
  "reason", "required_value", "detected_value", "bounding_box"}]}`.
- **Dashboard** `GET /api/dashboard` →
  `{"total_inspections", "total_complaints", "reviewed_complaints",
  "pending_complaints", "recent_inspections": [...]}` — computed from real
  data, scoped to the user.

Internal identifiers: primary keys are UUIDs; the API additionally exposes
human-readable public ids (`INSP-...`, `CMP-...`) for display and lookups.
Relationships stored in the database always use the internal UUID.

Response envelope for every endpoint (including `GET /api/health`):

```json
{ "success": true, "data": {}, "message": "..." }
```

`ComplaintOut.inspection_id` is the public `INSP-XXXXXXXX` identifier
(not an internal UUID), so Flutter can use it directly with
`GET /api/inspections/{inspection_id}`.

`GET /api/profile` → `data.email` is populated automatically from the
authenticated Supabase token; it is not client-settable via `PATCH /api/profile`.

## ML integration interface

`services/ml_service.py` defines the integration point. `process_image(
image_path) -> dict` is a placeholder that raises `NotImplementedError` until
the model is integrated; the endpoint handles this by keeping the inspection
in `PENDING_ML`. See **[docs/ML_INTEGRATION.md](docs/ML_INTEGRATION.md)** for
the exact contract (input, output structure, validation, persistence).

## Tests

```bash
python -m pytest tests/ -q
```

The suite mocks Supabase Auth and Storage, builds the schema through the real
Alembic migration, and covers auth, scan validation, inspections, complaints,
dashboard, profile, cross-user isolation, error envelopes, and database
failure handling. No ML model is required.