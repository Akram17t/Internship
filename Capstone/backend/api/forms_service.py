from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from fastapi import HTTPException

from backend.api.storage import (
    _document_kind_for_path,
    _get_data_dir,
    _resolve_document_path,
)

PDF_MIME = "application/pdf"

# Cocokkan placeholder bracket yang dipakai template form, misalnya "[  ]".
FORM_PLACEHOLDER_PATTERN = re.compile(r"\[[^\[\]]*\]")
# Field segment adalah segmen teks yang seluruh isinya hanya satu bracket.
# Placeholder inline seperti "Nama: [ ]" atau header dilewati agar form tetap singkat.
FORM_FIELD_CELL_PATTERN = re.compile(r"^\[[^\[\]]*\]$")

FORM_FIELD_TYPES = {"text", "textarea", "date", "checkbox", "signature_image"}
IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg"}

# Helvetica bawaan PDF dipakai untuk menulis nilai agar tidak perlu embed font.
_FILL_FONT = "helv"
_MIN_FONT_SIZE = 6.0
_ALIGNMENTS = {"left": 0, "center": 1, "right": 2}


def _page_segments(page, page_number: int) -> list[dict]:
    """Ambil semua segmen teks PDF beserta bbox dari satu halaman."""
    segments: list[dict] = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(char["c"] for span in spans for char in span.get("chars", []))
            if not text.strip():
                continue
            segments.append(
                {
                    "page": page_number,
                    "text": text.strip(),
                    "bbox": tuple(line["bbox"]),
                    "size": spans[0]["size"] if spans else 10.0,
                }
            )
    return segments


def _clean_label(text: str) -> str | None:
    # Rapikan teks kandidat label; buang jika kosong atau masih mengandung bracket.
    candidate = text.strip().rstrip(":").strip()
    if candidate and not FORM_PLACEHOLDER_PATTERN.search(candidate):
        return candidate
    return None


def _segment_label(field: dict, segments: list[dict]) -> str | None:
    """Cari label teks bersih untuk satu segmen placeholder.

    Urutan pencarian: isi bracket dulu, lalu teks terdekat
    di kiri pada baris yang sama, lalu teks tepat di atasnya. Jika tidak ada
    label yang layak, kembalikan None agar segmen itu dilewati.
    """
    inside = field["text"][1:-1].strip()
    if inside:
        return inside

    fx0, fy0, fx1, fy1 = field["bbox"]
    field_center_y = (fy0 + fy1) / 2

    best_left, best_left_x1 = None, float("-inf")
    for segment in segments:
        if segment is field or FORM_FIELD_CELL_PATTERN.match(segment["text"]):
            continue
        x0, y0, x1, y1 = segment["bbox"]
        if y0 <= field_center_y <= y1 and x1 <= fx0 + 2 and x1 > best_left_x1:
            candidate = _clean_label(segment["text"])
            if candidate:
                best_left, best_left_x1 = candidate, x1
    if best_left:
        return best_left

    best_above, best_above_y1 = None, float("-inf")
    for segment in segments:
        if segment is field or FORM_FIELD_CELL_PATTERN.match(segment["text"]):
            continue
        x0, y0, x1, y1 = segment["bbox"]
        if y1 <= fy0 + 2 and not (x1 < fx0 or x0 > fx1) and y1 > best_above_y1:
            candidate = _clean_label(segment["text"])
            if candidate:
                best_above, best_above_y1 = candidate, y1
    return best_above


def _cluster_rows(segments: list[dict]) -> list[dict]:
    """Kelompokkan segmen menjadi baris berdasarkan tumpang tindih vertikal."""
    rows: list[dict] = []
    for segment in sorted(segments, key=lambda s: (round(s["bbox"][1]), s["bbox"][0])):
        top, bottom = segment["bbox"][1], segment["bbox"][3]
        if rows and top < rows[-1]["bottom"] - 1:
            rows[-1]["items"].append(segment)
            rows[-1]["bottom"] = max(rows[-1]["bottom"], bottom)
        else:
            rows.append({"items": [segment], "bottom": bottom})
    return rows


def _field_segments(doc) -> list[dict]:
    """Ambil field placeholder dari blok info atas tiap halaman.

    Hanya blok baris placeholder pertama yang diambil. Bagian lanjutan seperti
    tabel log, teks bebas, atau blok tanda tangan dilewati agar form tetap singkat.
    """
    fields: list[dict] = []
    for page_number, page in enumerate(doc):
        segments = _page_segments(page, page_number)
        started = False
        for row in _cluster_rows(segments):
            row_fields: list[dict] = []
            for segment in sorted(row["items"], key=lambda s: s["bbox"][0]):
                if not FORM_FIELD_CELL_PATTERN.match(segment["text"]):
                    continue
                label = _segment_label(segment, segments)
                if label:
                    x0, y0, x1, y1 = segment["bbox"]
                    row_fields.append(
                        {
                            "key": f"{page_number}:{x0:.0f}:{y0:.0f}:{x1:.0f}:{y1:.0f}",
                            "label": label,
                            "page": page_number,
                            "bbox": segment["bbox"],
                            "size": segment["size"],
                            "row": row["items"],
                        }
                    )
            if row_fields:
                started = True
                fields.extend(row_fields)
            elif started:
                break  # end of the top info block for this page
    return fields


def _scan_form_fields(path: Path) -> list[dict[str, str]]:
    # Kembalikan daftar field {key, label} dari template form PDF.
    with fitz.open(path) as doc:
        return [{"key": field["key"], "label": field["label"]} for field in _field_segments(doc)]


def _unique_form_fields(path: Path) -> list[dict[str, str]]:
    """Hilangkan field duplikat berdasarkan label agar input tidak berulang."""
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for field in _scan_form_fields(path):
        if field["label"] in seen:
            continue
        seen.add(field["label"])
        unique.append({"key": field["label"], "label": field["label"]})
    return unique


def _fit_font_size(page, field: dict, value: str) -> float:
    """Perkecil font agar nilai muat sampai batas kanan placeholder."""
    x0, _y0, x1, y1 = field["bbox"]
    field_center_y = (field["bbox"][1] + y1) / 2
    right_boundary = page.rect.width - 40
    for segment in field["row"]:
        sx0, sy0, _sx1, sy1 = segment["bbox"]
        if sy0 <= field_center_y <= sy1 and sx0 >= x1 - 1:
            right_boundary = min(right_boundary, sx0 - 2)
    available = max(right_boundary - x0, 20)

    size = field["size"]
    while size > _MIN_FONT_SIZE and fitz.get_text_length(value, fontname=_FILL_FONT, fontsize=size) > available:
        size -= 0.5
    return size


def _fill_form_placeholders(path: Path, values: dict[str, str]) -> bytes:
    """Isi setiap field yang labelnya punya nilai lalu kembalikan PDF hasilnya.

    Nilai dipetakan berdasarkan label, jadi satu input bisa mengisi semua field
    dengan label yang sama. Nilai kosong dibiarkan apa adanya.
    """
    doc = fitz.open(path)
    try:
        fields_by_label: dict[str, list[dict]] = {}
        for field in _field_segments(doc):
            fields_by_label.setdefault(field["label"], []).append(field)

        for label, raw_value in values.items():
            value = str(raw_value).strip()
            if not value:
                continue
            for field in fields_by_label.get(label, []):
                page = doc[field["page"]]
                x0, y0, x1, y1 = field["bbox"]
                size = _fit_font_size(page, field, value)
                # Tutup placeholder lama dengan kotak putih lalu tulis nilai di posisi sama.
                page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=None, fill=(1, 1, 1))
                page.insert_text(
                    (x0, y1 - 2),
                    value,
                    fontname=_FILL_FONT,
                    fontsize=size,
                    color=(0, 0, 0),
                )

        return doc.tobytes(deflate=True)
    finally:
        doc.close()


def _resolve_form_path(path: str) -> Path:
    # Tentukan dan validasi bahwa path menunjuk ke template form PDF yang bisa diisi.
    resolved_path = _resolve_document_path(path)
    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Form not found.")
    if (
        resolved_path.suffix.lower() != ".pdf"
        or _document_kind_for_path(resolved_path) != "form"
    ):
        raise HTTPException(status_code=400, detail="Dokumen ini bukan form yang bisa diisi.")
    return resolved_path


def _form_schema_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "form_schemas"


def _relative_form_path(path: Path) -> str:
    return path.resolve().relative_to(_get_data_dir().resolve()).as_posix()


def _coerce_checkbox(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _rect_from_schema(rect: dict[str, Any]) -> fitz.Rect:
    x = float(rect["x"])
    y = float(rect["y"])
    width = float(rect["width"])
    height = float(rect["height"])
    return fitz.Rect(x, y, x + width, y + height)


def _public_field(field: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(field["id"]),
        "label": str(field["label"]),
        "type": str(field["type"]),
        "page": int(field["page"]),
        "rect": {
            "x": float(field["rect"]["x"]),
            "y": float(field["rect"]["y"]),
            "width": float(field["rect"]["width"]),
            "height": float(field["rect"]["height"]),
        },
        "required": bool(field.get("required", False)),
        "section": str(field.get("section") or ""),
        "placeholder": str(field.get("placeholder") or "") or None,
        "font_size": float(field.get("font_size") or 10),
        "align": str(field.get("align") or "left"),
        "line_height": float(field.get("line_height") or 1.08),
        "clear": bool(field.get("clear", True)),
        "clear_padding": max(float(field.get("clear_padding") or 1.0), 0.0),
    }


def _validate_schema_payload(payload: dict[str, Any], schema_path: Path) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail=f"Schema {schema_path.name} tidak valid.")
    path = str(payload.get("path") or "").strip()
    title = str(payload.get("title") or "").strip()
    pages = payload.get("pages")
    fields = payload.get("fields")
    if not path or not title or not isinstance(pages, list) or not isinstance(fields, list):
        raise HTTPException(status_code=500, detail=f"Schema {schema_path.name} tidak lengkap.")

    normalized_pages: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict):
            raise HTTPException(status_code=500, detail=f"Schema {schema_path.name} tidak valid.")
        normalized_pages.append(
            {
                "number": int(page["number"]),
                "width": float(page["width"]),
                "height": float(page["height"]),
            }
        )
    page_numbers = {page["number"] for page in normalized_pages}

    normalized_fields: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for field in fields:
        if not isinstance(field, dict):
            raise HTTPException(status_code=500, detail=f"Schema {schema_path.name} tidak valid.")
        field_id = str(field.get("id") or "").strip()
        field_type = str(field.get("type") or "").strip()
        page_number = int(field.get("page"))
        rect = field.get("rect")
        if (
            not field_id
            or field_id in seen_ids
            or field_type not in FORM_FIELD_TYPES
            or page_number not in page_numbers
            or not isinstance(rect, dict)
        ):
            raise HTTPException(status_code=500, detail=f"Schema {schema_path.name} tidak valid.")
        seen_ids.add(field_id)
        normalized_fields.append(
            {
                "id": field_id,
                "label": str(field.get("label") or field_id),
                "type": field_type,
                "page": page_number,
                "rect": {
                    "x": float(rect["x"]),
                    "y": float(rect["y"]),
                    "width": float(rect["width"]),
                    "height": float(rect["height"]),
                },
                "required": bool(field.get("required", False)),
                "section": str(field.get("section") or ""),
                "placeholder": str(field.get("placeholder") or "") or None,
                "font_size": float(field.get("font_size") or 10),
                "align": str(field.get("align") or "left"),
                "line_height": float(field.get("line_height") or 1.08),
                "clear": bool(field.get("clear", True)),
                "clear_padding": max(float(field.get("clear_padding") or 1.0), 0.0),
            }
        )

    return {
        "path": path,
        "title": title,
        "pages": normalized_pages,
        "fields": normalized_fields,
    }


def _load_form_schema_payloads() -> list[dict[str, Any]]:
    schema_dir = _form_schema_dir()
    if not schema_dir.exists():
        return []

    payloads: list[dict[str, Any]] = []
    for schema_path in sorted(schema_dir.glob("*.json")):
        payload = json.loads(schema_path.read_text(encoding="utf-8"))
        payloads.append(_validate_schema_payload(payload, schema_path))
    return payloads


def _schema_for_resolved_path(path: Path) -> dict[str, Any] | None:
    relative_path = _relative_form_path(path)
    for payload in _load_form_schema_payloads():
        if payload["path"] == relative_path:
            return payload
    return None


def _schema_field_map(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(field["id"]): field for field in schema["fields"]}


def has_schema_form(path: Path) -> bool:
    return _schema_for_resolved_path(path) is not None


def get_form_schema(path: str) -> dict[str, Any]:
    resolved_path = _resolve_form_path(path)
    schema = _schema_for_resolved_path(resolved_path)
    if schema is None:
        raise HTTPException(status_code=404, detail="Schema editor belum tersedia untuk form ini.")
    return {
        "path": schema["path"],
        "title": schema["title"],
        "pages": schema["pages"],
        "fields": [_public_field(field) for field in schema["fields"]],
    }


def _shape_text_fits(
    page: fitz.Page,
    rect: fitz.Rect,
    value: str,
    *,
    font_size: float,
    align: str,
    line_height: float,
) -> fitz.Shape | None:
    shape = page.new_shape()
    spare = shape.insert_textbox(
        rect,
        value,
        fontname=_FILL_FONT,
        fontsize=font_size,
        color=(0, 0, 0),
        align=_ALIGNMENTS.get(align, 0),
        lineheight=line_height,
    )
    return shape if spare >= 0 else None


def _clear_rect_for_field(field: dict[str, Any]) -> fitz.Rect:
    rect = _rect_from_schema(field["rect"])
    padding = max(float(field.get("clear_padding") or 0.0), 0.0)
    if padding <= 0:
        return rect
    return fitz.Rect(
        rect.x0 - padding,
        rect.y0 - padding,
        rect.x1 + padding,
        rect.y1 + padding,
    )


def _write_text_field(page: fitz.Page, field: dict[str, Any], value: str) -> None:
    rect = _rect_from_schema(field["rect"])
    font_size = float(field.get("font_size") or 10)
    line_height = float(field.get("line_height") or 1.08)
    align = str(field.get("align") or "left")

    chosen_shape: fitz.Shape | None = None
    current_size = font_size
    while current_size >= _MIN_FONT_SIZE:
        chosen_shape = _shape_text_fits(
            page,
            rect,
            value,
            font_size=current_size,
            align=align,
            line_height=line_height,
        )
        if chosen_shape is not None:
            break
        current_size -= 0.5

    if field.get("clear", True):
        page.draw_rect(_clear_rect_for_field(field), color=None, fill=(1, 1, 1))

    if chosen_shape is None:
        chosen_shape = page.new_shape()
        chosen_shape.insert_textbox(
            rect,
            value,
            fontname=_FILL_FONT,
            fontsize=_MIN_FONT_SIZE,
            color=(0, 0, 0),
            align=_ALIGNMENTS.get(align, 0),
            lineheight=line_height,
        )
    chosen_shape.commit(overlay=True)


def _write_checkbox(page: fitz.Page, field: dict[str, Any]) -> None:
    rect = _rect_from_schema(field["rect"])
    if field.get("clear", True):
        page.draw_rect(_clear_rect_for_field(field), color=None, fill=(1, 1, 1))

    font_size = max(min(rect.height * 0.95, 16), _MIN_FONT_SIZE)
    text_width = fitz.get_text_length("X", fontname=_FILL_FONT, fontsize=font_size)
    page.insert_text(
        (
            rect.x0 + max((rect.width - text_width) / 2, 0),
            rect.y1 - max((rect.height - font_size) / 2.8, 1),
        ),
        "X",
        fontname=_FILL_FONT,
        fontsize=font_size,
        color=(0, 0, 0),
    )


def _write_signature_image(page: fitz.Page, field: dict[str, Any], image_content: bytes) -> None:
    rect = _rect_from_schema(field["rect"])
    if field.get("clear", True):
        page.draw_rect(_clear_rect_for_field(field), color=None, fill=(1, 1, 1))
    page.insert_image(rect, stream=image_content, keep_proportion=True, overlay=True)


def _validate_schema_values(
    schema: dict[str, Any],
    values: dict[str, str | bool],
    signature_files: dict[str, dict[str, Any]],
) -> None:
    field_map = _schema_field_map(schema)
    unknown_values = sorted(key for key in values if key not in field_map)
    if unknown_values:
        raise HTTPException(
            status_code=422,
            detail=f"Field tidak dikenal: {', '.join(unknown_values)}.",
        )

    invalid_signature_keys = sorted(
        key
        for key in signature_files
        if key not in field_map or field_map[key]["type"] != "signature_image"
    )
    if invalid_signature_keys:
        raise HTTPException(
            status_code=422,
            detail=f"Upload signature tidak valid untuk field: {', '.join(invalid_signature_keys)}.",
        )


def fill_schema_form(
    path: Path,
    values: dict[str, str | bool],
    signature_files: dict[str, dict[str, Any]],
) -> bytes:
    schema = _schema_for_resolved_path(path)
    if schema is None:
        raise HTTPException(status_code=404, detail="Schema editor belum tersedia untuk form ini.")

    for field_id, file_payload in signature_files.items():
        content_type = str(file_payload.get("content_type") or "").lower()
        if content_type not in IMAGE_CONTENT_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f'Field "{field_id}" harus berupa PNG atau JPEG.',
            )
        if not isinstance(file_payload.get("content"), bytes) or not file_payload["content"]:
            raise HTTPException(
                status_code=422,
                detail=f'File untuk field "{field_id}" kosong.',
            )

    _validate_schema_values(schema, values, signature_files)

    doc = fitz.open(path)
    try:
        for field in schema["fields"]:
            page = doc[int(field["page"])]
            field_id = str(field["id"])
            field_type = str(field["type"])
            if field_type == "signature_image":
                upload = signature_files.get(field_id)
                if upload is None:
                    continue
                _write_signature_image(page, field, upload["content"])
                continue
            if field_type == "checkbox":
                if _coerce_checkbox(values.get(field_id)):
                    _write_checkbox(page, field)
                continue
            value = str(values.get(field_id) or "").strip()
            if not value:
                continue
            _write_text_field(page, field, value)
        return doc.tobytes(deflate=True)
    finally:
        doc.close()
