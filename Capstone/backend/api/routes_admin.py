from __future__ import annotations

import hmac
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated
from urllib.parse import unquote

from fastapi import Header, HTTPException, Query

from backend.api.auth import _create_admin_token, _find_admin, _has_configured_admin, _require_admin
from backend.api.cache_store import _add_admin_config, _find_faq_index, _load_faqs, _save_faqs
from backend.api.core import FAQ_LOCK, LIBRARY_EXTENSIONS, REINDEX_LOCK, app
from backend.api.faq_service import PINNED_IMAGE_EXTENSIONS, _build_faq_item, replace_pinned_image
from backend.api.flowchart_service import clear_flowchart_cache_for_source
from backend.api.forms_service import delete_form_docx_template, ensure_form_docx_template
from backend.api.models import (
    ActivityLogItem,
    ActivityLogSessionItem,
    ActivityLogSummaryResponse,
    AdminAccountResponse,
    AdminCreatePayload,
    AdminDocumentPayload,
    AdminDocumentResponse,
    AdminFAQPayload,
    AdminFAQResponse,
    AdminLoginPayload,
    AdminLoginResponse,
    AdminReindexResponse,
    LibraryItem,
)
from backend.api.storage import (
    _decode_document,
    _document_kind_for_path,
    _get_data_dir,
    _is_embeddable_path,
    _iter_library_items,
    _resolve_document_path,
    _to_library_item,
)
from backend.cache_db import (
    delete_activity_log,
    delete_activity_logs_for_conversation,
    list_activity_log_sessions,
    list_activity_logs,
    summarize_activity_logs,
)

logger = logging.getLogger("uvicorn.error")


def _activity_date_range(
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, str]:
    today = datetime.now().date()
    default_start = today - timedelta(days=29)
    try:
        start = datetime.fromisoformat(start_date).date() if start_date else default_start
        end = datetime.fromisoformat(end_date).date() if end_date else today
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Format tanggal harus YYYY-MM-DD.") from error
    if end < start:
        raise HTTPException(status_code=422, detail="Tanggal akhir harus setelah tanggal mulai.")
    return (
        datetime.combine(start, datetime.min.time()).isoformat(timespec="seconds"),
        datetime.combine(end, datetime.max.time()).isoformat(timespec="seconds"),
    )


@app.post("/api/admin/login", response_model=AdminLoginResponse)
def login_admin(payload: AdminLoginPayload) -> AdminLoginResponse:
    # Autentikasi admin lalu buat token sesi.
    if not _has_configured_admin():
        raise HTTPException(
            status_code=503,
            detail="Admin belum dikonfigurasi. Tambahkan admin ke database aplikasi.",
        )

    email = payload.email.strip().lower()
    password = payload.password
    admin = _find_admin(email)
    if admin is None or not hmac.compare_digest(str(admin.get("password") or ""), password):
        raise HTTPException(status_code=401, detail="Email atau password admin salah.")

    token, expires_at = _create_admin_token(email)
    return AdminLoginResponse(
        email=email,
        name=admin.get("name") or "Admin",
        token=token,
        expires_at=expires_at.isoformat(timespec="seconds"),
    )


@app.post("/api/admin/admins", response_model=AdminAccountResponse)
def create_admin_account(
    payload: AdminCreatePayload,
    authorization: str = Header(default=""),
) -> AdminAccountResponse:
    # Tambahkan akun admin baru dari sesi admin yang sudah login.
    _require_admin(authorization)
    admin = _add_admin_config(
        email=payload.email,
        password=payload.password,
        name=payload.name,
    )
    return AdminAccountResponse(email=admin["email"], name=admin["name"])


@app.post("/api/admin/faq-image", response_model=AdminDocumentResponse)
def upload_pinned_faq_image(
    payload: AdminDocumentPayload,
    authorization: str = Header(default=""),
) -> AdminDocumentResponse:
    # Ganti aset gambar organogram pinned.
    _require_admin(authorization)
    extension = Path(unquote(payload.filename)).suffix.lower()
    if extension not in PINNED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Gambar harus berformat .webp, .png, atau .jpg.",
        )

    content = _decode_document(payload.content_base64)
    replace_pinned_image(content, extension)
    return AdminDocumentResponse(message="Gambar FAQ diperbarui.")


@app.post("/api/admin/faq", response_model=AdminFAQResponse)
def create_faq(
    payload: AdminFAQPayload,
    authorization: str = Header(default=""),
) -> AdminFAQResponse:
    # Buat lalu simpan FAQ baru.
    _require_admin(authorization)
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
    authorization: str = Header(default=""),
) -> AdminFAQResponse:
    # Buat ulang lalu ganti FAQ yang sudah ada.
    _require_admin(authorization)
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
    authorization: str = Header(default=""),
) -> AdminFAQResponse:
    # Hapus satu FAQ tersimpan berdasarkan ID.
    _require_admin(authorization)
    with FAQ_LOCK:
        items = _load_faqs()
        index = _find_faq_index(items, faq_id)
        items.pop(index)
        _save_faqs(items)
    return AdminFAQResponse(message="FAQ deleted.")


@app.get("/api/library", response_model=list[LibraryItem])
def get_library() -> list[LibraryItem]:
    # Kembalikan daftar library dokumen yang bisa dilihat guest dan admin.
    return _iter_library_items()


@app.get("/api/admin/logs", response_model=list[ActivityLogItem])
def get_activity_logs(
    start_date: str | None = None,
    end_date: str | None = None,
    conversation_id: str | None = None,
    feedback: str | None = None,
    limit: Annotated[int, Query(ge=1, le=250)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    authorization: str = Header(default=""),
) -> list[ActivityLogItem]:
    # Kembalikan activity log chat untuk dashboard pemakaian chatbot.
    _require_admin(authorization)
    if feedback not in {None, "", "all", "negative"}:
        raise HTTPException(status_code=422, detail="Filter feedback tidak valid.")
    start_at, end_at = _activity_date_range(start_date, end_date)
    return [
        ActivityLogItem(**item)
        for item in list_activity_logs(
            event_type="chat",
            start_at=start_at,
            end_at=end_at,
            conversation_id=conversation_id,
            negative_feedback_only=feedback == "negative",
            limit=limit,
            offset=offset,
        )
    ]


@app.get("/api/admin/logs/sessions", response_model=list[ActivityLogSessionItem])
def get_activity_log_sessions(
    start_date: str | None = None,
    end_date: str | None = None,
    authorization: str = Header(default=""),
) -> list[ActivityLogSessionItem]:
    # Kembalikan daftar sesi chat dalam date range yang dipilih.
    _require_admin(authorization)
    start_at, end_at = _activity_date_range(start_date, end_date)
    return [
        ActivityLogSessionItem(**item)
        for item in list_activity_log_sessions(
            event_type="chat",
            start_at=start_at,
            end_at=end_at,
        )
    ]


@app.delete("/api/admin/logs/{log_id}", response_model=AdminFAQResponse)
def delete_activity_log_item(
    log_id: int,
    authorization: str = Header(default=""),
) -> AdminFAQResponse:
    # Hapus satu activity log chat dari dashboard admin.
    _require_admin(authorization)
    deleted = delete_activity_log(log_id, event_type="chat")
    if not deleted:
        raise HTTPException(status_code=404, detail="Log not found.")
    return AdminFAQResponse(message="Log deleted.")


@app.delete("/api/admin/logs/sessions/{conversation_id}", response_model=AdminFAQResponse)
def delete_activity_log_session(
    conversation_id: str,
    authorization: str = Header(default=""),
) -> AdminFAQResponse:
    # Hapus semua activity log chat dalam satu session.
    _require_admin(authorization)
    deleted_count = delete_activity_logs_for_conversation(
        unquote(conversation_id),
        event_type="chat",
    )
    if not deleted_count:
        raise HTTPException(status_code=404, detail="Session not found.")
    return AdminFAQResponse(message="Session logs deleted.")


@app.get("/api/admin/logs/summary", response_model=ActivityLogSummaryResponse)
def get_activity_log_summary(
    start_date: str | None = None,
    end_date: str | None = None,
    conversation_id: str | None = None,
    authorization: str = Header(default=""),
) -> ActivityLogSummaryResponse:
    # Ringkasan pemakaian chatbot untuk rentang tanggal yang sama dengan list log.
    _require_admin(authorization)
    start_at, end_at = _activity_date_range(start_date, end_date)
    return ActivityLogSummaryResponse(
        **summarize_activity_logs(
            event_type="chat",
            start_at=start_at,
            end_at=end_at,
            conversation_id=conversation_id,
        )
    )


@app.post("/api/admin/documents", response_model=AdminDocumentResponse)
def save_document(
    payload: AdminDocumentPayload,
    authorization: str = Header(default=""),
) -> AdminDocumentResponse:
    # Tambahkan atau ganti dokumen backend yang dikelola.
    _require_admin(authorization)
    filename = Path(unquote(payload.filename)).name
    data_dir = _get_data_dir().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(filename).suffix.lower()
    if suffix not in LIBRARY_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported document type.")
    if suffix == ".docx" and _document_kind_for_path(Path(filename)) == "form":
        raise HTTPException(
            status_code=400,
            detail="Upload form Word tidak didukung. Upload PDF form agar versi Word dibuat otomatis.",
        )

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
    if suffix == ".pdf":
        clear_flowchart_cache_for_source(target_path.name)
    if suffix == ".pdf" and _document_kind_for_path(target_path) == "form":
        logger.info(
            "[admin-documents] Form PDF %s tersimpan, mulai buat template Word",
            target_path.name,
        )
        ensure_form_docx_template(target_path, replace=True)
    requires_reindex = _is_embeddable_path(target_path)
    message = f"Document {action}."
    return AdminDocumentResponse(
        message=message,
        requires_reindex=requires_reindex,
        item=_to_library_item(target_path, data_dir),
    )


@app.delete("/api/admin/documents/{document_path:path}", response_model=AdminDocumentResponse)
def delete_document(
    document_path: str,
    authorization: str = Header(default=""),
) -> AdminDocumentResponse:
    # Hapus satu dokumen terkelola dan laporkan kebutuhan reindex.
    _require_admin(authorization)
    target_path = _resolve_document_path(document_path)
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")
    if target_path.suffix.lower() not in LIBRARY_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported document type.")

    requires_reindex = _is_embeddable_path(target_path)
    if target_path.suffix.lower() == ".pdf" and _document_kind_for_path(target_path) == "form":
        delete_form_docx_template(target_path)
    target_path.unlink()
    if target_path.suffix.lower() == ".pdf":
        clear_flowchart_cache_for_source(target_path.name)
    message = "Document deleted."
    return AdminDocumentResponse(
        message=message,
        requires_reindex=requires_reindex,
    )


@app.post("/api/admin/reindex", response_model=AdminReindexResponse)
def reindex_documents(authorization: str = Header(default="")) -> AdminReindexResponse:
    # Bangun ulang vector database dari dokumen sumber saat ini.
    _require_admin(authorization)
    if not REINDEX_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Reindex is already running.")

    try:
        from backend.preprocessing.ingest import main as rebuild_knowledge_base

        reindex_result = rebuild_knowledge_base()
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Rebuild embeddings failed: {error}",
        ) from error
    finally:
        REINDEX_LOCK.release()

    if reindex_result == "cleared":
        return AdminReindexResponse(message="No source documents found. Embeddings cleared.")
    return AdminReindexResponse(message="Embeddings rebuilt.")
