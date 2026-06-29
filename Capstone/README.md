# ICS SOP & Knowledge Assistant

RAG-based internal document assistant for SOP, guideline, and runbook search, now with a custom web frontend served directly from FastAPI.

General project documentation is available in [PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md).

## Stack

- FastAPI for REST backend and frontend hosting
- Vanilla HTML, CSS, and JavaScript for the web UI
- CrewAI for multi-agent orchestration
- ChromaDB for local vector storage
- Ollama for local LLM and embedding

## Quick Start

1. Create a virtual environment and install dependencies from `requirements.txt`.
2. Copy `.env.example` to `.env` and adjust values if needed.
3. Put PDF or DOCX files into `backend/data/`.
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

- `run.bat` uses `backend\researcher_crew\.venv`, checks the required imports, runs ingestion only when `backend\chroma_db` is empty, then starts FastAPI and opens the web frontend in your browser.
- `clean.bat` removes `__pycache__`, `.pytest_cache`, `*.pyc`, and generated files inside `backend\chroma_db` except `.gitkeep`.

## Frontend Pages

- `Chat`: main conversational interface connected to `POST /query`
- `FAQ`: curated operational starter questions
- `Library`: indexed source document list with download links from `backend/data`

## Structure

```text
Capstone/
├── backend/
│   ├── api/              # FastAPI routes and frontend hosting
│   ├── researcher_crew/  # CrewAI project and its venv
│   ├── preprocessing/    # ingestion, loaders, chunking, embeddings, vectorstore
│   ├── data/             # source documents
│   └── chroma_db/        # persisted vector database
├── frontend/
│   └── web/              # static web frontend (HTML/CSS/JS)
├── .env.example
├── .gitignore
├── README.md
├── clean.bat
├── run.bat
└── requirements.txt
```
