# ICS SOP & Knowledge Assistant

RAG-based internal document Q&A system for SOP, guideline, and runbook search.

## Stack

- Streamlit for chat UI
- FastAPI for REST backend
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

6. Start the chat UI:

```bash
streamlit run frontend/app.py
```

## Windows Scripts

For the easiest Windows flow, use:

```bat
run.bat
clean.bat
```

- `run.bat` uses `backend\researcher_crew\.venv`, checks the required imports, runs ingestion only when `backend\chroma_db` is empty, then starts FastAPI on port `8000` and Streamlit on port `8501`.
- `clean.bat` removes `__pycache__`, `.pytest_cache`, `*.pyc`, and generated files inside `backend\chroma_db` except `.gitkeep`.

## Structure

```text
Capstone/
├── backend/
│   ├── api/              # FastAPI routes
│   ├── researcher_crew/  # CrewAI project and its venv
│   ├── preprocessing/    # ingestion, loaders, chunking, embeddings, vectorstore
│   ├── data/             # source documents
│   └── chroma_db/        # persisted vector database
├── frontend/
│   └── app.py            # Streamlit UI
├── .env.example
├── .gitignore
├── README.md
├── clean.bat
├── run.bat
└── requirements.txt
```
