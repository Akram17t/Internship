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
FAQ_LOCK = threading.Lock()
REINDEX_LOCK = threading.Lock()

DEFAULT_FAQ_ITEMS = [
    {
        "id": "cuti-tahunan",
        "question": "Berapa hak cuti tahunan karyawan?",
        "answer": (
            "Karyawan yang telah bekerja 12 bulan terus-menerus berhak atas 12 hari kerja cuti tahunan. "
            "Maksimal 5 hari dapat dibawa ke tahun berikutnya dan akan hangus pada 31 Maret jika tidak digunakan."
        ),
        "source": "ICS_PP03_Kebijakan_Cuti.pdf - Pasal 1 - PDF halaman 2",
        "source_url": "/api/documents/ICS_PP03_Kebijakan_Cuti.pdf",
        "suggested_query": "Jelaskan hak, pengajuan, dan carry over cuti tahunan karyawan.",
    },
    {
        "id": "upah-lembur",
        "question": "Bagaimana mekanisme dan perhitungan upah lembur?",
        "answer": (
            "Lembur dilakukan atas permintaan tertulis Atasan Langsung dengan persetujuan Karyawan. "
            "Jam pertama dibayar 1,5 kali upah per jam, jam berikutnya 2 kali, dengan batas maksimal 4 jam per hari dan 18 jam per minggu."
        ),
        "source": "ICS_PP01_Peraturan_Perusahaan.pdf - Pasal 6 - PDF halaman 2-3",
        "source_url": "/api/documents/ICS_PP01_Peraturan_Perusahaan.pdf",
        "suggested_query": "Bagaimana mekanisme dan perhitungan upah lembur?",
    },
    {
        "id": "gaji-bulanan",
        "question": "Kapan gaji bulanan dibayarkan?",
        "answer": (
            "Gaji dibayarkan setiap tanggal 25 melalui transfer bank. Jika tanggal 25 jatuh pada hari libur atau akhir pekan, "
            "pembayaran dilakukan pada hari kerja sebelumnya."
        ),
        "source": "ICS_PP02_Kebijakan_Penggajian.pdf - Pasal 4 - PDF halaman 3",
        "source_url": "/api/documents/ICS_PP02_Kebijakan_Penggajian.pdf",
        "suggested_query": "Kapan dan bagaimana gaji bulanan dibayarkan?",
    },
    {
        "id": "password-perusahaan",
        "question": "Apa ketentuan password akun perusahaan?",
        "answer": (
            "Password minimal terdiri dari 12 karakter dengan kombinasi huruf besar, huruf kecil, angka, dan simbol. "
            "Password sistem kritikal diganti minimal setiap 90 hari dan MFA wajib untuk layanan cloud serta email perusahaan."
        ),
        "source": "ICS_PP04_Kebijakan_IT.pdf - Pasal 4 - PDF halaman 3",
        "source_url": "/api/documents/ICS_PP04_Kebijakan_IT.pdf",
        "suggested_query": "Apa seluruh ketentuan keamanan password dan MFA perusahaan?",
    },
    {
        "id": "insiden-it",
        "question": "Bagaimana melaporkan insiden keamanan IT?",
        "answer": (
            "Insiden atau dugaan insiden harus segera dilaporkan ke Departemen IT melalui security@icscompute.com atau hotline IT dalam 1x24 jam. "
            "Penanganan berikutnya meliputi isolasi, investigasi, pemulihan, dan dokumentasi oleh tim IT."
        ),
        "source": "ICS_PP04_Kebijakan_IT.pdf - Pasal 7 - PDF halaman 3",
        "source_url": "/api/documents/ICS_PP04_Kebijakan_IT.pdf",
        "suggested_query": "Jelaskan prosedur lengkap pelaporan dan penanganan insiden keamanan IT.",
    },
    {
        "id": "cuti-sakit",
        "question": "Apa ketentuan pengajuan cuti sakit?",
        "answer": (
            "Cuti sakit diberikan selama sakit berlangsung dengan Surat Keterangan Dokter. Sakit satu hari tanpa surat dokter diperbolehkan maksimal dua kali dalam setahun; "
            "kejadian ketiga wajib menyertakan surat dokter."
        ),
        "source": "ICS_PP03_Kebijakan_Cuti.pdf - Pasal 3 - PDF halaman 2",
        "source_url": "/api/documents/ICS_PP03_Kebijakan_Cuti.pdf",
        "suggested_query": "Jelaskan hak, bukti, dan ketentuan lengkap cuti sakit karyawan.",
    },
    {
        "id": "thr",
        "question": "Siapa yang berhak menerima THR dan kapan dibayarkan?",
        "answer": (
            "THR diberikan kepada karyawan dengan masa kerja minimal satu bulan secara terus-menerus. "
            "Besarannya satu kali gaji untuk masa kerja minimal 12 bulan atau proporsional untuk masa kerja 1-12 bulan, dan dibayarkan paling lambat tujuh hari sebelum hari raya."
        ),
        "source": "ICS_PP02_Kebijakan_Penggajian.pdf - Pasal 7 - PDF halaman 3",
        "source_url": "/api/documents/ICS_PP02_Kebijakan_Penggajian.pdf",
        "suggested_query": "Jelaskan syarat, perhitungan, dan jadwal pembayaran THR.",
    },
    {
        "id": "work-from-home",
        "question": "Apa ketentuan Work From Home?",
        "answer": (
            "Work From Home diperbolehkan sesuai kebijakan Departemen SDM dan harus mendapat persetujuan Atasan Langsung. "
            "Jam kerja normal tetap 40 jam per minggu dengan core hours pukul 10.00-16.00 WIB."
        ),
        "source": "ICS_PP01_Peraturan_Perusahaan.pdf - Pasal 5 - PDF halaman 2",
        "source_url": "/api/documents/ICS_PP01_Peraturan_Perusahaan.pdf",
        "suggested_query": "Jelaskan aturan Work From Home, jam kerja, dan persetujuan yang dibutuhkan.",
    },
    {
        "id": "ai-generatif",
        "question": "Apa aturan penggunaan AI generatif untuk pekerjaan?",
        "answer": (
            "AI generatif boleh digunakan untuk drafting, brainstorming, dan analisis non-sensitif. "
            "Data Konfidensial atau Rahasia dilarang dimasukkan ke layanan AI publik, dan seluruh output AI wajib diverifikasi sebelum digunakan."
        ),
        "source": "ICS_PP04_Kebijakan_IT.pdf - Pasal 9 - PDF halaman 4",
        "source_url": "/api/documents/ICS_PP04_Kebijakan_IT.pdf",
        "suggested_query": "Jelaskan hal yang boleh dan dilarang dalam penggunaan AI generatif untuk pekerjaan.",
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
    id: str
    question: str
    answer: str
    source: str = ""
    source_url: str = ""
    suggested_query: str
    citations: list[CitationResponse] = Field(default_factory=list)
    updated_at: str | None = None


class AdminFAQPayload(BaseModel):
    question: str = Field(..., min_length=3)


class AdminFAQResponse(BaseModel):
    message: str
    item: FAQItem | None = None


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


class AdminReindexResponse(BaseModel):
    message: str


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


def _get_faq_file() -> Path:
    return _get_cache_dir() / "faqs.json"


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


def _citation_download_url(source: str) -> str:
    return f"/api/documents/{quote(source, safe='')}" if source else ""


def _normalize_citation(raw_item: object, index: int) -> CitationResponse | None:
    if not isinstance(raw_item, dict):
        return None

    source = str(raw_item.get("source", "")).strip()
    if not source:
        return None

    return CitationResponse(
        id=int(raw_item.get("id") or index + 1),
        source=source,
        page=raw_item.get("page") if isinstance(raw_item.get("page"), int) else None,
        section=str(raw_item.get("section", "")).strip() or None,
        chunk_id=raw_item.get("chunk_id") if isinstance(raw_item.get("chunk_id"), int) else None,
        download_url=str(raw_item.get("download_url", "")).strip() or _citation_download_url(source),
    )


def _normalize_citations(item: dict[str, object]) -> list[CitationResponse]:
    raw_citations = item.get("citations")
    if isinstance(raw_citations, list):
        citations = [
            citation
            for citation in (
                _normalize_citation(raw_item, index)
                for index, raw_item in enumerate(raw_citations)
            )
            if citation is not None
        ]
        if citations:
            return citations

    source = str(item.get("source", "")).strip()
    source_url = str(item.get("source_url", "")).strip()
    if not source:
        return []

    return [
        CitationResponse(
            id=1,
            source=source,
            download_url=source_url or _citation_download_url(source),
        )
    ]


def _normalize_faq_item(item: dict[str, object]) -> FAQItem | None:
    question = str(item.get("question", "")).strip()
    answer = str(item.get("answer", "")).strip()
    if not question or not answer:
        return None

    citations = _normalize_citations(item)
    source = str(item.get("source", "")).strip()
    source_url = str(item.get("source_url", "")).strip()
    if citations and not source:
        source = citations[0].source
    if citations and not source_url:
        source_url = citations[0].download_url or ""

    return FAQItem(
        id=str(item.get("id") or uuid.uuid4().hex),
        question=question,
        answer=answer,
        source=source,
        source_url=source_url,
        suggested_query=str(item.get("suggested_query", "")).strip() or question,
        citations=citations,
        updated_at=str(item.get("updated_at", "")).strip() or None,
    )


def _load_faqs() -> list[FAQItem]:
    path = _get_faq_file()
    if not path.exists():
        return [
            item
            for item in (_normalize_faq_item(default_item) for default_item in DEFAULT_FAQ_ITEMS)
            if item is not None
        ]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(data, list):
        return []

    return [
        item
        for item in (_normalize_faq_item(raw_item) for raw_item in data if isinstance(raw_item, dict))
        if item is not None
    ]


def _save_faqs(items: list[FAQItem]) -> None:
    cache_dir = _get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = [
        item.model_dump() if hasattr(item, "model_dump") else item.dict()
        for item in items
    ]
    _get_faq_file().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _find_faq_index(items: list[FAQItem], faq_id: str) -> int:
    for index, item in enumerate(items):
        if item.id == faq_id:
            return index
    raise HTTPException(status_code=404, detail="FAQ not found.")


def _build_faq_item(payload: AdminFAQPayload, faq_id: str | None = None) -> FAQItem:
    from researcher_crew.main import run_faq_crew

    question = payload.question.strip()
    answer, raw_citations = run_faq_crew(question)
    citations = [
        CitationResponse(
            **citation,
            download_url=f"/api/documents/{quote(str(citation['source']), safe='')}",
        )
        for citation in raw_citations
    ]
    source = citations[0].source if citations else ""
    source_url = citations[0].download_url if citations else ""
    return FAQItem(
        id=faq_id or uuid.uuid4().hex,
        question=question,
        answer=answer,
        source=source,
        source_url=source_url or "",
        suggested_query=question,
        citations=citations,
        updated_at=datetime.now().isoformat(timespec="seconds"),
    )


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
    with FAQ_LOCK:
        return _load_faqs()


@app.post("/api/admin/faq", response_model=AdminFAQResponse)
def create_faq(
    payload: AdminFAQPayload,
    x_admin_email: str = Header(default=""),
) -> AdminFAQResponse:
    _require_admin(x_admin_email)
    item = _build_faq_item(payload)
    with FAQ_LOCK:
        items = _load_faqs()
        items.append(item)
        _save_faqs(items)
    return AdminFAQResponse(message="FAQ inserted.", item=item)


@app.put("/api/admin/faq/{faq_id}", response_model=AdminFAQResponse)
def update_faq(
    faq_id: str,
    payload: AdminFAQPayload,
    x_admin_email: str = Header(default=""),
) -> AdminFAQResponse:
    _require_admin(x_admin_email)
    with FAQ_LOCK:
        items = _load_faqs()
        index = _find_faq_index(items, faq_id)
        item = _build_faq_item(payload, faq_id=items[index].id)
        items[index] = item
        _save_faqs(items)
    return AdminFAQResponse(message="FAQ updated.", item=item)


@app.delete("/api/admin/faq/{faq_id}", response_model=AdminFAQResponse)
def delete_faq(
    faq_id: str,
    x_admin_email: str = Header(default=""),
) -> AdminFAQResponse:
    _require_admin(x_admin_email)
    with FAQ_LOCK:
        items = _load_faqs()
        index = _find_faq_index(items, faq_id)
        items.pop(index)
        _save_faqs(items)
    return AdminFAQResponse(message="FAQ deleted.")


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


@app.post("/api/admin/reindex", response_model=AdminReindexResponse)
def reindex_documents(x_admin_email: str = Header(default="")) -> AdminReindexResponse:
    _require_admin(x_admin_email)
    if not REINDEX_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Reindex is already running.")

    try:
        from backend.preprocessing.ingest import main as rebuild_knowledge_base

        rebuild_knowledge_base()
    finally:
        REINDEX_LOCK.release()

    return AdminReindexResponse(message="Embeddings rebuilt.")


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
