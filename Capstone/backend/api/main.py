from __future__ import annotations

import base64
import binascii
import json
import os
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[2]
CREW_SRC_DIR = ROOT_DIR / "backend" / "researcher_crew" / "src"
if str(CREW_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(CREW_SRC_DIR))

app = FastAPI(title="ICS Knowledge Assistant API", version="1.0.0")
FRONTEND_DIR = ROOT_DIR / "frontend" / "web"
ASSETS_DIR = FRONTEND_DIR / "assets"
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}
ADMIN_EMAILS = {"admin@gmail.com"}
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_CONVERSATIONS = 50
MAX_CONVERSATION_MESSAGES = 12
CONVERSATION_LOCK = threading.Lock()

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
    conversation_id: str | None = Field(default=None, description="Client conversation identifier.")


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
    conversation_id: str


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


class AdminDocumentPayload(BaseModel):
    filename: str = Field(..., min_length=1)
    content_base64: str = Field(..., min_length=1)
    replace_path: str | None = None


class AdminDocumentResponse(BaseModel):
    message: str
    item: LibraryItem | None = None


def _get_data_dir() -> Path:
    raw_dir = os.getenv("DATA_DIR", "backend/data")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _to_library_item(path: Path, data_dir: Path) -> LibraryItem:
    relative_path = path.relative_to(data_dir).as_posix()
    stat = path.stat()
    display_name = path.stem.replace("_", " ").replace("-", " ").strip() or path.name
    return LibraryItem(
        name=path.name,
        relative_path=relative_path,
        display_name=display_name.title(),
        doc_type=path.suffix.lower().lstrip("."),
        size_bytes=stat.st_size,
        updated_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        download_url=f"/api/documents/{quote(relative_path, safe='/')}",
    )


def _iter_library_items() -> list[LibraryItem]:
    data_dir = _get_data_dir()
    if not data_dir.exists():
        return []

    items: list[LibraryItem] = []
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        items.append(_to_library_item(path, data_dir))

    return items


def _require_admin(x_admin_email: str) -> None:
    if x_admin_email.strip().lower() not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin access required.")


def _resolve_document_path(document_path: str) -> Path:
    data_dir = _get_data_dir().resolve()
    resolved_path = (data_dir / unquote(document_path)).resolve()

    try:
        resolved_path.relative_to(data_dir)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid document path.") from error

    return resolved_path


def _decode_document(content_base64: str) -> bytes:
    try:
        payload = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status_code=400, detail="Invalid document payload.") from error

    if not payload:
        raise HTTPException(status_code=400, detail="Document cannot be empty.")
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Document is too large.")
    return payload


def _get_cache_dir() -> Path:
    raw_dir = os.getenv("CONVERSATION_CACHE_DIR", "backend/cache")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _get_conversation_file() -> Path:
    return _get_cache_dir() / "conversations.json"


def _clean_conversation_id(value: str | None) -> str:
    if not value:
        return uuid.uuid4().hex

    cleaned = "".join(char for char in value if char.isalnum() or char in {"-", "_"})
    if 8 <= len(cleaned) <= 80:
        return cleaned
    return uuid.uuid4().hex


def _load_conversations() -> dict[str, list[dict[str, object]]]:
    path = _get_conversation_file()
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(data, dict):
        return {}
    return {
        str(key): value
        for key, value in data.items()
        if isinstance(value, list)
    }


def _save_conversations(conversations: dict[str, list[dict[str, object]]]) -> None:
    cache_dir = _get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    trimmed_items = list(conversations.items())[-MAX_CONVERSATIONS:]
    payload = {key: value[-MAX_CONVERSATION_MESSAGES:] for key, value in trimmed_items}
    _get_conversation_file().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _get_conversation_context(conversation_id: str) -> str:
    with CONVERSATION_LOCK:
        messages = _load_conversations().get(conversation_id, [])

    context_lines: list[str] = []
    for message in messages[-6:]:
        role = "User" if message.get("role") == "user" else "Assistant"
        content = str(message.get("content", "")).strip()
        if content:
            context_lines.append(f"{role}: {content}")

    return "\n".join(context_lines)[-1600:]


def _append_conversation_turn(conversation_id: str, question: str, answer: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with CONVERSATION_LOCK:
        conversations = _load_conversations()
        messages = conversations.setdefault(conversation_id, [])
        messages.extend(
            [
                {"role": "user", "content": question, "created_at": now},
                {"role": "assistant", "content": answer, "created_at": now},
            ]
        )
        conversations[conversation_id] = messages[-MAX_CONVERSATION_MESSAGES:]
        _save_conversations(conversations)


if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query_knowledge_base(payload: QueryRequest) -> QueryResponse:
    from researcher_crew.main import run_knowledge_crew

    conversation_id = _clean_conversation_id(payload.conversation_id)
    conversation_context = _get_conversation_context(conversation_id)
    answer, raw_citations = run_knowledge_crew(payload.question, conversation_context)
    _append_conversation_turn(conversation_id, payload.question, answer)
    citations = [
        CitationResponse(
            **citation,
            download_url=f"/api/documents/{quote(str(citation['source']), safe='')}",
        )
        for citation in raw_citations
    ]
    return QueryResponse(answer=answer, citations=citations, conversation_id=conversation_id)


@app.get("/api/faq", response_model=list[FAQItem])
def get_faq() -> list[FAQItem]:
    return [FAQItem(**item) for item in FAQ_ITEMS]


@app.get("/api/library", response_model=list[LibraryItem])
def get_library() -> list[LibraryItem]:
    return _iter_library_items()


@app.post("/api/admin/documents", response_model=AdminDocumentResponse)
def save_document(
    payload: AdminDocumentPayload,
    x_admin_email: str = Header(default=""),
) -> AdminDocumentResponse:
    _require_admin(x_admin_email)
    data_dir = _get_data_dir().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(unquote(payload.filename)).name
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported document type.")

    content = _decode_document(payload.content_base64)

    if payload.replace_path:
        target_path = _resolve_document_path(payload.replace_path)
        if not target_path.exists() or not target_path.is_file():
            raise HTTPException(status_code=404, detail="Document not found.")
        if target_path.suffix.lower() != suffix:
            raise HTTPException(
                status_code=400,
                detail="Replacement file type must match the existing document.",
            )
        action = "updated"
    else:
        target_path = (data_dir / filename).resolve()
        try:
            target_path.relative_to(data_dir)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Invalid filename.") from error
        if target_path.exists():
            raise HTTPException(status_code=409, detail="Document already exists.")
        action = "inserted"

    target_path.write_bytes(content)
    return AdminDocumentResponse(
        message=f"Document {action}.",
        item=_to_library_item(target_path, data_dir),
    )


@app.delete("/api/admin/documents/{document_path:path}", response_model=AdminDocumentResponse)
def delete_document(
    document_path: str,
    x_admin_email: str = Header(default=""),
) -> AdminDocumentResponse:
    _require_admin(x_admin_email)
    target_path = _resolve_document_path(document_path)

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")
    if target_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported document type.")

    target_path.unlink()
    return AdminDocumentResponse(message="Document deleted.")


@app.get("/api/documents/{document_path:path}")
def download_document(document_path: str) -> FileResponse:
    resolved_path = _resolve_document_path(document_path)

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")

    return FileResponse(path=resolved_path, filename=resolved_path.name)


@app.get("/", response_class=FileResponse, include_in_schema=False)
def frontend_app() -> FileResponse:
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend bundle not found.")
    return FileResponse(index_file)
