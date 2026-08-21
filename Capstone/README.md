# HR Assistant — ICS SOP & Knowledge Assistant

Internal HR knowledge assistant developed as an internship capstone project at ICS Compute. The application uses Retrieval-Augmented Generation (RAG) to answer questions from company SOPs, policies, guidelines, and organizational documents. Answers can include source citations and related downloadable form templates.

> This repository contains application source code and technical documentation. Company source documents under `backend/data/` are intended for authorized internal review only.

## Highlights

- RAG chat with source citations, conversation history, follow-up context resolution, and safe fallback responses.
- LangGraph-based context resolution that decides whether a message requires document retrieval.
- Semantic answer cache populated only after positive user feedback.
- Document library for SOPs and related PDF, Word, or Excel form templates.
- Google Workspace sign-in with user/admin role separation and 12-hour signed sessions.
- Admin tools for documents, reindexing, FAQs, guardrails, activity logs, feedback review, and account management.
- Usage analytics with date filters, topic distribution, trends, active users, and negative-feedback metrics.
- Bilingual English/Indonesian interface; assistant responses follow the language of the question.
- Optional Langfuse tracing with masked input/output data.
- Local Windows workflow and single-host Docker/EC2 deployment scripts.

## Architecture

```mermaid
flowchart LR
    U[User or Admin Browser] --> API[FastAPI]
    API --> AUTH[Google Sign-In]
    API --> PG[(PostgreSQL)]
    API --> RAG[LangGraph Context + RAG Pipeline]
    RAG --> DOCS[(ChromaDB Document Index)]
    RAG --> CACHE[(ChromaDB Cache Vectors)]
    RAG --> LLM[9Router / OpenAI-compatible Chat API]
    DOCS --> EMBED[Nscale Embeddings]
    CACHE --> EMBED
    API --> WEB[Vanilla JS Web App]
    WEB --> DASH[Embedded React Analytics Dashboard]
```

The document index is stored in ChromaDB. Semantic-cache answer metadata is stored in PostgreSQL while its similarity-search vectors are stored in a separate ChromaDB collection. PostgreSQL is the source of truth for users, admin accounts, conversations, messages, FAQs, logs, guardrails, analytics, and cache metadata.

For detailed diagrams and runtime flows, see:

- [`docs/SYSTEM_FLOWS.md`](docs/SYSTEM_FLOWS.md)
- [`docs/architecture.pdf`](docs/architecture.pdf) and its source, [`docs/architecture.tex`](docs/architecture.tex)
- [`docs/admin-guide/admin_guide.pdf`](docs/admin-guide/admin_guide.pdf) and its source, [`docs/admin-guide/admin_guide.tex`](docs/admin-guide/admin_guide.tex)

## Technology Stack

| Area | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| RAG orchestration | LangGraph, LangChain loaders/splitters |
| Database | PostgreSQL 16, SQLAlchemy 2, Alembic |
| Vector storage | Persistent local ChromaDB |
| Chat completion | 9Router/Kiro by default, or another OpenAI-compatible endpoint |
| Embeddings | Nscale OpenAI-compatible API |
| User frontend | Vanilla HTML, CSS, and modular JavaScript |
| Analytics dashboard | React 19, TypeScript, Vite, Recharts, Tailwind CSS 4 |
| Authentication | Google ID token verification and signed application sessions |
| Observability | Langfuse 4 (optional) |
| Deployment | Docker Compose, Nginx, AWS EC2 scripts |

## Repository Layout

```text
Capstone/
|-- backend/
|   |-- api/                 # FastAPI app, routes, auth, storage, request models
|   |-- analytics/           # Topic classification and aggregate refresh
|   |-- db/                  # SQLAlchemy models, repository, Alembic migrations
|   |-- preprocessing/       # Load, describe, chunk, embed, and index documents
|   |-- researcher_crew/src/ # Context graph, retrieval, prompts, answer generation
|   |-- scripts/             # Storage checks and maintenance helpers
|   |-- data/                # Authorized source documents and linked forms
|   |-- semantic_cache.py    # PostgreSQL + Chroma semantic answer cache
|   `-- observability.py     # Optional Langfuse integration
|-- frontend/
|   |-- web/                 # Main static SPA served by FastAPI
|   `-- dashboard/           # React/Vite analytics source
|-- tests/                   # Backend and frontend-integration tests
|-- deploy/                  # EC2 update, Kiro connection, and Nginx config
|-- docs/                    # Architecture, system flows, and admin guide
|-- .env.example             # Safe local configuration template
|-- .env.production.example  # Safe production configuration template
|-- alembic.ini
|-- docker-compose.dev-db.yml
|-- docker-compose.yml
|-- Dockerfile
|-- requirements.txt
|-- run.bat / clean.bat
`-- README.md
```

## Prerequisites

Required for local development:

- Python 3.12
- Docker Desktop with Docker Compose (for PostgreSQL)
- A configured OpenAI-compatible chat endpoint; the default local setup expects 9Router at `http://localhost:20128/v1`
- An Nscale service token for embeddings
- A Google OAuth client ID configured for the local application origin

Optional:

- Node.js and npm, only when rebuilding or developing the React analytics dashboard
- A LaTeX distribution, only when regenerating the PDF documentation
- `pytest`, only when running the test suite (it is not a production dependency)

## Local Setup

### 1. Create the Python environment

`run.bat` expects the virtual environment at `backend/researcher_crew/.venv`.

**Windows PowerShell or Command Prompt:**

```bat
py -3.12 -m venv backend\researcher_crew\.venv
backend\researcher_crew\.venv\Scripts\python -m pip install --upgrade pip
backend\researcher_crew\.venv\Scripts\python -m pip install -r requirements.txt
```

**Linux/macOS:**

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Configure the environment

Create a local configuration from the safe template:

```bat
copy .env.example .env
```

```bash
cp .env.example .env
```

At minimum, review and set:

```env
MODEL=kr/claude-sonnet-4.5
CHAT_BASE_URL=http://localhost:20128/v1
CHAT_API_KEY=
NSCALE_SERVICE_TOKEN=<your-token>
GOOGLE_CLIENT_ID=<your-google-client-id>
INITIAL_ADMIN_EMAIL=<first-admin@your-domain>
ANALYTICS_PSEUDONYM_SECRET=<random-secret>
DATABASE_URL=postgresql+psycopg://hr_agent:hr_agent_dev_password@localhost:5432/hr_agent
```

If the chat endpoint does not require authentication, list it in `OPENAI_COMPAT_NO_AUTH_BASE_URLS`. Never put real credentials in `.env.example`.

### 3. Start PostgreSQL and apply migrations

```bash
docker compose -f docker-compose.dev-db.yml up -d
python -m alembic -c alembic.ini upgrade head
```

On Windows, use the virtual-environment Python if it is not activated:

```bat
backend\researcher_crew\.venv\Scripts\python -m alembic -c alembic.ini upgrade head
```

PostgreSQL is required. There is no SQLite fallback.

### 4. Add and index documents

Place embeddable `.pdf`, `.docx`, or `.txt` files in `DATA_DIR` (default: `backend/data/`). Linked form templates may be PDF, Word, or Excel files under the appropriate `forms/` subfolder or can be uploaded through the admin UI.

```bash
python -m backend.preprocessing.ingest
```

Ingestion:

1. loads supported non-form documents;
2. adds optional diagram descriptions for likely visual PDF pages;
3. generates AI-assisted chunks, with a local splitter fallback;
4. creates embeddings and atomically activates a new ChromaDB index;
5. writes chunk diagnostics to `backend/debug/chunks.md`; and
6. clears the old semantic cache after a successful reindex.

### 5. Start the application

```bash
python -m uvicorn backend.api.main:app --reload
```

Open `http://127.0.0.1:8000`.

Interactive API documentation is available at `http://127.0.0.1:8000/docs` while the app is running.

## Windows Helper Scripts

After the first database migration is applied, the easiest Windows workflow is:

```bat
run.bat
```

`run.bat`:

- uses `backend/researcher_crew/.venv`;
- verifies required imports;
- starts the local PostgreSQL container when necessary;
- checks that the migrated database schema is ready;
- reuses an existing valid vector index or runs ingestion when source documents exist; and
- starts FastAPI on port `8000` and opens the browser.

Cleanup:

```bat
clean.bat
```

`clean.bat` stops the local server, removes Python bytecode caches, and clears the local document-vector index so the next run can re-ingest documents. It does not delete PostgreSQL data.

## Frontend Development

### Main web application

The main UI is a static SPA in `frontend/web/`. `assets/app.js` initializes the application, while feature modules are organized under `assets/js/`:

- `chat.js`, `markdown.js`, `citations.js`: chat, rendering, source citations, and form downloads
- `auth.js`, `googleAuth.js`, `api.js`: session, Google sign-in, and request helpers
- `sidebar.js`: conversation list, rename, and delete behavior
- `faq.js`, `library.js`: FAQ and document/form management
- `logs.js`, `analytics.js`, `guardrails.js`: admin monitoring and configuration
- `i18n.js`: English/Indonesian interface text

No bundler is required for these files.

### React analytics dashboard

React source lives in `frontend/dashboard/`. The generated bundle is embedded into the main app at `frontend/web/assets/dashboard/`.

```bash
cd frontend/dashboard
npm ci
npm run lint
npm run build
```

The Vite build intentionally emits fixed filenames (`dashboard.js` and `dashboard.css`) and removes the standalone development `index.html` from production output so the dashboard remains behind the main application's sign-in gate.

For dashboard-only development:

```bash
npm run dev
```

Vite proxies `/api` requests to `http://127.0.0.1:8000`.

## Configuration Reference

### Required runtime configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL SQLAlchemy connection string |
| `MODEL` | Chat-completion model identifier |
| `CHAT_BASE_URL` | OpenAI-compatible chat endpoint |
| `NSCALE_SERVICE_TOKEN` | Nscale embedding credential |
| `EMBED_MODEL` | Embedding model identifier |
| `RERANK_MODEL` | Optional cross-encoder model name when the extra runtime dependency is available |
| `GOOGLE_CLIENT_ID` | Google ID-token audience and frontend sign-in client |

### Common application settings

| Variable | Default / role |
|---|---|
| `DATA_DIR` | `backend/data`; source documents and forms |
| `CHROMA_DIR` | `backend/chroma_db`; active document vectors |
| `CHUNK_CACHE_DIR` | `backend/cache/chunks`; AI chunk cache |
| `SEMANTIC_CACHE_DIR` | `backend/cache/semantic_chroma`; cache similarity vectors |
| `TOP_K` | Number of final retrieved chunks |
| `RETRIEVAL_MIN_SCORE` | Minimum accepted reranker score |
| `SEMANTIC_CACHE_THRESHOLD` | Cache-hit similarity threshold |
| `ALLOWED_EMAIL_DOMAIN` | Allowed Google Workspace domain |
| `INITIAL_ADMIN_EMAIL` | Seeds the first admin if no admin account exists |
| `ANALYTICS_PSEUDONYM_SECRET` | HMAC secret for stable pseudonymous analytics IDs |
| `TYPING_ANIMATION_ENABLED` | Enables/disables answer reveal animation |

See [`.env.example`](.env.example) and [`.env.production.example`](.env.production.example) for the complete safe templates.

## Main API Endpoints

All protected endpoints expect `Authorization: Bearer <session-token>`, except browser download routes which also accept a short-lived session token through their query string fallback.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Basic process health |
| `GET` | `/api/config` | Public frontend configuration |
| `POST` | `/api/auth/google` | Exchange a Google ID token for an application session |
| `POST` | `/query` | Run context resolution, cache lookup, retrieval, and answer generation |
| `POST` | `/api/feedback` | Record positive/negative answer feedback |
| `GET` | `/api/faq` | List published FAQs |
| `GET` | `/api/library` | List authorized documents and forms |
| `GET` | `/api/documents/{path}` | Download a document or form template |
| `GET` | `/api/citations/{path}` | Open a cited source document |
| `GET/PATCH/DELETE` | `/api/conversations/...` | List, read, rename, or delete user conversations |
| `POST/DELETE` | `/api/admin/documents...` | Upload, replace, or delete managed documents/forms |
| `POST` | `/api/admin/reindex` | Rebuild the document-vector index |
| `POST/PUT/DELETE` | `/api/admin/faq...` | Manage FAQ content |
| `GET/PUT` | `/api/admin/guardrails` | Read or update answer guardrails |
| `GET/DELETE` | `/api/admin/logs...` | Review or delete activity logs/sessions |
| `GET/POST` | `/api/admin/analytics/...` | Query or refresh usage analytics |

FastAPI's generated `/docs` page is the authoritative endpoint/schema reference.

## Tests and Validation

The full test suite expects a reachable, migrated **disposable PostgreSQL database** through `DATABASE_URL`. Never point tests at development or production data.

> **Current test-isolation limitation:** `test_admin_auth.py` and `test_admin_logs.py` expect empty tables but do not reset PostgreSQL state between every test case. The application checks and non-DB tests pass, but these DB-heavy modules require a table reset/isolation fixture between cases for a completely clean full-suite run.

```bash
docker compose -f docker-compose.dev-db.yml up -d
python -m alembic -c alembic.ini upgrade head
python -m pytest -q
```

Frontend dashboard checks:

```bash
cd frontend/dashboard
npm ci
npm run lint
npm run build
```

Docker configuration/build checks:

```bash
docker compose config
docker compose build
```

## Single-Host Docker Deployment

The production Compose file starts the application, 9Router, and a loopback proxy. PostgreSQL is not declared in `docker-compose.yml`; `DATABASE_URL` must point to a reachable migrated PostgreSQL instance. The audited EC2 environment described in `docs/architecture.pdf` used a PostgreSQL container on the same host, but a managed database is also compatible.

1. Create a production configuration:

   ```bash
   cp .env.production.example .env.production
   ```

2. Fill all credentials and stable secrets. Keep production storage paths under `/app/storage` and keep the internal chat URL at `http://9router:20129/v1`.

3. Validate, build, and start:

   ```bash
   docker compose config
   docker compose up -d --build
   ```

4. Apply database migrations:

   ```bash
   docker compose exec app python -m alembic -c alembic.ini upgrade head
   ```

5. Add source documents to the configured volume and run ingestion:

   ```bash
   docker compose run --rm app python -m backend.preprocessing.ingest
   ```

6. Inspect logs and health:

   ```bash
   docker compose logs app
   curl http://127.0.0.1:8000/health
   ```

For the existing EC2 workflow, `deploy/update-ec2.sh` backs up configuration, rebuilds services, runs Alembic, validates 9Router/model access, and polls application health. `deploy/connect-kiro-ec2.sh` supports the AWS Builder ID device flow for the host-side 9Router account. Nginx configuration is provided at `deploy/nginx/hr-agent.conf`.

The repository configuration exposes the application and 9Router dashboard only on host loopback. Use Nginx or an SSH tunnel as appropriate, restrict security-group access, and add TLS before exposing the service beyond a trusted internal network.

## Langfuse Observability

Tracing is optional and fail-open. Configure it only in local/private environment files:

```env
LANGFUSE_TRACING_ENABLED=true
LANGFUSE_PUBLIC_KEY=<project-public-key>
LANGFUSE_SECRET_KEY=<project-secret-key>
LANGFUSE_BASE_URL=https://your-langfuse-host
LANGFUSE_TRACING_ENVIRONMENT=development
LANGFUSE_TRACE_IO_MODE=masked
```

Each `/query` can produce a `chat-query` trace covering context resolution, semantic cache, retrieval, generation, cache storage, and response finalization. `masked` mode redacts common secret/contact patterns and large image payloads before export.

## Safe Distribution Checklist

Before sharing this project as a ZIP or copying it outside the development machine:

**Include:** source code, tests, safe `.example` environment templates, source documents authorized for the recipient, frontend assets/source, deployment scripts, migrations, and documentation (including admin-guide screenshots).

**Exclude:**

- `.env` and `.env.production`
- `.git/`, `.venv/`, `node_modules/`
- `__pycache__/`, `*.pyc`, `.pytest_cache/`, `*.tsbuildinfo`
- local Chroma/vector indexes and semantic/chunk caches
- generated ingestion diagnostics such as `backend/debug/chunks.md`
- deployment backups, process markers, editor state, and transient logs

Never replace the safe `.env.example` files with real credentials. Rotate any credential immediately if it is accidentally included in an archive or commit.

## Current Limitations

- The provided deployment is single-host and has no built-in high availability.
- Document and cache vector stores are local persistent ChromaDB directories, so horizontal app scaling requires shared/managed storage or a different vector backend.
- The application has no built-in rate limiter or server-side session revocation list.
- The basic `/health` endpoint does not verify every external dependency.
- Nginx configuration currently provides HTTP reverse proxying only; TLS termination must be added for broader use.

## Project Context

Capstone project for the ICS Compute internship program, developed and documented by Akram. This repository is intended for project review and authorized internal use.
