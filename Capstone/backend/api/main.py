from __future__ import annotations

import base64
import binascii
import json
import re
import sys
import threading
import uuid
from datetime import datetime
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.settings import get_env, load_capstone_env

ROOT_DIR = Path(__file__).resolve().parents[2]
load_capstone_env()
CREW_SRC_DIR = ROOT_DIR / "backend" / "researcher_crew" / "src"
if str(CREW_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(CREW_SRC_DIR))

app = FastAPI(title="ICS Knowledge Assistant API", version="1.0.0")
FRONTEND_DIR = ROOT_DIR / "frontend" / "web"
ASSETS_DIR = FRONTEND_DIR / "assets"
EMBEDDABLE_EXTENSIONS = {".pdf", ".docx", ".txt"}
LIBRARY_EXTENSIONS = EMBEDDABLE_EXTENSIONS | {".xlsx"}
ADMIN_EMAILS = {"admin@gmail.com"}
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_CONVERSATIONS = 50
MAX_CONVERSATION_TURNS = 5
MAX_CONVERSATION_MESSAGES = MAX_CONVERSATION_TURNS * 2
MAX_CONVERSATION_CONTEXT_CHARS = 3200
CONVERSATION_TTL = timedelta(days=1)
CONVERSATION_LOCK = threading.Lock()
FAQ_LOCK = threading.Lock()
REINDEX_LOCK = threading.Lock()

DEFAULT_FAQ_ITEMS: list[dict[str, object]] = [
    {
        "id": "alur-perjalanan-dinas",
        "question": "Bagaimana alur pengajuan perjalanan dinas?",
        "answer": (
            "Requestor mengisi Form Permohonan Perjalanan Dinas sebelum berangkat dan meminta persetujuan atasan terkait serta Director. "
            "Jika membutuhkan uang muka, requestor juga mengajukan Form Permohonan Uang Muka, lalu setelah perjalanan selesai wajib menyerahkan "
            "Form Penyelesaian Perjalanan Dinas ke General Affair. [1][2][3]"
        ),
        "source": "SOP - Perjalanan Dinas.pdf",
        "source_url": "/api/documents/SOP%20-%20Perjalanan%20Dinas.pdf",
        "suggested_query": "Jelaskan alur lengkap pengajuan perjalanan dinas beserta approval dan form yang digunakan.",
        "citations": [
            {"id": 1, "source": "SOP - Perjalanan Dinas.pdf", "page": 7, "section": "6. AKTIVITAS", "chunk_id": 32},
            {"id": 2, "source": "SOP - Perjalanan Dinas.pdf", "page": 7, "section": "6. AKTIVITAS", "chunk_id": 34},
            {"id": 3, "source": "SOP - Perjalanan Dinas.pdf", "page": 8, "section": "6. AKTIVITAS", "chunk_id": 35},
        ],
    },
    {
        "id": "form-perjalanan-dinas",
        "question": "Form apa saja yang digunakan untuk perjalanan dinas?",
        "answer": (
            "SOP Perjalanan Dinas mencantumkan tiga form utama: Form Permohonan Uang Muka Perjalanan Dinas, "
            "Form Penyelesaian Perjalanan Dinas, dan Form Permohonan Perjalanan Dinas. Ketiganya tercantum pada bagian Dokumen Terkait "
            "dan dipakai sesuai tahap proses perjalanan dinas. [1]"
        ),
        "source": "SOP - Perjalanan Dinas.pdf",
        "source_url": "/api/documents/SOP%20-%20Perjalanan%20Dinas.pdf",
        "suggested_query": "Sebutkan seluruh form yang dipakai dalam proses perjalanan dinas.",
        "citations": [
            {"id": 1, "source": "SOP - Perjalanan Dinas.pdf", "page": 8, "section": "8. DOKUMEN TERKAIT", "chunk_id": 38},
        ],
    },
    {
        "id": "persiapan-onboarding",
        "question": "Apa saja persiapan onboarding karyawan baru?",
        "answer": (
            "Persiapan onboarding mencakup penyiapan perlengkapan kerja, perkenalan lingkungan kerja dan Peraturan Perusahaan, "
            "pembuatan akun HRIS, sampai evaluasi kontrak karyawan. HR Personnel juga berkoordinasi dengan General Affair dan IT Internal "
            "agar kebutuhan kerja karyawan baru siap sejak awal. [1][2]"
        ),
        "source": "SOP - Administrasi Karyawan.pdf",
        "source_url": "/api/documents/SOP%20-%20Administrasi%20Karyawan.pdf",
        "suggested_query": "Jelaskan persiapan onboarding karyawan baru berdasarkan SOP Administrasi Karyawan.",
        "citations": [
            {"id": 1, "source": "SOP - Administrasi Karyawan.pdf", "page": 5, "section": "2. RUANG LINGKUP", "chunk_id": 2},
            {"id": 2, "source": "SOP - Administrasi Karyawan.pdf", "page": 6, "section": "6. AKTIVITAS", "chunk_id": 7},
        ],
    },
    {
        "id": "fasilitas-karyawan-baru",
        "question": "Siapa yang menyiapkan fasilitas kerja untuk karyawan baru?",
        "answer": (
            "General Affair Staff bertugas menyiapkan fasilitas dan perlengkapan kerja karyawan baru. "
            "HR Personnel Staff berkoordinasi dengan General Affair dan IT Internal agar perlengkapan kerja siap saat onboarding. [1][2]"
        ),
        "source": "SOP - Administrasi Karyawan.pdf",
        "source_url": "/api/documents/SOP%20-%20Administrasi%20Karyawan.pdf",
        "suggested_query": "Siapa PIC penyiapan fasilitas dan perlengkapan kerja untuk karyawan baru?",
        "citations": [
            {"id": 1, "source": "SOP - Administrasi Karyawan.pdf", "page": 6, "section": "5. TUGAS DAN TANGGUNG JAWAB", "chunk_id": 6},
            {"id": 2, "source": "SOP - Administrasi Karyawan.pdf", "page": 6, "section": "6. AKTIVITAS", "chunk_id": 7},
        ],
    },
    {
        "id": "terminasi-karyawan",
        "question": "Apa yang wajib diselesaikan saat terminasi hubungan kerja?",
        "answer": (
            "Saat terminasi, karyawan wajib menyelesaikan handover kepada atasan atau pihak yang ditunjuk, "
            "menuntaskan Exit Clearance termasuk pengembalian aset, dan keluar dari media komunikasi operasional perusahaan. "
            "Proses terminasi juga mencakup exit interview oleh HR Personnel serta verifikasi penyelesaian kewajiban oleh pihak terkait. [1][2][3]"
        ),
        "source": "SOP - Terminasi Hubungan Kerja.pdf",
        "source_url": "/api/documents/SOP%20-%20Terminasi%20Hubungan%20Kerja.pdf",
        "suggested_query": "Jelaskan kewajiban utama karyawan dan tim terkait dalam proses terminasi hubungan kerja.",
        "citations": [
            {"id": 1, "source": "SOP - Terminasi Hubungan Kerja.pdf", "page": 5, "section": "2. RUANG LINGKUP", "chunk_id": 41},
            {"id": 2, "source": "SOP - Terminasi Hubungan Kerja.pdf", "page": 6, "section": "6. AKTIVITAS", "chunk_id": 46},
            {"id": 3, "source": "SOP - Terminasi Hubungan Kerja.pdf", "page": 6, "section": "6. AKTIVITAS", "chunk_id": 48},
        ],
    },
    {
        "id": "deadline-exit-clearance",
        "question": "Kapan Exit Clearance harus diselesaikan?",
        "answer": (
            "Exit Clearance wajib diselesaikan pada hari terakhir efektif bekerja, termasuk pengembalian seluruh aset perusahaan. "
            "Form Exit Clearance juga harus lengkap, ditandatangani pihak terkait, dan paling lambat selesai pada hari terakhir bekerja. [1][2]"
        ),
        "source": "SOP - Terminasi Hubungan Kerja.pdf",
        "source_url": "/api/documents/SOP%20-%20Terminasi%20Hubungan%20Kerja.pdf",
        "suggested_query": "Kapan deadline Exit Clearance dan apa saja syarat penyelesaiannya?",
        "citations": [
            {"id": 1, "source": "SOP - Terminasi Hubungan Kerja.pdf", "page": 6, "section": "6. AKTIVITAS", "chunk_id": 47},
            {"id": 2, "source": "SOP - Terminasi Hubungan Kerja.pdf", "page": 6, "section": "6. AKTIVITAS", "chunk_id": 48},
        ],
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


class FormDownloadResponse(BaseModel):
    name: str
    display_name: str
    download_url: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationResponse] = Field(default_factory=list)
    form_downloads: list[FormDownloadResponse] = Field(default_factory=list)
    conversation_id: str


class FAQItem(BaseModel):
    id: str
    question: str
    answer: str
    source: str = ""
    source_url: str = ""
    suggested_query: str
    citations: list[CitationResponse] = Field(default_factory=list)
    image_url: str = ""
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
    document_kind: str
    is_embeddable: bool
    size_bytes: int
    updated_at: str
    download_url: str


class AdminDocumentPayload(BaseModel):
    filename: str = Field(..., min_length=1)
    content_base64: str = Field(..., min_length=1)
    replace_path: str | None = None


class AdminDocumentResponse(BaseModel):
    message: str
    requires_reindex: bool = False
    item: LibraryItem | None = None


class AdminReindexResponse(BaseModel):
    message: str


def _get_data_dir() -> Path:
    raw_dir = get_env("DATA_DIR", "backend/data")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _document_kind_for_path(path: Path) -> str:
    name = path.stem.lower()
    if path.suffix.lower() == ".xlsx" or name.startswith("form"):
        return "form"
    if name.startswith("sop"):
        return "sop"
    return "document"


def _is_embeddable_path(path: Path) -> bool:
    return path.suffix.lower() in EMBEDDABLE_EXTENSIONS


def _to_library_item(path: Path, data_dir: Path) -> LibraryItem:
    relative_path = path.relative_to(data_dir).as_posix()
    stat = path.stat()
    display_name = path.stem.replace("_", " ").replace("-", " ").strip() or path.name
    return LibraryItem(
        name=path.name,
        relative_path=relative_path,
        display_name=display_name.title(),
        doc_type=path.suffix.lower().lstrip("."),
        document_kind=_document_kind_for_path(path),
        is_embeddable=_is_embeddable_path(path),
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
        if not path.is_file() or path.suffix.lower() not in LIBRARY_EXTENSIONS:
            continue
        if path.name.startswith("~$"):  # skip Excel lock files
            continue

        items.append(_to_library_item(path, data_dir))

    return items


def _form_keywords_for_path(path: Path) -> list[str]:
    name = path.name.lower()
    if "perjalanan dinas" in name:
        return [
            "perjalanan dinas",
            "uang muka",
            "penyelesaian perjalanan",
            "permohonan perjalanan",
        ]
    if "onboarding" in name:
        return ["onboarding", "on boarding", "karyawan baru", "preparation"]
    if "exit" in name:
        return [
            "exit clearance",
            "exit interview",
            "terminasi",
            "resign",
            "pengunduran diri",
            "offboarding",
        ]
    return [path.stem.lower()]


def _format_form_display_name(path: Path) -> str:
    return (
        path.stem.replace("Form - ", "")
        .replace("(Template)", "")
        .replace("_", " ")
        .strip()
    )


def _form_download_response(path: Path, data_dir: Path) -> FormDownloadResponse:
    relative_path = path.relative_to(data_dir).as_posix()
    return FormDownloadResponse(
        name=path.name,
        display_name=_format_form_display_name(path),
        download_url=f"/api/documents/{quote(relative_path, safe='/')}",
    )


def _matching_form_downloads(*texts: str) -> list[FormDownloadResponse]:
    haystack = " ".join(texts).lower()
    data_dir = _get_data_dir()
    if not data_dir.exists():
        return []

    matches: list[FormDownloadResponse] = []
    for path in sorted(data_dir.rglob("*.xlsx")):
        if not path.is_file() or path.name.startswith("~$"):
            continue
        keywords = _form_keywords_for_path(path)
        is_form_request = "form" in haystack or any(keyword in haystack for keyword in keywords)
        if not is_form_request or not any(keyword in haystack for keyword in keywords):
            continue
        matches.append(_form_download_response(path, data_dir))
    return matches


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
    raw_dir = get_env("CONVERSATION_CACHE_DIR", "backend/cache")
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


def _parse_conversation_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _prune_expired_conversations(
    conversations: dict[str, list[dict[str, object]]],
) -> dict[str, list[dict[str, object]]]:
    cutoff = datetime.now() - CONVERSATION_TTL
    pruned: dict[str, list[dict[str, object]]] = {}

    for conversation_id, messages in conversations.items():
        if not isinstance(messages, list) or not messages:
            continue

        latest_timestamp: datetime | None = None
        for message in reversed(messages):
            if not isinstance(message, dict):
                continue
            latest_timestamp = _parse_conversation_timestamp(message.get("created_at"))
            if latest_timestamp is not None:
                break

        if latest_timestamp is None or latest_timestamp < cutoff:
            continue

        pruned[conversation_id] = messages

    return pruned


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

    conversations = {
        str(key): value
        for key, value in data.items()
        if isinstance(value, list)
    }
    return _prune_expired_conversations(conversations)


def _save_conversations(conversations: dict[str, list[dict[str, object]]]) -> None:
    cache_dir = _get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    active_conversations = _prune_expired_conversations(conversations)
    trimmed_items = list(active_conversations.items())[-MAX_CONVERSATIONS:]
    payload = {key: value[-MAX_CONVERSATION_MESSAGES:] for key, value in trimmed_items}
    _get_conversation_file().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _get_conversation_context(conversation_id: str) -> str:
    with CONVERSATION_LOCK:
        messages = _load_conversations().get(conversation_id, [])

    context_lines: list[str] = []
    for message in messages[-MAX_CONVERSATION_MESSAGES:]:
        role = "User" if message.get("role") == "user" else "Assistant"
        content = str(message.get("content", "")).strip()
        if content:
            context_lines.append(f"{role}: {content}")

    return "\n".join(context_lines)[-MAX_CONVERSATION_CONTEXT_CHARS:]


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
        image_url=str(item.get("image_url", "")).strip(),
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


def _is_unusable_faq_answer(answer: str, citations: list[CitationResponse]) -> bool:
    normalized = " ".join(answer.lower().split())
    blocked_phrases = (
        "informasi ini belum tersedia",
        "informasi tersebut tidak tersedia",
        "tidak tersedia dalam dokumen",
        "tidak ditemukan dalam dokumen",
        "pertanyaan anda tidak jelas",
        "mohon berikan detail",
        "berikan detail lebih lanjut",
        "[nama perusahaan]",
    )
    return not citations or any(phrase in normalized for phrase in blocked_phrases)


def _build_faq_item(payload: AdminFAQPayload, faq_id: str | None = None) -> FAQItem:
    from researcher_crew.main import OllamaGenerationError, run_faq_crew

    question = payload.question.strip()
    try:
        answer, raw_citations = run_faq_crew(question)
    except OllamaGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    citations = [
        CitationResponse(
            **citation,
            download_url=f"/api/documents/{quote(str(citation['source']), safe='')}",
        )
        for citation in raw_citations
    ]
    if _is_unusable_faq_answer(answer, citations):
        raise HTTPException(
            status_code=422,
            detail=(
                "FAQ tidak disimpan karena tidak ada sumber dari dokumen terindeks. "
                "Coba tulis pertanyaan yang lebih spesifik atau tambahkan dokumen yang relevan."
            ),
        )
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
    from researcher_crew.main import OllamaGenerationError, run_knowledge_crew

    conversation_id = _clean_conversation_id(payload.conversation_id)
    conversation_context = _get_conversation_context(conversation_id)
    try:
        answer, raw_citations = run_knowledge_crew(payload.question, conversation_context)
    except OllamaGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    _append_conversation_turn(conversation_id, payload.question, answer)
    citations = [
        CitationResponse(
            **citation,
            download_url=f"/api/documents/{quote(str(citation['source']), safe='')}",
        )
        for citation in raw_citations
    ]
    return QueryResponse(
        answer=answer,
        citations=citations,
        form_downloads=_matching_form_downloads(payload.question, answer),
        conversation_id=conversation_id,
    )


# Static, pinned FAQ shown at the top for everyone. Not stored in faqs.json and
# not editable/deletable via the admin FAQ endpoints (id is empty). Only its
# image can be replaced, via POST /api/admin/faq-image.
PINNED_IMAGE_STEM = "organogram"
PINNED_IMAGE_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg"}


def _pinned_image_name() -> str:
    for extension in (".webp", ".png", ".jpg", ".jpeg"):
        if (ASSETS_DIR / f"{PINNED_IMAGE_STEM}{extension}").exists():
            return f"{PINNED_IMAGE_STEM}{extension}"
    return f"{PINNED_IMAGE_STEM}.webp"


def _pinned_image_url() -> str:
    name = _pinned_image_name()
    path = ASSETS_DIR / name
    # Cache-bust with mtime so the browser reloads after the image is replaced.
    version = int(path.stat().st_mtime) if path.exists() else 0
    return f"/assets/{name}?v={version}"


def _pinned_faq_items() -> list[FAQItem]:
    return [
        FAQItem(
            id="",
            question="Bagaimana struktur organisasi ICS Compute?",
            answer="Berikut struktur organisasi (organogram) ICS Compute.",
            suggested_query="Bagaimana struktur organisasi ICS Compute?",
            image_url=_pinned_image_url(),
        ),
    ]


@app.get("/api/faq", response_model=list[FAQItem])
def get_faq() -> list[FAQItem]:
    with FAQ_LOCK:
        stored = _load_faqs()
    return [*_pinned_faq_items(), *stored]


@app.post("/api/admin/faq-image", response_model=AdminDocumentResponse)
def upload_pinned_faq_image(
    payload: AdminDocumentPayload,
    x_admin_email: str = Header(default=""),
) -> AdminDocumentResponse:
    _require_admin(x_admin_email)
    extension = Path(unquote(payload.filename)).suffix.lower()
    if extension not in PINNED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Gambar harus berformat .webp, .png, atau .jpg.",
        )

    content = _decode_document(payload.content_base64)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    # Keep a single organogram image: drop any other extension variants first.
    for other_extension in PINNED_IMAGE_EXTENSIONS:
        if other_extension == extension:
            continue
        stale = ASSETS_DIR / f"{PINNED_IMAGE_STEM}{other_extension}"
        if stale.exists():
            stale.unlink()

    (ASSETS_DIR / f"{PINNED_IMAGE_STEM}{extension}").write_bytes(content)
    return AdminDocumentResponse(message="Gambar FAQ diperbarui.")


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
def get_library(x_admin_email: str = Header(default="")) -> list[LibraryItem]:
    _require_admin(x_admin_email)
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
    if suffix not in LIBRARY_EXTENSIONS:
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
    requires_reindex = _is_embeddable_path(target_path)
    return AdminDocumentResponse(
        message=f"Document {action}.",
        requires_reindex=requires_reindex,
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
    if target_path.suffix.lower() not in LIBRARY_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported document type.")

    requires_reindex = _is_embeddable_path(target_path)
    target_path.unlink()
    return AdminDocumentResponse(message="Document deleted.", requires_reindex=requires_reindex)


@app.post("/api/admin/reindex", response_model=AdminReindexResponse)
def reindex_documents(x_admin_email: str = Header(default="")) -> AdminReindexResponse:
    _require_admin(x_admin_email)
    if not REINDEX_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Reindex is already running.")

    try:
        from backend.preprocessing.ingest import main as rebuild_knowledge_base

        rebuild_knowledge_base()
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Rebuild embeddings failed: {error}",
        ) from error
    finally:
        REINDEX_LOCK.release()

    return AdminReindexResponse(message="Embeddings rebuilt.")


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Matches placeholder brackets the form templates use, e.g. "[  ]", "[Tanggal]".
FORM_PLACEHOLDER_PATTERN = re.compile(r"\[[^\[\]]*\]")
# A "field" cell is one whose whole content is a single bracket (the labelled
# info rows). Inline placeholders like "Nama: [ ]" (signature blocks) or
# "No. Form: [Nomor Form]" (headers) are skipped to keep the form short.
FORM_FIELD_CELL_PATTERN = re.compile(r"^\[[^\[\]]*\]$")


class FormFillPayload(BaseModel):
    path: str = Field(..., min_length=1)
    values: dict[str, str] = Field(default_factory=dict)


def _field_label(worksheet, cell) -> str | None:
    """Find a clean text label for a placeholder cell, or None if there isn't one.

    Looks inside the bracket, then at the nearest text to the left, then above.
    Returns None when no proper label exists (e.g. a stray grid cell), so it can
    be skipped instead of showing a "[  ]" field.
    """
    inside = str(cell.value).strip()[1:-1].strip()
    if inside:
        return inside
    for column in range(cell.column - 1, 0, -1):
        left = worksheet.cell(row=cell.row, column=column).value
        if isinstance(left, str):
            candidate = left.strip().rstrip(":").strip()
            if candidate and not FORM_PLACEHOLDER_PATTERN.search(candidate):
                return candidate
    if cell.row > 1:
        above = worksheet.cell(row=cell.row - 1, column=cell.column).value
        if isinstance(above, str):
            candidate = above.strip().rstrip(":").strip()
            if candidate and not FORM_PLACEHOLDER_PATTERN.search(candidate):
                return candidate
    return None


def _scan_form_fields(path: Path) -> list[dict[str, str]]:
    """List the main info fields of a form: the first contiguous block of
    labelled "[  ]" rows in each sheet. Later sections (free text, cost tables,
    signature blocks) are skipped so the fill form stays short."""
    from openpyxl import load_workbook

    workbook = load_workbook(path)
    fields: list[dict[str, str]] = []
    for index, worksheet in enumerate(workbook.worksheets):
        started = False
        for row in worksheet.iter_rows():
            row_fields: list[dict[str, str]] = []
            for cell in row:
                if not (isinstance(cell.value, str) and FORM_FIELD_CELL_PATTERN.match(cell.value.strip())):
                    continue
                label = _field_label(worksheet, cell)
                if label:
                    row_fields.append(
                        {"key": f"{index}:{cell.coordinate}", "label": label}
                    )
            if row_fields:
                started = True
                fields.extend(row_fields)
            elif started:
                break  # end of the top info block for this sheet
    return fields


def _unique_form_fields(path: Path) -> list[dict[str, str]]:
    """Deduplicate the scanned fields by label so a repeated block (e.g. the
    same info section on 3 sheets) shows as one input."""
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for field in _scan_form_fields(path):
        if field["label"] in seen:
            continue
        seen.add(field["label"])
        unique.append({"key": field["label"], "label": field["label"]})
    return unique


def _fill_form_placeholders(path: Path, values: dict[str, str]) -> bytes:
    """Fill every placeholder cell whose label the user provided a value for.

    Values are keyed by label, so one entry fills all cells sharing that label
    (e.g. the same field repeated across sheets). Blanks are left untouched.
    """
    from openpyxl import load_workbook

    coords_by_label: dict[str, list[str]] = {}
    for field in _scan_form_fields(path):
        coords_by_label.setdefault(field["label"], []).append(field["key"])

    workbook = load_workbook(path)
    for label, raw_value in values.items():
        value = str(raw_value).strip()
        if not value:
            continue
        for coord_key in coords_by_label.get(label, []):
            try:
                index_str, coordinate = coord_key.split(":", 1)
                cell = workbook.worksheets[int(index_str)][coordinate]
            except (ValueError, IndexError, KeyError):
                continue
            if isinstance(cell.value, str) and FORM_PLACEHOLDER_PATTERN.search(cell.value):
                cell.value = FORM_PLACEHOLDER_PATTERN.sub(lambda _match: value, cell.value, count=1)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _resolve_form_path(path: str) -> Path:
    resolved_path = _resolve_document_path(path)
    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Form not found.")
    if (
        resolved_path.suffix.lower() != ".xlsx"
        or _document_kind_for_path(resolved_path) != "form"
    ):
        raise HTTPException(status_code=400, detail="Dokumen ini bukan form yang bisa diisi.")
    return resolved_path


@app.get("/api/documents/{document_path:path}")
def download_document(
    document_path: str,
    x_admin_email: str = Header(default=""),
) -> FileResponse:
    resolved_path = _resolve_document_path(document_path)

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")
    if _document_kind_for_path(resolved_path) != "form":
        _require_admin(x_admin_email)

    return FileResponse(
        path=resolved_path,
        filename=resolved_path.name,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/forms/fields")
def form_fields(path: str) -> dict[str, object]:
    resolved_path = _resolve_form_path(path)
    return {"fields": _unique_form_fields(resolved_path)}


@app.post("/api/forms/fill")
def fill_form(payload: FormFillPayload) -> Response:
    resolved_path = _resolve_form_path(payload.path)
    content = _fill_form_placeholders(resolved_path, payload.values)
    nama = next(
        (v.strip() for v in payload.values.values() if v.strip()),
        "",
    )
    suffix = f" - {nama}" if nama else ""
    filename = f"{resolved_path.stem}{suffix}.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MIME,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )


@app.get("/", response_class=FileResponse, include_in_schema=False)
def frontend_app() -> FileResponse:
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend bundle not found.")
    return FileResponse(index_file)
