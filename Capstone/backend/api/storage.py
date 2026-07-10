from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import HTTPException

from backend.answer_policy import is_unsupported_answer
from backend.api.core import EMBEDDABLE_EXTENSIONS, LIBRARY_EXTENSIONS, MAX_DOCUMENT_BYTES, ROOT_DIR
from backend.api.models import FormDownloadResponse, LibraryItem
from backend.settings import get_env


def _get_data_dir() -> Path:
    # Tentukan folder data backend dari konfigurasi env.
    raw_dir = get_env("DATA_DIR", "backend/data")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _document_kind_for_path(path: Path) -> str:
    # Klasifikasikan file tersimpan sebagai form, SOP, atau dokumen umum.
    # Semua dokumen kini PDF, jadi jenis ditentukan murni dari awalan nama file.
    name = path.stem.lower()
    if name.startswith("form"):
        return "form"
    if name.startswith("sop"):
        return "sop"
    return "document"


def _is_embeddable_path(path: Path) -> bool:
    # Kembalikan True jika file perlu masuk ke vector DB.
    # Template form dikecualikan agar tidak ikut terindeks sebagai sumber jawaban.
    return (
        path.suffix.lower() in EMBEDDABLE_EXTENSIONS
        and _document_kind_for_path(path) != "form"
    )


def _to_library_item(path: Path, data_dir: Path) -> LibraryItem:
    # Ubah file tersimpan menjadi bentuk respons library admin.
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
    # Daftar semua file yang didukung di folder data saat ini.
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


def _format_form_display_name(path: Path) -> str:
    # Ubah nama file form mentah menjadi label yang lebih rapi.
    return (
        path.stem.replace("Form - ", "")
        .replace("(Template)", "")
        .replace("_", " ")
        .strip()
    )


def _form_download_response(path: Path, data_dir: Path) -> FormDownloadResponse:
    # Bentuk payload download publik untuk file form.
    relative_path = path.relative_to(data_dir).as_posix()
    return FormDownloadResponse(
        name=path.name,
        display_name=_format_form_display_name(path),
        download_url=f"/api/documents/{quote(relative_path, safe='/')}",
    )


def _iter_form_downloads() -> list[FormDownloadResponse]:
    # Daftar semua template form yang bisa diunduh.
    data_dir = _get_data_dir()
    if not data_dir.exists():
        return []

    forms: list[FormDownloadResponse] = []
    for path in _iter_form_paths(data_dir):
        forms.append(_form_download_response(path, data_dir))
    return forms


def _iter_form_paths(data_dir: Path | None = None) -> list[Path]:
    # Kumpulkan semua path template form PDF (nama diawali "Form").
    data_dir = data_dir or _get_data_dir()
    if not data_dir.exists():
        return []

    paths: list[Path] = []
    for path in sorted(data_dir.rglob("*.pdf")):
        if not path.is_file() or _document_kind_for_path(path) != "form":
            continue
        paths.append(path)
    return paths


def _available_form_catalog(forms: list[FormDownloadResponse]) -> str:
    # Ubah daftar form menjadi katalog yang bisa dipilih AI.
    if not forms:
        return "[]"

    return json.dumps(
        [
            {
                "name": form.name,
                "display_name": form.display_name,
            }
            for form in forms
        ],
        ensure_ascii=False,
    )


def _form_lookup_keys(form: FormDownloadResponse) -> set[str]:
    # Buat key pencocokan longgar untuk satu pilihan form.
    return {
        form.name.strip().lower(),
        form.display_name.strip().lower(),
        Path(form.name).stem.strip().lower(),
        Path(form.display_name).stem.strip().lower(),
    }


def _selected_form_downloads(
    selected_names: list[str],
    forms: list[FormDownloadResponse],
) -> list[FormDownloadResponse]:
    # Cocokkan nama form pilihan AI ke payload download yang nyata.
    if not selected_names or not forms:
        return []

    lookup: dict[str, FormDownloadResponse] = {}
    for form in forms:
        for key in _form_lookup_keys(form):
            if key:
                lookup[key] = form

    selected: list[FormDownloadResponse] = []
    seen_names: set[str] = set()
    for raw_name in selected_names:
        form = lookup.get(raw_name.strip().lower())
        if form is None or form.name in seen_names:
            continue
        selected.append(form)
        seen_names.add(form.name)
    return selected


def _answer_has_supported_form_context(answer: str) -> bool:
    # Sembunyikan form download jika jawabannya sebenarnya fallback tanpa sumber.
    return not is_unsupported_answer(answer)


def _resolve_document_path(document_path: str) -> Path:
    # Tentukan path dokumen relatif sambil mencegah path traversal.
    data_dir = _get_data_dir().resolve()
    resolved_path = (data_dir / unquote(document_path)).resolve()

    try:
        resolved_path.relative_to(data_dir)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid document path.") from error

    return resolved_path


def _decode_document(content_base64: str) -> bytes:
    # Decode file upload base64 dan terapkan batas ukuran.
    try:
        payload = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status_code=400, detail="Invalid document payload.") from error

    if not payload:
        raise HTTPException(status_code=400, detail="Document cannot be empty.")
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Document is too large.")
    return payload
