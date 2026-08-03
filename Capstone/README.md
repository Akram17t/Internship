# ICS SOP & Knowledge Assistant

RAG-based internal document assistant for SOP, guideline, and runbook search, with a custom web frontend served directly from FastAPI.

System flow diagrams are in [docs/SYSTEM_FLOWS.md](docs/SYSTEM_FLOWS.md).

## Stack

- FastAPI for REST backend and frontend hosting
- Vanilla HTML, CSS, and JavaScript for the web UI
- OpenAI-compatible chat, FAQ, and document chunk generation, defaulting to 9Router with Kiro for chat
- Nscale OpenAI-compatible API for hosted embeddings
- ChromaDB for local vector storage

## Quick Start

1. Create a virtual environment and install dependencies from `requirements.txt`.
2. Copy `.env.example` to `.env`, run 9Router locally or set another OpenAI-compatible `CHAT_BASE_URL`, then set `CHAT_API_KEY` if your endpoint requires it and `NSCALE_SERVICE_TOKEN`.
3. Start the local PostgreSQL container and apply migrations (app state and analytics require PostgreSQL -- there is no SQLite fallback):

```bash
docker compose -f docker-compose.dev-db.yml up -d
python -m alembic -c alembic.ini upgrade head
```

4. Put SOP/knowledge PDF or DOCX files into `backend/data/`; form templates can be PDF, Word, or Excel files. Forms uploaded below an SOP in the admin UI do not need a `Form` filename prefix.
5. Run ingestion:

```bash
python -m backend.preprocessing.ingest
```

6. Start the API:

```bash
uvicorn backend.api.main:app --reload
```

7. Open `http://127.0.0.1:8000` in your browser.

`run.bat` (see below) automates steps 3, 5, and 6.

## Windows Scripts

For the easiest Windows flow, use:

```bat
run.bat
clean.bat
```

- `run.bat` uses `backend\researcher_crew\.venv`, checks the required imports, starts the local PostgreSQL dev container if it isn't already running, reads `CHROMA_DIR` and `DATA_DIR` from `.env`, runs ingestion only when no valid vector index exists, then starts FastAPI and opens the web frontend in your browser.
- `clean.bat` stops the server, removes `__pycache__`, `.pytest_cache`, and `*.pyc`, and clears the `CHROMA_DIR` vector index (keeping `.gitkeep`) so the next `run.bat` re-ingests documents.

## Docker Deployment

For a single-container VPS deployment, use the provided Dockerfile and
`docker-compose.yml`. Runtime data is stored in the named Docker volume
`app_storage`, mounted at `/app/storage` inside the container.

1. Copy the production env template and fill in the API keys. `.env.production`
   is git-ignored -- it holds real secrets, so it's created locally per
   environment (dev machine, EC2) and never committed:

```bash
cp .env.production.example .env.production
```

2. Confirm the production storage paths stay on `/app/storage`, and keep the
   internal 9Router service URL on the Compose network:

```env
MODEL=kr/claude-sonnet-4.5
CHAT_BASE_URL=http://9router:20129/v1
CHAT_API_KEY=
OPENAI_COMPAT_NO_AUTH_BASE_URLS=http://9router:20129/v1
CHUNK_AI_MAX_COMPLETION_TOKENS=16384
DATA_DIR=/app/storage/data
CHROMA_DIR=/app/storage/chroma_db
SEMANTIC_CACHE_DIR=/app/storage/semantic_chroma
JWT_SECRET=<fixed-random-secret>
API_KEY_SECRET=<fixed-random-secret>
DATABASE_URL=<postgresql+psycopg://user:password@host:5432/dbname>
ANALYTICS_PSEUDONYM_SECRET=<fixed-random-secret>
```

App state (conversations, admin accounts, activity logs, FAQs, semantic cache
metadata) and analytics live in PostgreSQL, not in `app_storage` -- point
`DATABASE_URL` at a reachable Postgres instance (RDS, a managed EC2 install,
or the local dev container in `docker-compose.dev-db.yml`) and apply schema
migrations before starting the app:

```bash
python -m alembic -c alembic.ini upgrade head
```

The Compose file runs 9Router plus an internal loopback proxy. Capstone calls
port `20129`, which forwards to 9Router through `127.0.0.1` inside the router
network namespace, so no API key is needed for app-to-router traffic. Only the
dashboard/API port `20128` is bound to EC2 localhost. Keep it closed publicly
and use an SSH tunnel for dashboard access. The existing `/home/ec2-user/.9router`
data directory remains mounted so the Kiro connection survives rebuilds.
Keep `CHAT_API_KEY` blank for this internal 9Router
setup. The app treats `localhost:20128`, `localhost:20129`, `9router:20128`,
and `9router:20129` as no-auth 9Router endpoints and will not fall back to a
global `OPENAI_API_KEY` for them.

3. Build and start the app:

```bash
docker compose build
docker compose up -d
```

To rebuild and validate the complete deployment on EC2:

```bash
bash deploy/update-ec2.sh
```

If the EC2 9Router database has no Kiro account, connect it directly with the
AWS Builder ID device flow:

```bash
bash deploy/connect-kiro-ec2.sh
```

4. Add source documents to the `DATA_DIR` volume path, then run ingestion:

```bash
docker compose run --rm app python -m backend.preprocessing.ingest
```

Ingestion also writes the exact chunks sent to embeddings into
`debug/chunks.md` next to the configured `DATA_DIR`. Locally this is
`backend/debug/chunks.md`; in Docker deployment this is
`/app/storage/debug/chunks.md`.

5. Inspect logs when needed:

```bash
docker compose logs app
```

6. On EC2 or a VPS, put Nginx in front of the app so the public URL can use
   port 80 while Docker stays bound to localhost:

```bash
sudo dnf install -y nginx
sudo systemctl enable --now nginx
sudo cp deploy/nginx/hr-agent.conf /etc/nginx/conf.d/hr-agent.conf
sudo nginx -t
sudo systemctl reload nginx
```

Then open:

```text
http://PUBLIC_SERVER_IP
```

For this setup, expose `HTTP 80` in the cloud firewall/security group. Keep
`SSH 22` limited to your IP, and keep Docker port `8000` closed to the public.

The container starts FastAPI with the production command:

```bash
python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

Important persistent data in `app_storage`:

- `data/`: uploaded/source documents
- `chroma_db/`: vector database index
- `semantic_chroma/`: semantic answer cache

Admin accounts, sessions, activity logs, FAQs, and semantic cache metadata
live in PostgreSQL (see `DATABASE_URL` above), not in `app_storage`.

## Testing

```bash
pytest
```

Tests run against a dedicated `hr_agent_test` PostgreSQL database on the same
server as `DATABASE_URL` (see `conftest.py`), never against your own dev data.
The database and current table shape are created automatically on first run;
each test truncates all tables beforehand for isolation. Requires the local
PostgreSQL container to be running (`docker compose -f docker-compose.dev-db.yml up -d`).

## Frontend Config

- `TYPING_ANIMATION_ENABLED=false` shows full answers immediately by default.
- Set `TYPING_ANIMATION_ENABLED=true` to restore the assistant typing reveal.

## Langfuse Observability

The backend can send RAG traces to Langfuse Cloud. Set these values in the
local `.env` file only:

```env
LANGFUSE_TRACING_ENABLED=true
LANGFUSE_PUBLIC_KEY=<project-public-key>
LANGFUSE_SECRET_KEY=<project-secret-key>
LANGFUSE_BASE_URL=https://jp.cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=development
LANGFUSE_TRACE_IO_MODE=masked
```

Each `/query` request creates one `chat-query` trace, grouped by conversation
session. The trace includes context resolution (LangGraph-based, replacing
follow-up query rewriting), cache, retrieval, generation, semantic
cache store, and response finalization observations. `masked` mode redacts
common secrets, contact details, and large image data before export.

## Frontend Pages

- `Chat`: main conversational interface connected to `POST /query`
- `FAQ`: curated operational starter questions
- `Library`: admin document/form list with download links from `backend/data`
- Form templates: direct download only, with PDF/Word/Excel format choices based on the uploaded file

## Frontend Scripts

The frontend is still plain browser JavaScript without a bundler. `frontend/web/assets/app.js`
is now the bootstrap/glue file, while feature logic lives in small global modules:

- `assets/js/chat.js`: chat submit/rendering, citations, and form links
- `assets/js/faq.js`, `assets/js/library.js`, `assets/js/auth.js`, `assets/js/api.js`, `assets/js/markdown.js`: FAQ, document admin, auth bindings, API helpers, and markdown rendering

## Structure

```text
Capstone/
|-- backend/
|   |-- api/              # FastAPI routes and frontend hosting
|   |-- researcher_crew/  # RAG answer generation and retrieval helpers
|   |-- preprocessing/    # ingestion, loaders, chunking, embeddings, vectorstore
|   |-- analytics/        # topic classification and daily aggregate refresh
|   |-- db/               # SQLAlchemy models, engine, PostgreSQL repository, Alembic migrations
|   |-- scripts/          # small command-line helpers used by Windows scripts
|   |-- data/             # source documents
|   `-- chroma_db/        # persisted vector database
|-- frontend/
|   |-- web/              # static web frontend (HTML/CSS/JS modular globals)
|   `-- dashboard/        # React/Vite source for the analytics dashboard, built into frontend/web/assets/dashboard
|-- deploy/               # EC2 deployment and Kiro connection scripts, nginx config
|-- docs/                 # system flow diagrams, admin guide
|-- tests/, backend/tests/  # pytest suites
|-- docker-compose.yml, docker-compose.dev-db.yml, Dockerfile
|-- alembic.ini
|-- .env.example
|-- README.md
|-- clean.bat
|-- run.bat
`-- requirements.txt
```
