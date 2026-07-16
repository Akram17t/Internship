from __future__ import annotations

import hmac
import logging
from pathlib import Path
from urllib.parse import unquote

from fastapi import Header, HTTPException

from backend.api.auth import _admin_email, _admin_name, _admin_password, _create_admin_token, _require_admin
from backend.api.cache_store import _find_faq_index, _load_faqs, _save_faqs
from backend.api.core import ASSETS_DIR, FAQ_LOCK, LIBRARY_EXTENSIONS, REINDEX_LOCK, app
from backend.api.faq_service import PINNED_IMAGE_EXTENSIONS, PINNED_IMAGE_STEM, _build_faq_item
from backend.api.form_schema_generator import delete_schema_for_form_pdf, generate_schema_for_form_pdf
from backend.api.flowchart_service import clear_flowchart_cache_for_source
from backend.api.models import (
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

logger = logging.getLogger("uvicorn.error")


@app.post("/api/admin/login", response_model=AdminLoginResponse)
def login_admin(payload: AdminLoginPayload) -> AdminLoginResponse:
    # Autentikasi admin lalu buat token sesi.
    if not _admin_email() or not _admin_password():
        raise HTTPException(
            status_code=503,
            detail="Admin belum dikonfigurasi. Isi email dan password di backend/cache/admin.json.",
        )

    email = payload.email.strip().lower()
    password = payload.password
    if (
        not hmac.compare_digest(email, _admin_email())
        or not hmac.compare_digest(password, _admin_password())
    ):
        raise HTTPException(status_code=401, detail="Email atau password admin salah.")

    token, expires_at = _create_admin_token(email)
    return AdminLoginResponse(
        email=email,
        name=_admin_name(),
        token=token,
        expires_at=expires_at.isoformat(timespec="seconds"),
    )


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
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    # Simpan hanya satu gambar organogram: hapus varian ekstensi lain dulu.
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
def get_library(authorization: str = Header(default="")) -> list[LibraryItem]:
    # Kembalikan daftar library dokumen admin.
    _require_admin(authorization)
    return _iter_library_items()


@app.post("/api/admin/documents", response_model=AdminDocumentResponse)
def save_document(
    payload: AdminDocumentPayload,
    authorization: str = Header(default=""),
) -> AdminDocumentResponse:
    # Tambahkan atau ganti dokumen backend yang dikelola.
    _require_admin(authorization)
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
    if suffix == ".pdf":
        clear_flowchart_cache_for_source(target_path.name)
    schema_result = None
    if suffix == ".pdf" and _document_kind_for_path(target_path) == "form":
        logger.info(
            "[admin-documents] Form PDF %s tersimpan, mulai generate schema otomatis",
            target_path.name,
        )
        schema_result = generate_schema_for_form_pdf(target_path)
        if schema_result.generated:
            logger.info(
                "[admin-documents] Schema form otomatis selesai file=%s schema=%s",
                target_path.name,
                schema_result.schema_path,
            )
        else:
            logger.warning(
                "[admin-documents] Schema form otomatis gagal file=%s error=%s",
                target_path.name,
                schema_result.error,
            )
    requires_reindex = _is_embeddable_path(target_path)
    message = f"Document {action}."
    return AdminDocumentResponse(
        message=message,
        requires_reindex=requires_reindex,
        item=_to_library_item(target_path, data_dir),
        schema_generated=bool(schema_result and schema_result.generated),
        schema_path=schema_result.schema_path if schema_result else None,
        schema_error=schema_result.error if schema_result else None,
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
    schema_deleted = None
    if target_path.suffix.lower() == ".pdf" and _document_kind_for_path(target_path) == "form":
        schema_deleted = delete_schema_for_form_pdf(target_path)
    target_path.unlink()
    if target_path.suffix.lower() == ".pdf":
        clear_flowchart_cache_for_source(target_path.name)
    message = "Document deleted."
    return AdminDocumentResponse(
        message=message,
        requires_reindex=requires_reindex,
        schema_path=schema_deleted.schema_path if schema_deleted else None,
    )


@app.post("/api/admin/reindex", response_model=AdminReindexResponse)
def reindex_documents(authorization: str = Header(default="")) -> AdminReindexResponse:
    # Bangun ulang vector database dari dokumen sumber saat ini.
    _require_admin(authorization)
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
