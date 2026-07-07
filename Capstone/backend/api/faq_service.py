from __future__ import annotations

import uuid
from datetime import datetime
from urllib.parse import quote

from fastapi import HTTPException

from backend.api.core import ASSETS_DIR
from backend.api.models import AdminFAQPayload, CitationResponse, FAQItem


def _is_unusable_faq_answer(answer: str, citations: list[CitationResponse]) -> bool:
    # Tolak jawaban FAQ yang tidak punya evidence atau terlalu generik.
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
    # Buat dan validasi satu entri FAQ dari pertanyaan.
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


# FAQ pinned statis yang selalu tampil paling atas.
# Item ini tidak disimpan di faqs.json dan tidak bisa diedit/dihapus biasa.
# Hanya gambarnya yang bisa diganti lewat POST /api/admin/faq-image.
PINNED_IMAGE_STEM = "organogram"
PINNED_IMAGE_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg"}


def _pinned_image_name() -> str:
    # Kembalikan nama file gambar FAQ pinned yang aktif.
    for extension in (".webp", ".png", ".jpg", ".jpeg"):
        if (ASSETS_DIR / f"{PINNED_IMAGE_STEM}{extension}").exists():
            return f"{PINNED_IMAGE_STEM}{extension}"
    return f"{PINNED_IMAGE_STEM}.webp"


def _pinned_image_url() -> str:
    # Kembalikan URL cache-busted untuk gambar FAQ pinned.
    name = _pinned_image_name()
    path = ASSETS_DIR / name
    # Tambahkan cache-bust dari mtime agar browser reload setelah gambar diganti.
    version = int(path.stat().st_mtime) if path.exists() else 0
    return f"/assets/{name}?v={version}"


def _pinned_faq_items() -> list[FAQItem]:
    # Buat kartu FAQ statis untuk entri organogram.
    return [
        FAQItem(
            id="",
            question="Bagaimana struktur organisasi ICS Compute?",
            answer="Berikut struktur organisasi (organogram) ICS Compute.",
            suggested_query="Bagaimana struktur organisasi ICS Compute?",
            image_url=_pinned_image_url(),
        ),
    ]
