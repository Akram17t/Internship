# ICS SOP & Knowledge Assistant

RAG-based internal document assistant for SOP, guideline, and runbook search, with a custom web frontend served directly from FastAPI.

Architecture and design docs, including a topology diagram, are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Stack

- FastAPI for REST backend and frontend hosting
- Vanilla HTML, CSS, and JavaScript for the web UI
- Direct Groq LLM calls for chat, FAQ generation, and flowchart vision extraction
- Nscale OpenAI-compatible API for hosted embeddings
- ChromaDB for local vector storage

## Quick Start

1. Create a virtual environment and install dependencies from `requirements.txt`.
2. Copy `.env.example` to `.env`, then set `GROQ_API_KEY` and `NSCALE_SERVICE_TOKEN`.
3. Put SOP/knowledge PDF or DOCX files into `backend/data/`; form templates should be PDF files with filenames starting with `Form`. The backend creates matching DOCX templates automatically.
4. Run ingestion:

```bash
python -m backend.preprocessing.ingest
```

5. Start the API:

```bash
uvicorn backend.api.main:app --reload
```

6. Open `http://127.0.0.1:8000` in your browser.

## Windows Scripts

For the easiest Windows flow, use:

```bat
run.bat
clean.bat
```

- `run.bat` uses `backend\researcher_crew\.venv`, checks the required imports, reads `CHROMA_DIR` and `DATA_DIR` from `.env`, runs ingestion only when no valid vector index exists, then starts FastAPI and opens the web frontend in your browser.
- `clean.bat` stops the server, removes `__pycache__`, `.pytest_cache`, and `*.pyc`, and clears the `CHROMA_DIR` vector index (keeping `.gitkeep`) so the next `run.bat` re-ingests documents.

## Docker Deployment

For a single-container VPS deployment, use the provided Dockerfile and
`docker-compose.yml`. Runtime data is stored in the named Docker volume
`app_storage`, mounted at `/app/storage` inside the container.

1. Copy the production env template and fill in the API keys:

```bash
cp .env.production.example .env.production
```

2. Confirm the production storage paths stay on `/app/storage`:

```env
APP_STATE_DB=/app/storage/app_state.db
DATA_DIR=/app/storage/data
CHROMA_DIR=/app/storage/chroma_db
SEMANTIC_CACHE_DIR=/app/storage/semantic_chroma
```

3. Build and start the app:

```bash
docker compose build
docker compose up -d
```

4. Add source documents to the `DATA_DIR` volume path, then run ingestion:

```bash
docker compose run --rm app python -m backend.preprocessing.ingest
```

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

- `app_state.db`: admin accounts, sessions state, activity logs, and app state
- `data/`: uploaded/source documents
- `chroma_db/`: vector database index
- `semantic_chroma/`: semantic answer cache

## Frontend Config

- `TYPING_ANIMATION_ENABLED=true` keeps the assistant typing reveal enabled.
- Set `TYPING_ANIMATION_ENABLED=false` to show full answers immediately.

## Frontend Pages

- `Chat`: main conversational interface connected to `POST /query`
- `FAQ`: curated operational starter questions
- `Library`: admin document/form list with download links from `backend/data`
- Form templates: direct download only, with a PDF or Word format picker

## Frontend Scripts

The frontend is still plain browser JavaScript without a bundler. `frontend/web/assets/app.js`
is now the bootstrap/glue file, while feature logic lives in small global modules:

- `assets/js/chat.js`: chat submit/rendering, citations, flowcharts, and form links
- `assets/js/faq.js`, `assets/js/library.js`, `assets/js/auth.js`, `assets/js/api.js`, `assets/js/markdown.js`: FAQ, document admin, auth bindings, API helpers, and markdown rendering

## Structure

```text
Capstone/
|-- backend/
|   |-- api/              # FastAPI routes and frontend hosting
|   |-- researcher_crew/  # RAG answer generation and retrieval helpers
|   |-- preprocessing/    # ingestion, loaders, chunking, embeddings, vectorstore
|   |-- scripts/          # small command-line helpers used by Windows scripts
|   |-- data/             # source documents
|   `-- chroma_db/        # persisted vector database
|-- frontend/
|   `-- web/              # static web frontend (HTML/CSS/JS modular globals)
|-- .env.example
|-- README.md
|-- clean.bat
|-- run.bat
`-- requirements.txt
```
