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

## Structure

```text
Capstone/
├── backend/
│   ├── api/              # FastAPI routes
│   ├── crewai/           # CrewAI crew, agent YAML, task YAML, and CrewAI tool
│   ├── preprocessing/    # ingestion, loaders, chunking, embeddings, vectorstore
│   ├── data/             # source documents
│   └── chroma_db/        # persisted vector database
├── frontend/
│   └── app.py            # Streamlit UI
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```
