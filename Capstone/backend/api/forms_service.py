from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import HTTPException

from backend.api.storage import _document_kind_for_path

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def form_docx_template_path(pdf_path: Path) -> Path:
    if pdf_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Template form harus berupa PDF.")
    return pdf_path.with_suffix(".docx")


def _validate_form_pdf(pdf_path: Path) -> None:
    if not pdf_path.exists() or not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="Form not found.")
    if pdf_path.suffix.lower() != ".pdf" or _document_kind_for_path(pdf_path) != "form":
        raise HTTPException(status_code=400, detail="Dokumen ini bukan template form PDF.")


def _convert_pdf_to_docx_file(pdf_path: Path, docx_path: Path) -> None:
    try:
        from pdf2docx import Converter
    except ImportError as error:
        raise HTTPException(
            status_code=500,
            detail="Converter Word belum terpasang. Jalankan pip install -r requirements.txt.",
        ) from error

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    converter = Converter(str(pdf_path))
    try:
        converter.convert(str(docx_path), start=0, end=None)
    finally:
        converter.close()

    if not docx_path.exists() or docx_path.stat().st_size <= 0:
        raise HTTPException(status_code=500, detail="Template Word gagal dibuat.")


def ensure_form_docx_template(pdf_path: Path, *, replace: bool = False) -> Path:
    _validate_form_pdf(pdf_path)
    target_path = form_docx_template_path(pdf_path)
    if target_path.exists() and target_path.stat().st_size > 0 and not replace:
        return target_path

    with tempfile.TemporaryDirectory() as temporary_dir:
        temporary_path = Path(temporary_dir) / target_path.name
        _convert_pdf_to_docx_file(pdf_path, temporary_path)
        shutil.move(str(temporary_path), str(target_path))

    return target_path


def get_form_docx_template(pdf_path: Path) -> Path:
    return ensure_form_docx_template(pdf_path, replace=False)


def delete_form_docx_template(pdf_path: Path) -> Path | None:
    target_path = form_docx_template_path(pdf_path)
    if not target_path.exists():
        return None
    target_path.unlink()
    return target_path
