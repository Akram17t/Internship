from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import HTTPException

from backend.cache_db import (
    add_admin_account,
    append_conversation_turn,
    get_conversation_context,
    load_admin_config,
)
from backend.api.core import (
    ADMIN_CONFIG_LOCK,
    CONVERSATION_LOCK,
    ROOT_DIR,
)
from backend.api.models import CitationResponse, FAQItem
from backend.api.storage import _citation_download_url
from backend.settings import get_env


def _get_cache_dir() -> Path:
    # Tentukan folder cache lokal untuk FAQ JSON dan legacy import.
    raw_dir = get_env("CONVERSATION_CACHE_DIR", "backend/cache")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _get_faq_file() -> Path:
    # Kembalikan path file cache FAQ.
    return _get_cache_dir() / "faqs.json"


def _load_admin_config() -> dict[str, object]:
    # Muat config admin dari app_state DB.
    with ADMIN_CONFIG_LOCK:
        return load_admin_config()


def _add_admin_config(email: str, password: str, name: str) -> dict[str, str]:
    # Tambahkan admin baru ke app_state DB dan cegah email duplikat.
    with ADMIN_CONFIG_LOCK:
        try:
            return add_admin_account(email=email, password=password, name=name)
        except ValueError as error:
            if str(error) == "duplicate_email":
                raise HTTPException(status_code=409, detail="Email admin sudah terdaftar.") from error
            if str(error) == "missing_credentials":
                raise HTTPException(
                    status_code=422,
                    detail="Email dan password admin wajib diisi.",
                ) from error
            raise HTTPException(status_code=409, detail="Email admin sudah terdaftar.")


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
    with CONVERSATION_LOCK:
        return get_conversation_context(conversation_id)


def _append_conversation_turn(conversation_id: str, question: str, answer: str) -> None:
    # Tambahkan satu pasangan turn user/assistant ke cache percakapan.
    with CONVERSATION_LOCK:
        append_conversation_turn(conversation_id, question, answer)


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
    # Muat item FAQ dari cache JSON lokal.
    path = _get_faq_file()
    if not path.exists():
        return []

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
    # Simpan item FAQ ke cache JSON lokal.
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
    # Cari index item FAQ berdasarkan ID atau lempar 404.
    for index, item in enumerate(items):
        if item.id == faq_id:
            return index
    raise HTTPException(status_code=404, detail="FAQ not found.")
