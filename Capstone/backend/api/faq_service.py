from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from backend.answer_policy import is_unsupported_answer
from backend.api.core import ASSETS_DIR
from backend.api.models import AdminFAQPayload, CitationResponse, FAQItem
from backend.api.storage import _citation_download_url, _get_data_dir
from backend.settings import get_env


def _is_unusable_faq_answer(answer: str, citations: list[CitationResponse]) -> bool:
    # Tolak jawaban FAQ yang tidak punya evidence atau terlalu generik.
    normalized = " ".join(answer.lower().split())
    return not citations or is_unsupported_answer(answer) or "[nama perusahaan]" in normalized


def _build_faq_item(payload: AdminFAQPayload, faq_id: str | None = None) -> FAQItem:
    # Buat dan validasi satu entri FAQ dari pertanyaan.
    from researcher_crew.main import ModelGenerationError, run_faq_crew

    question = payload.question.strip()
    try:
        answer, raw_citations = run_faq_crew(question)
    except ModelGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    citations = [
        CitationResponse(
            **citation,
            download_url=_citation_download_url(str(citation["source"])),
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
# Item ini tidak disimpan sebagai FAQ DB biasa dan tidak bisa diedit/dihapus biasa.
# Hanya gambarnya yang bisa diganti lewat POST /api/admin/faq-image.
PINNED_IMAGE_STEM = "organogram"
PINNED_IMAGE_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg"}


def _persistent_faq_assets_dir() -> Path:
    configured_dir = get_env("FAQ_ASSETS_DIR", "")
    if configured_dir:
        path = Path(configured_dir)
        return path if path.is_absolute() else ASSETS_DIR.parent.parent.parent / path
    return _get_data_dir().parent / "faq_assets"


def _pinned_image_path() -> Path | None:
    # Prioritaskan gambar upload yang persist di storage volume.
    persistent_dir = _persistent_faq_assets_dir()
    for extension in (".webp", ".png", ".jpg", ".jpeg"):
        path = persistent_dir / f"{PINNED_IMAGE_STEM}{extension}"
        if path.exists():
            return path

    for extension in (".webp", ".png", ".jpg", ".jpeg"):
        path = ASSETS_DIR / f"{PINNED_IMAGE_STEM}{extension}"
        if path.exists():
            return path
    return None


def _pinned_image_name() -> str:
    # Kembalikan nama file gambar FAQ pinned yang aktif.
    path = _pinned_image_path()
    return path.name if path is not None else f"{PINNED_IMAGE_STEM}.webp"


def _pinned_image_url() -> str:
    # Kembalikan URL cache-busted untuk gambar FAQ pinned.
    path = _pinned_image_path()
    name = path.name if path is not None else f"{PINNED_IMAGE_STEM}.webp"
    # Tambahkan cache-bust dari mtime agar browser reload setelah gambar diganti.
    version = int(path.stat().st_mtime) if path is not None and path.exists() else 0
    if path is not None and path.parent.resolve() == _persistent_faq_assets_dir().resolve():
        return f"/api/faq-image/{name}?v={version}"
    return f"/assets/{name}?v={version}"


def replace_pinned_image(content: bytes, extension: str) -> Path:
    # Simpan organogram upload di storage volume agar tidak hilang saat Docker rebuild.
    persistent_dir = _persistent_faq_assets_dir()
    persistent_dir.mkdir(parents=True, exist_ok=True)

    for other_extension in PINNED_IMAGE_EXTENSIONS:
        stale = persistent_dir / f"{PINNED_IMAGE_STEM}{other_extension}"
        if stale.exists():
            stale.unlink()

    output_path = persistent_dir / f"{PINNED_IMAGE_STEM}{extension}"
    output_path.write_bytes(content)
    return output_path


def get_pinned_image_file(filename: str) -> Path:
    # Ambil gambar organogram persistent dengan validasi nama file ketat.
    requested = Path(filename).name
    extension = Path(requested).suffix.lower()
    if extension not in PINNED_IMAGE_EXTENSIONS:
        raise FileNotFoundError(filename)
    if Path(requested).stem != PINNED_IMAGE_STEM:
        raise FileNotFoundError(filename)

    path = _persistent_faq_assets_dir() / requested
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(filename)
    return path


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
