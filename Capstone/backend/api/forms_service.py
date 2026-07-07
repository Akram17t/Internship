from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException

from backend.api.storage import _document_kind_for_path, _resolve_document_path

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Cocokkan placeholder bracket yang dipakai template form, misalnya "[  ]".
FORM_PLACEHOLDER_PATTERN = re.compile(r"\[[^\[\]]*\]")
# Cell "field" adalah cell yang seluruh isinya hanya satu bracket.
# Placeholder inline seperti "Nama: [ ]" atau header dilewati agar form tetap singkat.
FORM_FIELD_CELL_PATTERN = re.compile(r"^\[[^\[\]]*\]$")


def _field_label(worksheet, cell) -> str | None:
    """Cari label teks yang bersih untuk satu cell placeholder.

    Pencarian dimulai dari isi bracket, lalu teks terdekat di kiri, lalu di atas.
    Jika tidak ada label yang layak, kembalikan None agar cell itu dilewati.
    """
    inside = str(cell.value).strip()[1:-1].strip()
    if inside:
        return inside
    for column in range(cell.column - 1, 0, -1):
        left = worksheet.cell(row=cell.row, column=column).value
        if isinstance(left, str):
            candidate = left.strip().rstrip(":").strip()
            if candidate and not FORM_PLACEHOLDER_PATTERN.search(candidate):
                return candidate
    if cell.row > 1:
        above = worksheet.cell(row=cell.row - 1, column=cell.column).value
        if isinstance(above, str):
            candidate = above.strip().rstrip(":").strip()
            if candidate and not FORM_PLACEHOLDER_PATTERN.search(candidate):
                return candidate
    return None


def _scan_form_fields(path: Path) -> list[dict[str, str]]:
    """Ambil field info utama dari blok atas tiap sheet.

    Hanya blok baris placeholder pertama yang diambil. Bagian lanjutan seperti
    tabel biaya, teks bebas, atau blok tanda tangan dilewati agar form tetap singkat.
    """
    from openpyxl import load_workbook

    workbook = load_workbook(path)
    fields: list[dict[str, str]] = []
    for index, worksheet in enumerate(workbook.worksheets):
        started = False
        for row in worksheet.iter_rows():
            row_fields: list[dict[str, str]] = []
            for cell in row:
                if not (isinstance(cell.value, str) and FORM_FIELD_CELL_PATTERN.match(cell.value.strip())):
                    continue
                label = _field_label(worksheet, cell)
                if label:
                    row_fields.append(
                        {"key": f"{index}:{cell.coordinate}", "label": label}
                    )
            if row_fields:
                started = True
                fields.extend(row_fields)
            elif started:
                break  # end of the top info block for this sheet
    return fields


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


def _fill_form_placeholders(path: Path, values: dict[str, str]) -> bytes:
    """Isi semua cell placeholder yang labelnya punya nilai dari user.

    Nilai dipetakan berdasarkan label, jadi satu input bisa mengisi semua cell
    dengan label yang sama. Nilai kosong dibiarkan apa adanya.
    """
    from openpyxl import load_workbook

    coords_by_label: dict[str, list[str]] = {}
    for field in _scan_form_fields(path):
        coords_by_label.setdefault(field["label"], []).append(field["key"])

    workbook = load_workbook(path)
    for label, raw_value in values.items():
        value = str(raw_value).strip()
        if not value:
            continue
        for coord_key in coords_by_label.get(label, []):
            try:
                index_str, coordinate = coord_key.split(":", 1)
                cell = workbook.worksheets[int(index_str)][coordinate]
            except (ValueError, IndexError, KeyError):
                continue
            if isinstance(cell.value, str) and FORM_PLACEHOLDER_PATTERN.search(cell.value):
                cell.value = FORM_PLACEHOLDER_PATTERN.sub(lambda _match: value, cell.value, count=1)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _resolve_form_path(path: str) -> Path:
    # Tentukan dan validasi bahwa path menunjuk ke template form yang bisa diisi.
    resolved_path = _resolve_document_path(path)
    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Form not found.")
    if (
        resolved_path.suffix.lower() != ".xlsx"
        or _document_kind_for_path(resolved_path) != "form"
    ):
        raise HTTPException(status_code=400, detail="Dokumen ini bukan form yang bisa diisi.")
    return resolved_path
