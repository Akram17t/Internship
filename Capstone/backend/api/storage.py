from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import HTTPException

from backend.answer_policy import is_unsupported_answer
from backend.api.core import (
    EMBEDDABLE_EXTENSIONS,
    FORM_EXTENSIONS,
    LIBRARY_EXTENSIONS,
    MAX_DOCUMENT_BYTES,
    ROOT_DIR,
)
from backend.api.models import FormDownloadResponse, LibraryItem
from backend.settings import get_env

FORM_CONTAINER_DIR = "forms"
FORM_SOP_ALIASES = {
    "backup log": "backup informasi",
    "system access control list": "kontrol akses",
    "incident report": "manajemen insiden",
    "perjalanan dinas": "perjalanan dinas",
    "exit clearance": "terminasi hubungan kerja",
    "exit interview": "terminasi hubungan kerja",
    "onboarding preparation": "administrasi karyawan",
}
FORM_INTENT_TERMS = {
    "access",
    "akses",
    "apply",
    "backup",
    "clearance",
    "download",
    "excel",
    "exit",
    "form",
    "formulir",
    "incident",
    "interview",
    "laporan",
    "muka",
    "onboarding",
    "permohonan",
    "procedure",
    "procedures",
    "request",
    "template",
    "travel",
    "trip",
    "uang",
    "word",
}


def _get_data_dir() -> Path:
    # Tentukan folder data backend dari konfigurasi env.
    raw_dir = get_env("DATA_DIR", "backend/data")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _document_kind_for_path(path: Path) -> str:
    # Klasifikasikan file tersimpan sebagai form, SOP, atau dokumen umum.
    # Form baru bisa disimpan di DATA_DIR/forms/<sop-key>/ tanpa prefix "Form".
    if any(part.lower() == FORM_CONTAINER_DIR for part in path.parts):
        return "form"
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


def _clean_document_label(value: str) -> str:
    label = Path(value).stem
    label = re.sub(r"(?i)^\s*(?:form|sop)\s*[-_]*\s*", "", label)
    label = re.sub(r"(?i)\btemplate\b", "", label)
    label = re.sub(r"\(\s*\)", "", label)
    label = label.replace("_", " ").replace("-", " ")
    label = re.sub(r"\s+", " ", label)
    return label.strip()


def _relation_key(value: str) -> str:
    value = _clean_document_label(value).lower()
    value = re.sub(r"[^a-z0-9\u00c0-\u024f]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _safe_form_folder_name(sop_path: Path) -> str:
    key = _relation_key(sop_path.stem) or sop_path.stem.lower()
    key = re.sub(r"[^a-z0-9]+", "-", key).strip("-")
    return key or "sop"


def _format_file_display_name(path: Path) -> str:
    return _clean_document_label(path.name) or path.stem.replace("_", " ").strip() or path.name


def _form_download_formats(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return ["pdf", "docx"]
    if suffix == ".docx":
        return ["docx"]
    if suffix in {".xlsx", ".xls"}:
        return [suffix.lstrip(".")]
    return [suffix.lstrip(".")] if suffix else []


def _is_form_docx_sidecar(path: Path) -> bool:
    return (
        path.suffix.lower() == ".docx"
        and _document_kind_for_path(path) == "form"
        and path.with_suffix(".pdf").exists()
    )


def _iter_form_anchor_paths(data_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(data_dir.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in LIBRARY_EXTENSIONS
        and _document_kind_for_path(path) != "form"
    ]


def _linked_sop_path_for_form(path: Path, data_dir: Path) -> str | None:
    relative_path = path.relative_to(data_dir)
    parts = relative_path.parts
    if len(parts) >= 3 and parts[0].lower() == FORM_CONTAINER_DIR:
        folder_key = parts[1].lower()
        for anchor_path in _iter_form_anchor_paths(data_dir):
            if _safe_form_folder_name(anchor_path) == folder_key:
                return anchor_path.relative_to(data_dir).as_posix()

    form_key = _relation_key(path.stem)
    expected_sop_key = ""
    for form_alias, sop_alias in FORM_SOP_ALIASES.items():
        if form_alias in form_key:
            expected_sop_key = sop_alias
            break

    form_tokens = set(form_key.split())
    best_path: Path | None = None
    best_score = 0
    for anchor_path in _iter_form_anchor_paths(data_dir):
        sop_key = _relation_key(anchor_path.stem)
        if expected_sop_key and expected_sop_key in sop_key:
            return anchor_path.relative_to(data_dir).as_posix()
        score = len(form_tokens.intersection(sop_key.split()))
        if score > best_score:
            best_score = score
            best_path = anchor_path
    if best_path is not None and best_score > 0:
        return best_path.relative_to(data_dir).as_posix()
    return None


def _form_upload_dir_for_sop(data_dir: Path, sop_path: Path) -> Path:
    return data_dir / FORM_CONTAINER_DIR / _safe_form_folder_name(sop_path)


def _to_library_item(path: Path, data_dir: Path) -> LibraryItem:
    # Ubah file tersimpan menjadi bentuk respons library admin.
    relative_path = path.relative_to(data_dir).as_posix()
    stat = path.stat()
    display_name = _format_file_display_name(path)
    document_kind = _document_kind_for_path(path)
    return LibraryItem(
        name=path.name,
        relative_path=relative_path,
        display_name=display_name.title(),
        doc_type=path.suffix.lower().lstrip("."),
        document_kind=document_kind,
        is_embeddable=_is_embeddable_path(path),
        size_bytes=stat.st_size,
        updated_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        download_url=f"/api/documents/{quote(relative_path, safe='/')}",
        linked_sop_path=_linked_sop_path_for_form(path, data_dir)
        if document_kind == "form"
        else None,
        formats=_form_download_formats(path) if document_kind == "form" else [],
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
        if path.name.startswith("~$"):  # skip temporary office lock files
            continue
        if _is_form_docx_sidecar(path):
            continue

        items.append(_to_library_item(path, data_dir))

    return items


def _format_form_display_name(path: Path) -> str:
    # Ubah nama file form mentah menjadi label yang lebih rapi.
    return _format_file_display_name(path)


def _form_download_response(path: Path, data_dir: Path) -> FormDownloadResponse:
    # Bentuk payload download publik untuk file form.
    relative_path = path.relative_to(data_dir).as_posix()
    return FormDownloadResponse(
        name=path.name,
        display_name=_format_form_display_name(path),
        download_url=f"/api/documents/{quote(relative_path, safe='/')}",
        doc_type=path.suffix.lower().lstrip("."),
        formats=_form_download_formats(path),
        linked_sop_path=_linked_sop_path_for_form(path, data_dir),
    )


def _citation_download_url(source: str) -> str:
    # Citation memakai endpoint publik terpisah dari library admin.
    return f"/api/citations/{quote(source, safe='')}" if source else ""


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
    # Kumpulkan semua path form download-only, termasuk Word/Excel.
    data_dir = data_dir or _get_data_dir()
    if not data_dir.exists():
        return []

    paths: list[Path] = []
    for path in sorted(data_dir.rglob("*")):
        if path.suffix.lower() not in FORM_EXTENSIONS:
            continue
        if not path.is_file() or _document_kind_for_path(path) != "form":
            continue
        if _is_form_docx_sidecar(path):
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
                "doc_type": form.doc_type,
                "linked_sop_path": form.linked_sop_path,
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


def _citation_source_keys(citations: list[dict[str, object]]) -> set[str]:
    keys: set[str] = set()
    for citation in citations:
        source = str(citation.get("source") or "").strip()
        if not source:
            continue
        keys.add(source.lower())
        keys.add(Path(source).name.lower())
    return keys


def _form_matches_cited_sop(form: FormDownloadResponse, source_keys: set[str]) -> bool:
    linked = str(form.linked_sop_path or "").strip()
    if not linked:
        return False
    return linked.lower() in source_keys or Path(linked).name.lower() in source_keys


def _content_matches_form(form: FormDownloadResponse, text: str) -> bool:
    text_key = _relation_key(text)
    if not text_key:
        return False
    text_tokens = set(text_key.split())
    has_form_intent = bool(text_tokens.intersection(FORM_INTENT_TERMS))
    form_tokens = {
        token
        for token in _relation_key(f"{form.name} {form.display_name}").split()
        if len(token) > 2 and token not in {"template", "form"}
    }
    return has_form_intent or bool(text_tokens.intersection(form_tokens))


def _related_form_downloads_for_citations(
    *,
    question: str,
    answer: str,
    citations: list[dict[str, object]],
    forms: list[FormDownloadResponse],
) -> list[FormDownloadResponse]:
    if not citations or not forms:
        return []
    source_keys = _citation_source_keys(citations)
    text = f"{question}\n{answer}"
    related: list[FormDownloadResponse] = []
    seen: set[str] = set()
    for form in forms:
        if form.name in seen:
            continue
        if not _form_matches_cited_sop(form, source_keys):
            continue
        if not _content_matches_form(form, text):
            continue
        related.append(form)
        seen.add(form.name)
    return related


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


def _resolve_citation_document_path(document_path: str) -> Path:
    # Citation biasanya menyimpan nama file saja; cari di DATA_DIR jika bukan path relatif penuh.
    resolved_path = _resolve_document_path(document_path)
    if resolved_path.exists():
        return resolved_path

    data_dir = _get_data_dir().resolve()
    raw_path = unquote(document_path).replace("\\", "/")
    if "/" in raw_path:
        return resolved_path

    source_name = Path(raw_path).name
    if not source_name:
        return resolved_path

    matches = [
        path.resolve()
        for path in data_dir.rglob(source_name)
        if path.is_file() and path.name == source_name
    ]
    if len(matches) == 1:
        return matches[0]
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
