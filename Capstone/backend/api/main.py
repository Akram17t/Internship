from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[2]
CREW_SRC_DIR = ROOT_DIR / "backend" / "researcher_crew" / "src"
if str(CREW_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(CREW_SRC_DIR))

from researcher_crew.main import run_knowledge_crew


app = FastAPI(title="ICS Knowledge Assistant API", version="1.0.0")
FRONTEND_DIR = ROOT_DIR / "frontend" / "web"
ASSETS_DIR = FRONTEND_DIR / "assets"
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}

FAQ_ITEMS = [
    {
        "question": "Apa respons pertama saat Priority 1 alarm muncul?",
        "answer": (
            "Operator harus acknowledge alarm, memastikan apakah alarm itu genuine atau terkait maintenance, "
            "memberi tahu supervisor dalam lima menit, membuka incident ticket, lalu mulai runbook yang relevan."
        ),
        "suggested_query": "Apa yang harus dilakukan pertama kali ketika Priority 1 alarm muncul?",
    },
    {
        "question": "Apa saja isi wajib shift handover?",
        "answer": (
            "Handover harus mencakup status sistem, alarm aktif atau belum selesai, aset yang degraded, "
            "aktivitas maintenance, perubahan akses sementara, work permit, dan ticket yang belum selesai."
        ),
        "suggested_query": "Apa saja yang wajib dimasukkan ke catatan shift handover?",
    },
    {
        "question": "Informasi apa yang dibutuhkan untuk request akses baru?",
        "answer": (
            "Minimal berisi nama lengkap, employee ID, departemen, supervisor, sistem yang dibutuhkan, "
            "business justification, dan durasi jika aksesnya sementara."
        ),
        "suggested_query": "Apa syarat untuk request akses user baru ke sistem ICS?",
    },
    {
        "question": "Kapan isu harus di-escalate ke supervisor atau tim lain?",
        "answer": (
            "Escalation dilakukan berdasarkan dampak dan urgensi. Supervisor on duty selalu jadi first line, "
            "lalu diteruskan ke engineering, OT security, platform owner, atau vendor coordinator sesuai kategori insidennya."
        ),
        "suggested_query": "Ke siapa insiden ICS harus di-escalate dan kapan?",
    },
]


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Natural language question from the user.")


class CitationResponse(BaseModel):
    id: int
    source: str
    page: int | None = None
    section: str | None = None
    chunk_id: int | None = None
    download_url: str | None = None


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationResponse] = Field(default_factory=list)


class FAQItem(BaseModel):
    question: str
    answer: str
    suggested_query: str


class LibraryItem(BaseModel):
    name: str
    relative_path: str
    display_name: str
    doc_type: str
    size_bytes: int
    updated_at: str
    download_url: str


def _get_data_dir() -> Path:
    raw_dir = os.getenv("DATA_DIR", "backend/data")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _iter_library_items() -> list[LibraryItem]:
    data_dir = _get_data_dir()
    if not data_dir.exists():
        return []

    items: list[LibraryItem] = []
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        relative_path = path.relative_to(data_dir).as_posix()
        stat = path.stat()
        display_name = path.stem.replace("_", " ").replace("-", " ").strip() or path.name
        items.append(
            LibraryItem(
                name=path.name,
                relative_path=relative_path,
                display_name=display_name.title(),
                doc_type=path.suffix.lower().lstrip("."),
                size_bytes=stat.st_size,
                updated_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                download_url=f"/api/documents/{quote(relative_path, safe='/')}",
            )
        )

    return items


if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query_knowledge_base(payload: QueryRequest) -> QueryResponse:
    answer, raw_citations = run_knowledge_crew(payload.question)
    citations = [
        CitationResponse(
            **citation,
            download_url=f"/api/documents/{quote(str(citation['source']), safe='')}",
        )
        for citation in raw_citations
    ]
    return QueryResponse(answer=answer, citations=citations)


@app.get("/api/faq", response_model=list[FAQItem])
def get_faq() -> list[FAQItem]:
    return [FAQItem(**item) for item in FAQ_ITEMS]


@app.get("/api/library", response_model=list[LibraryItem])
def get_library() -> list[LibraryItem]:
    return _iter_library_items()


@app.get("/api/documents/{document_path:path}")
def download_document(document_path: str) -> FileResponse:
    data_dir = _get_data_dir().resolve()
    resolved_path = (data_dir / unquote(document_path)).resolve()

    try:
        resolved_path.relative_to(data_dir)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid document path.") from error

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")

    return FileResponse(path=resolved_path, filename=resolved_path.name)


@app.get("/", response_class=FileResponse, include_in_schema=False)
def frontend_app() -> FileResponse:
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend bundle not found.")
    return FileResponse(index_file)
