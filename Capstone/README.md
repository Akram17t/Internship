# ICS SOP & Knowledge Assistant

RAG-based internal document assistant for SOP, guideline, and runbook search, with a custom web frontend served directly from FastAPI.

Architecture and design docs, including a topology diagram, are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Stack

- FastAPI for REST backend and frontend hosting
- Vanilla HTML, CSS, and JavaScript for the web UI
- Direct Groq/Ollama LLM calls for chat and FAQ generation
- ChromaDB for local vector storage
- Ollama for local embedding and optional local LLM fallback

## Quick Start

1. Create a virtual environment and install dependencies from `requirements.txt`.
2. Copy `.env.example` to `.env` and adjust values if needed.
3. Put SOP/knowledge PDF or DOCX files into `backend/data/`; PDF forms should use filenames starting with `Form`.
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

## Frontend Config

- `TYPING_ANIMATION_ENABLED=true` keeps the assistant typing reveal enabled.
- Set `TYPING_ANIMATION_ENABLED=false` to show full answers immediately.

## Frontend Pages

- `Chat`: main conversational interface connected to `POST /query`
- `FAQ`: curated operational starter questions
- `Library`: admin document/form list with download links from `backend/data`
- `PDF Form Editor`: schema-driven form preview/fill flow with local browser drafts

## Frontend Scripts

The frontend is still plain browser JavaScript without a bundler. `frontend/web/assets/app.js`
is now the bootstrap/glue file, while feature logic lives in small global modules:

- `assets/js/chat.js`: chat submit/rendering, citations, flowcharts, and form links
- `assets/js/forms.js`: PDF form editor, live preview overlay, schema/legacy submit flow
- `assets/js/storage.js` and `assets/js/drafts.js`: local form drafts and floating draft launcher
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
