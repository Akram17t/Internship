from __future__ import annotations

import uuid

from fastapi import HTTPException

from backend.cache_db import (
    add_admin_by_email,
    append_conversation_turn,
    get_conversation_context,
    list_faq_items,
    replace_faq_items,
)
from backend.api.core import ADMIN_CONFIG_LOCK
from backend.api.models import CitationResponse, FAQItem
from backend.api.storage import _citation_download_url


def _add_admin_by_email(email: str, name: str = "") -> dict[str, str]:
    # Tambahkan admin baru (by email) ke app_state DB dan cegah email duplikat.
    with ADMIN_CONFIG_LOCK:
        try:
            return add_admin_by_email(email=email, name=name)
        except ValueError as error:
            if str(error) == "duplicate_email":
                raise HTTPException(status_code=409, detail="Admin email is already registered.") from error
            if str(error) == "missing_email":
                raise HTTPException(
                    status_code=422,
                    detail="Admin email is required.",
                ) from error
            raise HTTPException(status_code=409, detail="Admin email is already registered.")


def _clean_conversation_id(value: str | None) -> str:
    # Sanitasi conversation ID dari client atau buat yang baru.
    if not value:
        return uuid.uuid4().hex

    cleaned = "".join(char for char in value if char.isalnum() or char in {"-", "_"})
    if 8 <= len(cleaned) <= 80:
        return cleaned
    return uuid.uuid4().hex


def _get_conversation_context(conversation_id: str) -> str:
    # Ubah turn terbaru menjadi context teks untuk rewrite query.
    # get_conversation_context() sudah pakai STATE_DB_LOCK sendiri di cache_db.py,
    # jadi tidak perlu lock kedua di sini.
    return get_conversation_context(conversation_id)


def _append_conversation_turn(
    conversation_id: str,
    question: str,
    answer: str,
    *,
    answer_source: str | None = None,
    feedback_id: int | None = None,
    feedback_token: str | None = None,
    duration_ms: int | None = None,
    citations: list | None = None,
    form_downloads: list | None = None,
) -> None:
    # Tambahkan satu pasangan turn user/assistant ke cache percakapan, lengkap
    # dengan asal jawaban, referensi feedback, dan citation supaya percakapan
    # lama tetap menampilkan badge, tombol feedback, dan chip sumber saat
    # dibuka kembali.
    append_conversation_turn(
        conversation_id,
        question,
        answer,
        answer_source=answer_source,
        feedback_id=feedback_id,
        feedback_token=feedback_token,
        duration_ms=duration_ms,
        citations=citations,
        form_downloads=form_downloads,
    )


def _normalize_citation(raw_item: object, index: int) -> CitationResponse | None:
    # Normalisasi satu dict citation mentah ke model respons API.
    if not isinstance(raw_item, dict):
        return None

    source = str(raw_item.get("source", "")).strip()
    if not source:
        return None

    return CitationResponse(
        id=int(raw_item.get("id") or index + 1),
        source=source,
        page=raw_item.get("page") if isinstance(raw_item.get("page"), int) else None,
        page_end=raw_item.get("page_end") if isinstance(raw_item.get("page_end"), int) else None,
        section=str(raw_item.get("section", "")).strip() or None,
        chunk_id=raw_item.get("chunk_id") if isinstance(raw_item.get("chunk_id"), int) else None,
        download_url=str(raw_item.get("download_url", "")).strip() or _citation_download_url(source),
    )


def _normalize_citations(item: dict[str, object]) -> list[CitationResponse]:
    # Normalisasi citation dengan fallback legacy source/source_url.
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
    # Normalisasi satu record FAQ tersimpan ke model API.
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
    # Muat item FAQ dari app_state DB.
    return [
        item
        for item in (
            _normalize_faq_item(raw_item)
            for raw_item in list_faq_items()
            if isinstance(raw_item, dict)
        )
        if item is not None
    ]


def _save_faqs(items: list[FAQItem]) -> None:
    # Simpan item FAQ ke app_state DB.
    payload = [
        item.model_dump() if hasattr(item, "model_dump") else item.dict()
        for item in items
    ]
    replace_faq_items(payload)


def _find_faq_index(items: list[FAQItem], faq_id: str) -> int:
    # Cari index item FAQ berdasarkan ID atau lempar 404.
    for index, item in enumerate(items):
        if item.id == faq_id:
            return index
    raise HTTPException(status_code=404, detail="FAQ not found.")
