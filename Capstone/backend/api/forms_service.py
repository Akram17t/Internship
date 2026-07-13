from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF
from fastapi import HTTPException

from backend.api.storage import _document_kind_for_path, _resolve_document_path

PDF_MIME = "application/pdf"

# Cocokkan placeholder bracket yang dipakai template form, misalnya "[  ]".
FORM_PLACEHOLDER_PATTERN = re.compile(r"\[[^\[\]]*\]")
# Field segment adalah segmen teks yang seluruh isinya hanya satu bracket.
# Placeholder inline seperti "Nama: [ ]" atau header dilewati agar form tetap singkat.
FORM_FIELD_CELL_PATTERN = re.compile(r"^\[[^\[\]]*\]$")

# Helvetica bawaan PDF dipakai untuk menulis nilai agar tidak perlu embed font.
_FILL_FONT = "helv"
_MIN_FONT_SIZE = 6.0


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
