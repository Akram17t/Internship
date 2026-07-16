from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz

from backend.api.forms_service import _form_schema_dir, _relative_form_path, _validate_schema_payload
from backend.settings import get_env, get_float_env, get_int_env

_MAX_TEXT_LINES = 80
_MAX_CANDIDATES = 120
_MAX_TEXT_CHARS = 90
_MAX_SCHEMA_OUTPUT_TOKENS = 4096
_GRID_TOLERANCE = 2.0

logger = logging.getLogger("uvicorn.error")


def _schema_form_path(path: Path) -> str:
    try:
        return _relative_form_path(path)
    except ValueError:
        return path.name


@dataclass(frozen=True)
class FormSchemaGenerationResult:
    generated: bool
    schema_path: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class FormSchemaDeletionResult:
    deleted: bool
    schema_path: str | None = None


def _round_rect(rect: fitz.Rect) -> dict[str, float]:
    return {
        "x": round(float(rect.x0), 2),
        "y": round(float(rect.y0), 2),
        "width": round(float(rect.width), 2),
        "height": round(float(rect.height), 2),
    }


def _line_text(line: dict[str, Any]) -> str:
    return "".join(str(span.get("text") or "") for span in line.get("spans", [])).strip()


def _page_lines(page: fitz.Page, page_number: int) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            text = _line_text(line)
            if not text:
                continue
            rect = fitz.Rect(line["bbox"])
            lines.append(
                {
                    "page": page_number,
                    "text": text,
                    "rect": _round_rect(rect),
                    "font_size": round(
                        max(
                            (
                                float(span.get("size") or 0)
                                for span in line.get("spans", [])
                            ),
                            default=10.0,
                        ),
                        2,
                    ),
                }
            )
    return sorted(lines, key=lambda item: (item["page"], item["rect"]["y"], item["rect"]["x"]))


def _nearest_label(region: fitz.Rect, lines: list[dict[str, Any]]) -> str:
    center_y = (region.y0 + region.y1) / 2
    best_left: tuple[float, str] | None = None
    best_above: tuple[float, str] | None = None

    for line in lines:
        rect = line["rect"]
        line_rect = fitz.Rect(
            rect["x"],
            rect["y"],
            rect["x"] + rect["width"],
            rect["y"] + rect["height"],
        )
        text = str(line["text"]).strip().rstrip(":").strip()
        if not text or "[" in text or "]" in text:
            continue
        if line_rect.y0 <= center_y <= line_rect.y1 and line_rect.x1 <= region.x0 + 3:
            distance = region.x0 - line_rect.x1
            if best_left is None or distance < best_left[0]:
                best_left = (distance, text)
        if line_rect.y1 <= region.y0 + 3 and not (line_rect.x1 < region.x0 or line_rect.x0 > region.x1):
            distance = region.y0 - line_rect.y1
            if best_above is None or distance < best_above[0]:
                best_above = (distance, text)

    return (best_left or best_above or (0, ""))[1]


def _widget_candidates(page: fitz.Page, page_number: int, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    widgets = page.widgets() or []
    for widget in widgets:
        rect = fitz.Rect(widget.rect)
        name = str(getattr(widget, "field_name", "") or "").strip()
        label = str(getattr(widget, "field_label", "") or "").strip()
        candidates.append(
            {
                "kind": "pdf_widget",
                "page": page_number,
                "name": name,
                "label_hint": label or name or _nearest_label(rect, lines),
                "widget_type": str(getattr(widget, "field_type_string", "") or getattr(widget, "field_type", "")),
                "rect": _round_rect(rect),
            }
        )
    return candidates


def _grid_line(
    page_number: int,
    orientation: str,
    *,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> dict[str, Any]:
    if orientation == "h":
        return {
            "page": page_number,
            "orientation": "h",
            "x0": round(min(x0, x1), 2),
            "x1": round(max(x0, x1), 2),
            "y": round((y0 + y1) / 2, 2),
        }
    return {
        "page": page_number,
        "orientation": "v",
        "x": round((x0 + x1) / 2, 2),
        "y0": round(min(y0, y1), 2),
        "y1": round(max(y0, y1), 2),
    }


def _drawing_geometry(
    page: fitz.Page,
    page_number: int,
    lines: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    grid_lines: list[dict[str, Any]] = []
    try:
        drawings = page.get_drawings()
    except Exception:
        return candidates, grid_lines

    for drawing in drawings:
        for item in drawing.get("items", []):
            if not item:
                continue
            kind = item[0]
            rect: fitz.Rect | None = None
            candidate_kind = ""
            if kind == "re" and len(item) > 1:
                rect = fitz.Rect(item[1])
                grid_lines.extend(
                    [
                        _grid_line(page_number, "h", x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y0),
                        _grid_line(page_number, "h", x0=rect.x0, y0=rect.y1, x1=rect.x1, y1=rect.y1),
                        _grid_line(page_number, "v", x0=rect.x0, y0=rect.y0, x1=rect.x0, y1=rect.y1),
                        _grid_line(page_number, "v", x0=rect.x1, y0=rect.y0, x1=rect.x1, y1=rect.y1),
                    ]
                )
                if 7 <= rect.width <= 24 and 7 <= rect.height <= 24:
                    candidate_kind = "checkbox_box"
                elif rect.width >= 30 and rect.height >= 8:
                    candidate_kind = "drawn_rect"
            elif kind == "l" and len(item) > 2:
                p1, p2 = item[1], item[2]
                if abs(float(p1.y) - float(p2.y)) <= 1 and abs(float(p2.x) - float(p1.x)) >= 30:
                    y = float(p1.y)
                    grid_lines.append(
                        _grid_line(page_number, "h", x0=float(p1.x), y0=y, x1=float(p2.x), y1=y)
                    )
                    rect = fitz.Rect(min(p1.x, p2.x), y - 8, max(p1.x, p2.x), y + 4)
                    candidate_kind = "underline"
                elif abs(float(p1.x) - float(p2.x)) <= 1 and abs(float(p2.y) - float(p1.y)) >= 8:
                    x = float(p1.x)
                    grid_lines.append(
                        _grid_line(page_number, "v", x0=x, y0=float(p1.y), x1=x, y1=float(p2.y))
                    )
            if rect is None or not candidate_kind:
                continue
            candidates.append(
                {
                    "kind": candidate_kind,
                    "page": page_number,
                    "label_hint": _nearest_label(rect, lines),
                    "rect": _round_rect(rect),
                }
            )
    return candidates, _dedupe_grid_lines(grid_lines)


def _dedupe_grid_lines(grid_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for line in grid_lines:
        if line["orientation"] == "h":
            key = (
                line["page"],
                "h",
                round(float(line["x0"]) / _GRID_TOLERANCE),
                round(float(line["x1"]) / _GRID_TOLERANCE),
                round(float(line["y"]) / _GRID_TOLERANCE),
            )
        else:
            key = (
                line["page"],
                "v",
                round(float(line["x"]) / _GRID_TOLERANCE),
                round(float(line["y0"]) / _GRID_TOLERANCE),
                round(float(line["y1"]) / _GRID_TOLERANCE),
            )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(line)
    return deduped


def _placeholder_candidates(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for line in lines:
        text = str(line["text"])
        if "[" not in text or "]" not in text:
            continue
        rect = line["rect"]
        line_rect = fitz.Rect(
            rect["x"],
            rect["y"],
            rect["x"] + rect["width"],
            rect["y"] + rect["height"],
        )
        label = re.sub(r"\[[^\[\]]*\]", "", text).strip(" :-")
        if not label:
            label = _nearest_label(line_rect, [other for other in lines if other["page"] == line["page"]])
        candidates.append(
            {
                "kind": "bracket_placeholder",
                "page": int(line["page"]),
                "label_hint": label,
                "text": text,
                "rect": line["rect"],
            }
        )
    return candidates


def parse_pdf_for_schema(path: Path) -> dict[str, Any]:
    with fitz.open(path) as doc:
        pages = [
            {
                "number": page_number,
                "width": round(float(page.rect.width), 2),
                "height": round(float(page.rect.height), 2),
            }
            for page_number, page in enumerate(doc)
        ]

        all_lines: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        grid_lines: list[dict[str, Any]] = []
        for page_number, page in enumerate(doc):
            lines = _page_lines(page, page_number)
            all_lines.extend(lines)
            candidates.extend(_widget_candidates(page, page_number, lines))
            drawing_candidates, drawing_grid_lines = _drawing_geometry(page, page_number, lines)
            candidates.extend(drawing_candidates)
            grid_lines.extend(drawing_grid_lines)

        candidates.extend(_placeholder_candidates(all_lines))

    return {
        "filename": path.name,
        "pages": pages,
        "text_lines": all_lines,
        "field_candidates": candidates,
        "grid_lines": _dedupe_grid_lines(grid_lines),
    }


def _short_text(value: object, limit: int = _MAX_TEXT_CHARS) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _compact_rect(rect: dict[str, Any]) -> list[float]:
    return [
        round(float(rect["x"]), 1),
        round(float(rect["y"]), 1),
        round(float(rect["width"]), 1),
        round(float(rect["height"]), 1),
    ]


def _compact_pdf_parse(path: Path, parsed_pdf: dict[str, Any]) -> dict[str, Any]:
    pages = [
        [
            int(page["number"]),
            round(float(page["width"]), 1),
            round(float(page["height"]), 1),
        ]
        for page in parsed_pdf["pages"]
    ]
    text_lines = [
        {
            "p": int(line["page"]),
            "x": round(float(line["rect"]["x"]), 1),
            "y": round(float(line["rect"]["y"]), 1),
            "t": _short_text(line["text"]),
        }
        for line in parsed_pdf["text_lines"][:_MAX_TEXT_LINES]
    ]
    candidates = [
        {
            "p": int(candidate["page"]),
            "k": candidate["kind"],
            "label": _short_text(candidate.get("label_hint") or candidate.get("name") or candidate.get("text")),
            "r": _compact_rect(candidate["rect"]),
        }
        for candidate in parsed_pdf["field_candidates"][:_MAX_CANDIDATES]
    ]
    candidates.sort(key=lambda item: (0 if item["label"] else 1, item["p"], item["r"][1], item["r"][0]))
    for index, candidate in enumerate(candidates):
        candidate["i"] = index

    return {
        "file": path.name,
        "path": _schema_form_path(path),
        "pages": pages,
        "texts": text_lines,
        "candidates": candidates,
    }


def _schema_file_name(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"(?i)^form\s*-\s*", "", stem)
    stem = re.sub(r"(?i)\(template\)", "", stem)
    stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^a-zA-Z0-9]+", "_", stem).strip("_").lower()
    return f"{stem or 'form_schema'}.json"


def delete_schema_for_form_pdf(path: Path) -> FormSchemaDeletionResult:
    schema_dir = _form_schema_dir()
    schema_path = schema_dir / _schema_file_name(path)
    if not schema_path.exists():
        return FormSchemaDeletionResult(deleted=False)

    schema_path.unlink()
    logger.info("[form-schema] Schema form ikut dihapus file=%s", schema_path)
    return FormSchemaDeletionResult(
        deleted=True,
        schema_path=schema_path.relative_to(schema_dir.parent).as_posix(),
    )


def _schema_prompt(path: Path, parsed_pdf: dict[str, Any]) -> str:
    heuristic_schema = _heuristic_schema_payload(path, parsed_pdf)
    candidates = [
        {
            "candidate_id": index,
            "id": field["id"],
            "label": field["label"],
            "type": field["type"],
            "page": field["page"],
            "section": field.get("section") or "",
            "placeholder": field.get("placeholder") or "",
            "layout": field.get("layout") or {},
        }
        for index, field in enumerate(heuristic_schema["fields"])
    ]
    return _schema_prompt_for_candidates(path, heuristic_schema["title"], candidates, "full_document")


def _schema_prompt_for_candidates(
    path: Path,
    title: str,
    candidates: list[dict[str, Any]],
    region_label: str,
) -> str:
    context = {
        "file": path.name,
        "path": _schema_form_path(path),
        "title": title,
        "region": region_label,
        "candidates": candidates,
    }
    return (
        "Return only valid JSON. No markdown. No explanation.\n"
        "You are refining already-detected PDF form field candidates.\n"
        "Return this exact shape: {\"title\":\"...\",\"fields\":[...]}\n"
        "Each field must include candidate_id and may include id,label,type,required,section,placeholder,font_size,clear,layout.\n"
        "Types: text,textarea,date,checkbox,signature_image. Use snake_case ids.\n"
        "Do not output rect, r, x, y, width, height, page, or coordinates. Coordinates are owned by backend.\n"
        "Keep all real fillable fields. Drop only obvious headers/non-inputs.\n"
        f"Required path: {_schema_form_path(path)}\n"
        "Candidate JSON:\n"
        f"{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("Model tidak mengembalikan JSON object.")
    decoder = json.JSONDecoder()
    payload, _end = decoder.raw_decode(cleaned[start:])
    if not isinstance(payload, dict):
        raise ValueError("Model JSON bukan object.")
    return payload


def _schema_pages(parsed_pdf: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "number": int(page["number"]),
            "width": float(page["width"]),
            "height": float(page["height"]),
        }
        for page in parsed_pdf["pages"]
    ]


def _number_list(value: str) -> list[float] | None:
    numbers = re.findall(r"-?\d+(?:\.\d+)?", value)
    if len(numbers) != 4:
        return None
    return [float(number) for number in numbers]


def _candidate_rect_lookup(path: Path, parsed_pdf: dict[str, Any]) -> dict[int, list[float]]:
    return {
        int(candidate["i"]): list(candidate["r"])
        for candidate in _compact_pdf_parse(path, parsed_pdf)["candidates"]
        if "i" in candidate and isinstance(candidate.get("r"), list)
    }


def _rect_payload(
    rect: object,
    *,
    candidate_rects: dict[int, list[float]] | None = None,
) -> dict[str, float]:
    if isinstance(rect, (int, float)):
        candidate = (candidate_rects or {}).get(int(rect))
        if candidate:
            return _rect_payload(candidate)
        raise ValueError(f"Candidate rect index tidak ditemukan: {rect}")
    if isinstance(rect, str):
        stripped = rect.strip()
        if stripped.isdigit() and candidate_rects:
            return _rect_payload(int(stripped), candidate_rects=candidate_rects)
        try:
            parsed_rect = json.loads(stripped)
        except json.JSONDecodeError:
            parsed_numbers = _number_list(stripped)
            if parsed_numbers is None:
                raise ValueError(f"Rect string model tidak valid: {stripped}")
            parsed_rect = parsed_numbers
        return _rect_payload(parsed_rect, candidate_rects=candidate_rects)
    if isinstance(rect, list) and len(rect) == 4:
        return {
            "x": float(rect[0]),
            "y": float(rect[1]),
            "width": float(rect[2]),
            "height": float(rect[3]),
        }
    if isinstance(rect, dict):
        if "i" in rect:
            return _rect_payload(rect["i"], candidate_rects=candidate_rects)
        if "index" in rect:
            return _rect_payload(rect["index"], candidate_rects=candidate_rects)
        if {"x", "y", "w", "h"}.issubset(rect):
            return {
                "x": float(rect["x"]),
                "y": float(rect["y"]),
                "width": float(rect["w"]),
                "height": float(rect["h"]),
            }
        if {"x0", "y0", "x1", "y1"}.issubset(rect):
            x0 = float(rect["x0"])
            y0 = float(rect["y0"])
            x1 = float(rect["x1"])
            y1 = float(rect["y1"])
            return {
                "x": x0,
                "y": y0,
                "width": max(x1 - x0, 0.1),
                "height": max(y1 - y0, 0.1),
            }
        if {"left", "top", "right", "bottom"}.issubset(rect):
            left = float(rect["left"])
            top = float(rect["top"])
            right = float(rect["right"])
            bottom = float(rect["bottom"])
            return {
                "x": left,
                "y": top,
                "width": max(right - left, 0.1),
                "height": max(bottom - top, 0.1),
            }
        return {
            "x": float(rect["x"]),
            "y": float(rect["y"]),
            "width": float(rect["width"]),
            "height": float(rect["height"]),
        }
    raise ValueError("Rect field model tidak valid.")


def _slug_field_id(label: str, fallback: str, seen_ids: set[str]) -> str:
    base = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-zA-Z0-9]+", "_", base).strip("_").lower() or fallback
    field_id = base
    suffix = 2
    while field_id in seen_ids:
        field_id = f"{base}_{suffix}"
        suffix += 1
    seen_ids.add(field_id)
    return field_id


def _infer_field_type(label: str, rect: dict[str, float], kind: str = "") -> str:
    normalized = label.lower()
    if "checkbox" in kind:
        return "checkbox"
    if any(token in normalized for token in ("tanda tangan", "signature", "ttd")):
        return "signature_image"
    if any(token in normalized for token in ("tanggal", "date")):
        return "date"
    if rect["height"] >= 28 or any(
        token in normalized
        for token in ("keterangan", "deskripsi", "kronologi", "catatan", "remark", "notes")
    ):
        return "textarea"
    return "text"


def _line_rect(line: dict[str, Any]) -> dict[str, float]:
    rect = line["rect"]
    return {
        "x": float(rect["x"]),
        "y": float(rect["y"]),
        "width": float(rect["width"]),
        "height": float(rect["height"]),
    }


def _clean_heuristic_label(label: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", label).strip(" :-") or label.strip()


def _expand_placeholder_rect(
    line: dict[str, Any],
    lines: list[dict[str, Any]],
    page_width: float,
) -> dict[str, float]:
    rect = _line_rect(line)
    text = str(line["text"]).strip()
    if "[" in text and not re.fullmatch(r"\[\s*\]", text):
        return rect

    center_y = rect["y"] + rect["height"] / 2
    right_boundary = page_width - 55
    for other in lines:
        if other is line or int(other["page"]) != int(line["page"]):
            continue
        other_rect = _line_rect(other)
        other_center_y = other_rect["y"] + other_rect["height"] / 2
        if abs(other_center_y - center_y) > max(rect["height"], other_rect["height"]):
            continue
        if other_rect["x"] <= rect["x"] + 1:
            continue
        right_boundary = min(right_boundary, other_rect["x"] - 4)

    return {
        "x": rect["x"],
        "y": rect["y"],
        "width": max(right_boundary - rect["x"], rect["width"]),
        "height": rect["height"],
    }


def _page_size_lookup(parsed_pdf: dict[str, Any]) -> dict[int, dict[str, float]]:
    return {
        int(page["number"]): {
            "width": float(page["width"]),
            "height": float(page["height"]),
        }
        for page in parsed_pdf["pages"]
    }


def _cluster_numbers(values: list[float], tolerance: float = _GRID_TOLERANCE) -> list[float]:
    if not values:
        return []
    clusters: list[list[float]] = []
    for value in sorted(values):
        if not clusters or abs(value - clusters[-1][-1]) > tolerance:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return [round(sum(cluster) / len(cluster), 2) for cluster in clusters]


def _rect_from_bounds(x0: float, y0: float, x1: float, y1: float, inset: float = 1.5) -> dict[str, float]:
    return {
        "x": round(x0 + inset, 2),
        "y": round(y0 + inset, 2),
        "width": round(max(x1 - x0 - inset * 2, 1.0), 2),
        "height": round(max(y1 - y0 - inset * 2, 1.0), 2),
    }


def _line_center(line: dict[str, Any]) -> tuple[float, float]:
    rect = _line_rect(line)
    return (rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2)


def _lines_by_page(lines: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for line in lines:
        grouped.setdefault(int(line["page"]), []).append(line)
    return grouped


def _layout(
    kind: str,
    *,
    group_id: str = "",
    group_label: str = "",
    row_label: str = "",
    column_label: str = "",
    choice_group: str = "",
) -> dict[str, str]:
    payload = {
        "kind": kind,
        "group_id": group_id,
        "group_label": group_label,
        "row_label": row_label,
        "column_label": column_label,
        "choice_group": choice_group,
    }
    return {key: value for key, value in payload.items() if value}


def _field_payload(
    label: str,
    field_type: str,
    page: int,
    rect: dict[str, float],
    seen_ids: set[str],
    *,
    field_id_label: str | None = None,
    section: str = "",
    placeholder: str | None = None,
    font_size: float = 10,
    clear: bool = True,
    align: str = "left",
    line_height: float = 1.08,
    clear_padding: float = 1.0,
    layout: dict[str, str] | None = None,
) -> dict[str, Any]:
    field = {
        "id": _slug_field_id(field_id_label or label, f"field_{len(seen_ids) + 1}", seen_ids),
        "label": label,
        "type": field_type,
        "page": page,
        "rect": rect,
        "required": False,
        "section": section,
        "placeholder": placeholder if placeholder is not None else (label if field_type != "checkbox" else None),
        "font_size": font_size,
        "align": align,
        "line_height": line_height,
        "clear": clear,
        "clear_padding": clear_padding,
    }
    if layout:
        field["layout"] = layout
    return field


def _field_key(page: int, label: str, rect: dict[str, float] | None = None) -> tuple[Any, ...]:
    if rect is None:
        return (page, _clean_heuristic_label(label).lower())
    return (
        page,
        _clean_heuristic_label(label).lower(),
        round(float(rect["x"]) / 4),
        round(float(rect["y"]) / 4),
    )


def _page_grid(parsed_pdf: dict[str, Any], page: int) -> dict[str, list[float]]:
    grid_lines = [line for line in parsed_pdf.get("grid_lines", []) if int(line["page"]) == page]
    h_lines = [line for line in grid_lines if line.get("orientation") == "h"]
    v_lines = [line for line in grid_lines if line.get("orientation") == "v"]
    if len(h_lines) < 2 or len(v_lines) < 2:
        return {"x": [], "y": []}
    x_positions = _cluster_numbers([float(line["x"]) for line in v_lines])
    y_positions = _cluster_numbers([float(line["y"]) for line in h_lines])
    if len(x_positions) < 2 or len(y_positions) < 2:
        return {"x": [], "y": []}
    return {"x": x_positions, "y": y_positions}


def _cell_text(
    lines: list[dict[str, Any]],
    page: int,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> str:
    parts: list[tuple[float, float, str]] = []
    for line in lines:
        if int(line["page"]) != page:
            continue
        cx, cy = _line_center(line)
        if x0 - 1 <= cx <= x1 + 1 and y0 - 1 <= cy <= y1 + 1:
            parts.append((cy, cx, str(line["text"]).strip()))
    parts.sort()
    return " ".join(part for _cy, _cx, part in parts if part).strip()


def _grid_rows(parsed_pdf: dict[str, Any], page: int) -> list[dict[str, Any]]:
    grid = _page_grid(parsed_pdf, page)
    xs = grid["x"]
    ys = grid["y"]
    lines = parsed_pdf["text_lines"]
    rows: list[dict[str, Any]] = []
    if len(xs) < 2 or len(ys) < 2:
        return rows
    for row_index in range(len(ys) - 1):
        y0, y1 = ys[row_index], ys[row_index + 1]
        if y1 - y0 < 5:
            continue
        cells: list[dict[str, Any]] = []
        for col_index in range(len(xs) - 1):
            x0, x1 = xs[col_index], xs[col_index + 1]
            if x1 - x0 < 5:
                continue
            cells.append(
                {
                    "index": col_index,
                    "x0": x0,
                    "x1": x1,
                    "y0": y0,
                    "y1": y1,
                    "text": _cell_text(lines, page, x0, y0, x1, y1),
                }
            )
        rows.append({"index": row_index, "page": page, "y0": y0, "y1": y1, "cells": cells})
    return rows


def _cell_at(row: dict[str, Any], col_index: int) -> dict[str, Any] | None:
    for cell in row["cells"]:
        if int(cell["index"]) == col_index:
            return cell
    return None


def _section_label_before(lines: list[dict[str, Any]], page: int, y: float) -> str:
    candidates = [
        line
        for line in lines
        if int(line["page"]) == page
        and _line_rect(line)["y"] < y
        and _line_rect(line)["y"] >= y - 45
        and str(line["text"]).strip()
    ]
    if not candidates:
        return ""
    candidates.sort(key=lambda line: _line_rect(line)["y"], reverse=True)
    label = _clean_heuristic_label(str(candidates[0]["text"]))
    return label[:80]


def _normalized_cell_text(cell: dict[str, Any] | None) -> str:
    return re.sub(r"\s+", " ", str((cell or {}).get("text") or "")).strip()


def _is_table_header_text(text: str) -> bool:
    normalized = text.lower()
    return normalized in {
        "no",
        "item",
        "done",
        "tanggal",
        "pernyataan",
        "sangat tidak setuju",
        "tidak setuju",
        "setuju",
        "sangat setuju",
    }


def _inline_placeholder_fields(
    line: dict[str, Any],
    page_size: dict[str, float],
    seen_ids: set[str],
    seen_labels: set[tuple[Any, ...]],
) -> list[dict[str, Any]]:
    text = str(line["text"])
    labels: list[tuple[str, int, int]] = []
    for match in re.finditer(r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s/.-]{1,35}):\s*\[", text):
        label = _clean_heuristic_label(match.group(1))
        if label:
            labels.append((label, match.start(), match.end() - 1))
    if len(labels) <= 1:
        return []

    rect = _line_rect(line)
    char_width = rect["width"] / max(len(text), 1)
    fields: list[dict[str, Any]] = []
    for index, (label, _label_start, bracket_index) in enumerate(labels):
        next_label_start = labels[index + 1][1] if index + 1 < len(labels) else len(text)
        x0 = rect["x"] + bracket_index * char_width
        x1 = rect["x"] + max(next_label_start * char_width - 4, bracket_index * char_width + 18)
        if index == len(labels) - 1:
            x1 = min(max(x1, x0 + 40), page_size["width"] - 55)
        field_rect = {
            "x": round(x0, 2),
            "y": rect["y"],
            "width": round(max(x1 - x0, 18), 2),
            "height": rect["height"],
        }
        key = _field_key(int(line["page"]), label, field_rect)
        if key in seen_labels:
            continue
        seen_labels.add(key)
        fields.append(
            _field_payload(
                label,
                _infer_field_type(label, field_rect, "bracket_placeholder"),
                int(line["page"]),
                field_rect,
                seen_ids,
                layout=_layout("inline_placeholder"),
            )
        )
    return fields


def _section_textarea_labels() -> tuple[str, ...]:
    return (
        "Deskripsi Insiden",
        "Dampak Bisnis",
        "Pihak yang Terdampak",
        "Kronologi Insiden",
        "Lampiran / Bukti",
        "Alasan / Penjelasan",
        "Hal yang perlu dipertahankan",
    )


def _is_section_textarea_label(label: str) -> bool:
    normalized = label.lower()
    if any(section.lower() in normalized for section in _section_textarea_labels()):
        return True
    if "?" in normalized and len(normalized) > 20:
        return True
    return bool(re.match(r"^\d+\.\s+.+", normalized)) and any(
        token in normalized
        for token in (
            "alasan",
            "penjelasan",
            "deskripsi",
            "hal ",
            "dapat",
            "dipertahankan",
            "ditingkatkan",
            "keterangan",
        )
    )


def _next_section_y(lines: list[dict[str, Any]], page: int, current_y: float) -> float | None:
    section_ys = [
        _line_rect(line)["y"]
        for line in lines
        if int(line["page"]) == page
        and _line_rect(line)["y"] > current_y + 4
        and _is_section_textarea_label(str(line["text"]))
    ]
    return min(section_ys) if section_ys else None


def _table_fields(parsed_pdf: dict[str, Any], seen_ids: set[str], seen_labels: set[tuple[Any, ...]]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    pages = [int(page["number"]) for page in parsed_pdf["pages"]]
    for page in pages:
        rows = _grid_rows(parsed_pdf, page)
        if not rows:
            continue
        consumed_rows: set[int] = set()
        special_table_found = False
        for row_index, row in enumerate(rows):
            header_texts = [_normalized_cell_text(cell) for cell in row["cells"]]
            lowered = [text.lower() for text in header_texts]
            if "pernyataan" in lowered and any("setuju" in text for text in lowered):
                special_table_found = True
                first_col = lowered.index("pernyataan")
                option_cols = [
                    cell["index"]
                    for cell in row["cells"]
                    if cell["index"] != first_col and "setuju" in _normalized_cell_text(cell).lower()
                ]
                group_label = _section_label_before(parsed_pdf["text_lines"], page, row["y0"]) or "Kuesioner"
                group_id = _slug_base(group_label or f"matrix_{page}_{row_index}")
                for data_row in rows[row_index + 1 :]:
                    if data_row["index"] in consumed_rows:
                        continue
                    row_label = _normalized_cell_text(_cell_at(data_row, first_col))
                    if not row_label or _is_table_header_text(row_label):
                        break
                    consumed_rows.add(int(data_row["index"]))
                    choice_group = f"{group_id}_{_slug_base(row_label) or data_row['index']}"
                    for col_index in option_cols:
                        option_cell = _cell_at(row, col_index)
                        value_cell = _cell_at(data_row, col_index)
                        if option_cell is None or value_cell is None:
                            continue
                        option_label = _normalized_cell_text(option_cell)
                        rect = _rect_from_bounds(
                            float(value_cell["x0"]),
                            float(value_cell["y0"]),
                            float(value_cell["x1"]),
                            float(value_cell["y1"]),
                            inset=2.0,
                        )
                        label = f"{row_label} - {option_label}"
                        key = _field_key(page, label, rect)
                        if key in seen_labels:
                            continue
                        seen_labels.add(key)
                        fields.append(
                            _field_payload(
                                label,
                                "checkbox",
                                page,
                                rect,
                                seen_ids,
                                field_id_label=f"{row_label}_{option_label}",
                                section=group_label,
                                font_size=10,
                                align="center",
                                layout=_layout(
                                    "choice_matrix",
                                    group_id=group_id,
                                    group_label=group_label,
                                    row_label=row_label,
                                    column_label=option_label,
                                    choice_group=choice_group,
                                ),
                            )
                        )
                continue

            if "item" in lowered and "done" in lowered and "tanggal" in lowered:
                special_table_found = True
                item_col = lowered.index("item")
                done_col = lowered.index("done")
                date_col = lowered.index("tanggal")
                group_label = _section_label_before(parsed_pdf["text_lines"], page, row["y0"]) or "Checklist"
                group_id = _slug_base(group_label or f"checklist_{page}_{row_index}")
                for data_row in rows[row_index + 1 :]:
                    row_item = _normalized_cell_text(_cell_at(data_row, item_col))
                    if not row_item:
                        continue
                    if _is_table_header_text(row_item) or row_item.lower() in {"hr", "ga - accessories", "ga - access card"}:
                        break
                    consumed_rows.add(int(data_row["index"]))
                    for col_index, column_label, field_type in (
                        (done_col, "Done", "checkbox"),
                        (date_col, "Tanggal", "date"),
                    ):
                        value_cell = _cell_at(data_row, col_index)
                        if value_cell is None:
                            continue
                        rect = _rect_from_bounds(
                            float(value_cell["x0"]),
                            float(value_cell["y0"]),
                            float(value_cell["x1"]),
                            float(value_cell["y1"]),
                            inset=2.0,
                        )
                        label = f"{row_item} - {column_label}"
                        key = _field_key(page, label, rect)
                        if key in seen_labels:
                            continue
                        seen_labels.add(key)
                        fields.append(
                            _field_payload(
                                label,
                                field_type,
                                page,
                                rect,
                                seen_ids,
                                field_id_label=f"{row_item}_{column_label}",
                                section=group_label,
                                font_size=9,
                                align="center" if field_type == "checkbox" else "left",
                                layout=_layout(
                                    "table_cell",
                                    group_id=group_id,
                                    group_label=group_label,
                                    row_label=row_item,
                                    column_label=column_label,
                                ),
                            )
                        )
                continue

        if special_table_found:
            continue

        for row_index, row in enumerate(rows):
            if row_index in consumed_rows:
                continue
            header_cells = row["cells"]
            header_texts = [_normalized_cell_text(cell) for cell in header_cells]
            if len([text for text in header_texts if text]) < 3:
                continue
            if not any(text.lower() in {"no", "nama karyawan", "departemen", "jabatan"} for text in header_texts):
                continue
            group_label = _section_label_before(parsed_pdf["text_lines"], page, row["y0"]) or "Tabel"
            group_id = _slug_base(group_label or f"table_{page}_{row_index}")
            input_columns = [
                (cell["index"], _normalized_cell_text(cell))
                for cell in header_cells
                if _normalized_cell_text(cell) and _normalized_cell_text(cell).lower() not in {"no"}
            ]
            for data_row in rows[row_index + 1 :]:
                first_text = _normalized_cell_text(_cell_at(data_row, 0))
                if not first_text:
                    continue
                if not re.fullmatch(r"\d+", first_text):
                    break
                row_label = f"Baris {first_text}"
                for col_index, column_label in input_columns:
                    value_cell = _cell_at(data_row, col_index)
                    if value_cell is None or _normalized_cell_text(value_cell):
                        continue
                    rect = _rect_from_bounds(
                        float(value_cell["x0"]),
                        float(value_cell["y0"]),
                        float(value_cell["x1"]),
                        float(value_cell["y1"]),
                        inset=1.0,
                    )
                    field_type = "date" if "tanggal" in column_label.lower() else "text"
                    label = f"{row_label} - {column_label}"
                    key = _field_key(page, label, rect)
                    if key in seen_labels:
                        continue
                    seen_labels.add(key)
                    fields.append(
                        _field_payload(
                            label,
                            field_type,
                            page,
                            rect,
                            seen_ids,
                            field_id_label=f"{row_label}_{column_label}",
                            section=group_label,
                            font_size=6.5 if rect["height"] < 10 else 8,
                            clear_padding=0.25,
                            layout=_layout(
                                "table_cell",
                                group_id=group_id,
                                group_label=group_label,
                                row_label=row_label,
                                column_label=column_label,
                            ),
                        )
                    )
            break
    return fields


def _slug_base(value: str) -> str:
    base = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "_", base).strip("_").lower()


def _signature_fields(
    parsed_pdf: dict[str, Any],
    seen_ids: set[str],
    seen_labels: set[tuple[Any, ...]],
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    lines_by_page = _lines_by_page(parsed_pdf["text_lines"])
    heading_pattern = re.compile(
        r"\b(dibuat oleh|diketahui oleh|disetujui oleh|pemohon|hrd|manager|direktur)\b",
        re.IGNORECASE,
    )
    for page, lines in lines_by_page.items():
        headings = [line for line in lines if heading_pattern.search(str(line["text"]))]
        if not headings:
            continue
        heading_centers = sorted((_line_center(line)[0], line) for line in headings)
        for index, (center_x, heading) in enumerate(heading_centers):
            heading_rect = _line_rect(heading)
            name_lines = [
                line
                for line in lines
                if _line_rect(line)["y"] > heading_rect["y"] + 20
                and _line_rect(line)["y"] < heading_rect["y"] + 120
                and "nama" in str(line["text"]).lower()
                and abs(_line_center(line)[0] - center_x) < 80
            ]
            if not name_lines:
                continue
            name_lines.sort(key=lambda line: abs(_line_center(line)[0] - center_x))
            name_line = name_lines[0]
            name_rect = _line_rect(name_line)
            left_boundary = (
                (heading_centers[index - 1][0] + center_x) / 2
                if index > 0
                else max(54.0, center_x - 70)
            )
            right_boundary = (
                (heading_centers[index + 1][0] + center_x) / 2
                if index + 1 < len(heading_centers)
                else min(_page_size_lookup(parsed_pdf)[page]["width"] - 54, center_x + 70)
            )
            x0 = max(left_boundary + 8, name_rect["x"] - 10)
            x1 = min(right_boundary - 8, max(name_rect["x"] + name_rect["width"] + 10, x0 + 70))
            y0 = heading_rect["y"] + heading_rect["height"] + 12
            y1 = max(name_rect["y"] - 8, y0 + 36)
            rect = _rect_from_bounds(x0, y0, x1, y1, inset=0)
            heading_label = _clean_heuristic_label(str(heading["text"]))
            label = f"Tanda tangan {heading_label}"
            key = _field_key(page, label, rect)
            if key in seen_labels:
                continue
            seen_labels.add(key)
            fields.append(
                _field_payload(
                    label,
                    "signature_image",
                    page,
                    rect,
                    seen_ids,
                    field_id_label=label,
                    section="Persetujuan",
                    placeholder=None,
                    font_size=10,
                    clear=False,
                    layout=_layout(
                        "signature_block",
                        group_id="persetujuan",
                        group_label="Persetujuan",
                        row_label=heading_label,
                    ),
                )
            )
    return fields


def _heuristic_fields_from_text(parsed_pdf: dict[str, Any]) -> list[dict[str, Any]]:
    lines = list(parsed_pdf["text_lines"])
    page_sizes = _page_size_lookup(parsed_pdf)
    fields: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_labels: set[tuple[Any, ...]] = set()

    for index, line in enumerate(lines):
        text = str(line["text"])
        if "[" not in text or "]" not in text:
            continue

        inline_fields = _inline_placeholder_fields(
            line,
            page_sizes[int(line["page"])],
            seen_ids,
            seen_labels,
        )
        if inline_fields:
            fields.extend(inline_fields)
            continue

        rect = line["rect"]
        line_rect = fitz.Rect(
            rect["x"],
            rect["y"],
            rect["x"] + rect["width"],
            rect["y"] + rect["height"],
        )
        raw_label = re.sub(r"\[[^\[\]]*\]", "", text).strip(" :-")
        has_inline_label = bool(raw_label)
        bracket_values = [value.strip() for value in re.findall(r"\[([^\[\]]*)\]", text)]
        if not raw_label and any(value for value in bracket_values):
            continue
        if not raw_label:
            raw_label = _nearest_label(
                line_rect,
                [other for other in lines if int(other["page"]) == int(line["page"])],
            )
        label = _clean_heuristic_label(raw_label)
        if not label:
            continue
        page_size = page_sizes[int(line["page"])]
        field_rect = _expand_placeholder_rect(line, lines, page_size["width"])
        inline_checkbox = bool(has_inline_label and text.lstrip().startswith("["))
        if inline_checkbox:
            base_rect = _line_rect(line)
            leading_offset = len(text) - len(text.lstrip())
            char_width = base_rect["width"] / max(len(text), 1)
            field_rect = {
                "x": round(base_rect["x"] + leading_offset * char_width, 2),
                "y": base_rect["y"],
                "width": min(14.0, max(base_rect["height"], 8.0)),
                "height": base_rect["height"],
            }
        key = _field_key(int(line["page"]), label, field_rect)
        if key in seen_labels:
            continue
        seen_labels.add(key)

        placeholder_kind = "checkbox_box" if inline_checkbox else "bracket_placeholder"
        field_type = _infer_field_type(label, field_rect, placeholder_kind)
        fields.append(_field_payload(label, field_type, int(line["page"]), field_rect, seen_ids))

    for index, line in enumerate(lines):
        raw_label = str(line["text"]).strip()
        if not _is_section_textarea_label(raw_label):
            continue
        label = _clean_heuristic_label(raw_label)
        rect = _line_rect(line)
        page = int(line["page"])
        page_size = page_sizes[page]
        grid = _page_grid(parsed_pdf, page)
        below_lines = [y for y in grid["y"] if y > rect["y"] + rect["height"] - 2]
        if below_lines:
            top = min(below_lines)
            next_lines = [y for y in below_lines if y > top + 18]
            bottom = min(next_lines) if next_lines else top + 80
        else:
            top = rect["y"] + rect["height"] + 8
            next_y = _next_section_y(lines, page, rect["y"])
            bottom = next_y - 8 if next_y is not None else rect["y"] + 80
        bottom = min(bottom, page_size["height"] - 55)
        if bottom - top < 24:
            continue
        field_rect = {
            "x": 55.0,
            "y": round(top + 2, 2),
            "width": max(page_size["width"] - 110, 80),
            "height": round(max(bottom - top - 4, 24), 2),
        }
        key = _field_key(page, label, field_rect)
        if key in seen_labels:
            continue
        seen_labels.add(key)
        fields.append(
            _field_payload(
                label,
                "textarea",
                page,
                field_rect,
                seen_ids,
                field_id_label=f"textarea_{index + 1}_{label}",
                font_size=9,
            )
        )

    fields.extend(_table_fields(parsed_pdf, seen_ids, seen_labels))
    fields.extend(_signature_fields(parsed_pdf, seen_ids, seen_labels))
    return fields


def _heuristic_schema_payload(path: Path, parsed_pdf: dict[str, Any]) -> dict[str, Any]:
    text_fields = _heuristic_fields_from_text(parsed_pdf)
    fields: list[dict[str, Any]] = list(text_fields)
    seen_ids: set[str] = set()
    for field in fields:
        seen_ids.add(str(field["id"]))
    if fields:
        return {
            "path": _schema_form_path(path),
            "title": path.stem,
            "pages": _schema_pages(parsed_pdf),
            "fields": fields,
        }

    compact_candidates = _compact_pdf_parse(path, parsed_pdf)["candidates"]
    for index, candidate in enumerate(compact_candidates):
        label = str(candidate.get("label") or "").strip() or f"Field {index + 1}"
        rect = _rect_payload(candidate["r"])
        if rect["width"] < 5 or rect["height"] < 5:
            continue
        if any(
            int(field.get("page", 0)) == int(candidate["p"])
            and _rect_overlap_ratio(field["rect"], rect) > 0.75
            for field in fields
        ):
            continue
        field_type = _infer_field_type(label, rect, str(candidate.get("k") or ""))
        fields.append(
            {
                "id": _slug_field_id(label, f"field_{index + 1}", seen_ids),
                "label": label,
                "type": field_type,
                "page": int(candidate["p"]),
                "rect": rect,
                "required": False,
                "section": "",
                "placeholder": label if field_type != "checkbox" else None,
                "font_size": 10,
                "clear": True,
            }
        )
    return {
        "path": _schema_form_path(path),
        "title": path.stem,
        "pages": _schema_pages(parsed_pdf),
        "fields": fields,
    }


def _coerce_candidate_id(field: dict[str, Any]) -> int | None:
    raw_candidate_id = field.get("candidate_id")
    if raw_candidate_id is None:
        raw_candidate_id = field.get("candidateId")
    if raw_candidate_id is None:
        raw_candidate_id = field.get("i")
    try:
        return int(raw_candidate_id)
    except (TypeError, ValueError):
        return None


def _expand_model_schema_payload(
    payload: dict[str, Any],
    path: Path,
    parsed_pdf: dict[str, Any],
) -> dict[str, Any]:
    heuristic_payload = _heuristic_schema_payload(path, parsed_pdf)
    candidate_fields = list(heuristic_payload["fields"])
    fields: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, field in enumerate(payload.get("fields") or []):
        if not isinstance(field, dict):
            continue
        candidate_id = _coerce_candidate_id(field)
        if candidate_id is None or candidate_id < 0 or candidate_id >= len(candidate_fields):
            logger.warning(
                "[form-schema] Skip model field without valid candidate_id index=%s field=%s",
                index,
                field,
            )
            continue

        base_field = dict(candidate_fields[candidate_id])
        label = str(field.get("label") or field.get("l") or base_field["label"]).strip()
        raw_field_id = str(field.get("id") or base_field["id"]).strip()
        field_id = _slug_field_id(raw_field_id or label, f"field_{index + 1}", seen_ids)

        if any(key in field for key in ("rect", "r", "x", "y", "width", "height", "page", "p")):
            logger.warning(
                "[form-schema] Ignoring model coordinates for candidate_id=%s id=%s",
                candidate_id,
                field_id,
            )

        field_type = str(field.get("type") or field.get("t") or base_field["type"]).strip()
        layout = dict(base_field.get("layout") or {})
        if isinstance(field.get("layout"), dict):
            for key in ("kind", "group_id", "group_label", "row_label", "column_label", "choice_group"):
                if field["layout"].get(key):
                    layout[key] = str(field["layout"][key])
        fields.append(
            {
                **base_field,
                "id": field_id,
                "label": label or str(base_field["label"]),
                "type": field_type,
                "required": bool(field.get("required") if "required" in field else field.get("req", base_field.get("required", False))),
                "section": str(field.get("section") or field.get("s") or base_field.get("section") or ""),
                "placeholder": str(field.get("placeholder") or field.get("ph") or base_field.get("placeholder") or "") or None,
                "font_size": float(field.get("font_size") or field.get("fs") or base_field.get("font_size") or 10),
                "clear": bool(field.get("clear", base_field.get("clear", True))),
                "layout": layout,
            }
        )

    return {
        "path": _schema_form_path(path),
        "title": str(payload.get("title") or heuristic_payload["title"]),
        "pages": heuristic_payload["pages"],
        "fields": fields,
    }


def _rect_area(rect: dict[str, Any]) -> float:
    return max(float(rect["width"]), 0) * max(float(rect["height"]), 0)


def _rect_overlap_ratio(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_x1 = float(left["x"]) + float(left["width"])
    left_y1 = float(left["y"]) + float(left["height"])
    right_x1 = float(right["x"]) + float(right["width"])
    right_y1 = float(right["y"]) + float(right["height"])
    x0 = max(float(left["x"]), float(right["x"]))
    y0 = max(float(left["y"]), float(right["y"]))
    x1 = min(left_x1, right_x1)
    y1 = min(left_y1, right_y1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    intersection = (x1 - x0) * (y1 - y0)
    return intersection / max(min(_rect_area(left), _rect_area(right)), 0.1)


def _postprocess_fields(fields: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    processed: list[dict[str, Any]] = []
    seen_label_rows: set[tuple[int, str, int]] = set()
    seen_ids: set[str] = set()

    for field in sorted(
        fields,
        key=lambda item: (
            int(item.get("page", 0)),
            float(item.get("rect", {}).get("y", 0)),
            float(item.get("rect", {}).get("x", 0)),
        ),
    ):
        rect = field.get("rect")
        if not isinstance(rect, dict):
            warnings.append(f"skip_no_rect:{field.get('id') or field.get('label')}")
            continue

        label = _clean_heuristic_label(str(field.get("label") or field.get("id") or "Field"))
        field_type = str(field.get("type") or "text")
        if field_type != "checkbox" and (float(rect["width"]) < 18 or float(rect["height"]) < 6):
            warnings.append(f"skip_tiny:{label}")
            continue

        layout = field.get("layout") if isinstance(field.get("layout"), dict) else {}
        layout_kind = str(layout.get("kind") or "")
        if layout_kind in {"inline_placeholder", "signature_block", "table_cell", "choice_matrix"}:
            row_key = (
                int(field.get("page", 0)),
                label.lower(),
                round(float(rect["y"]) / 6),
                round(float(rect["x"]) / 6),
            )
        else:
            row_key = (int(field.get("page", 0)), label.lower(), round(float(rect["y"]) / 6))
        if row_key in seen_label_rows:
            warnings.append(f"dedupe_label_row:{label}")
            continue
        if any(
            int(existing.get("page", 0)) == int(field.get("page", 0))
            and _rect_overlap_ratio(existing["rect"], rect) > 0.88
            for existing in processed
        ):
            warnings.append(f"dedupe_overlap:{label}")
            continue

        seen_label_rows.add(row_key)
        field_id = _slug_field_id(str(field.get("id") or label), f"field_{len(processed) + 1}", seen_ids)
        processed.append(
            {
                **field,
                "id": field_id,
                "label": label,
                "type": field_type,
                "placeholder": str(field.get("placeholder") or label) if field_type != "checkbox" else None,
            }
        )

    return processed


def _quality_score(fields: list[dict[str, Any]], warnings: list[str]) -> float:
    if not fields:
        return 0.0
    score = 1.0
    layout_fields = [
        field
        for field in fields
        if isinstance(field.get("layout"), dict)
        and str(field["layout"].get("kind") or "") in {"table_cell", "choice_matrix", "signature_block", "inline_placeholder"}
    ]
    if len(fields) > 60 and len(layout_fields) < int(len(fields) * 0.5):
        warnings.append("too_many_fields")
        score -= 0.25
    if len(fields) < 3:
        warnings.append("too_few_fields")
        score -= 0.25
    if any(str(field.get("type")) == "signature_image" for field in fields):
        score += 0.02
    if any(str((field.get("layout") or {}).get("kind")) in {"table_cell", "choice_matrix"} for field in fields):
        score += 0.03
    score -= min(len(warnings) * 0.025, 0.45)
    return round(min(max(score, 0.0), 1.0), 2)


def _finalize_schema_payload(
    payload: dict[str, Any],
    *,
    source: str,
    inherited_warnings: list[str] | None = None,
) -> dict[str, Any]:
    warnings = list(inherited_warnings or [])
    fields = _postprocess_fields(list(payload.get("fields") or []), warnings)
    score = _quality_score(fields, warnings)
    return {
        **payload,
        "fields": fields,
        "generator": {
            "source": source,
            "quality_score": score,
            "warnings": warnings,
        },
    }


def _schema_is_better_than(candidate: dict[str, Any], baseline: dict[str, Any]) -> bool:
    candidate_generator = candidate.get("generator") if isinstance(candidate.get("generator"), dict) else {}
    baseline_generator = baseline.get("generator") if isinstance(baseline.get("generator"), dict) else {}
    candidate_fields = len(candidate.get("fields") or [])
    baseline_fields = len(baseline.get("fields") or [])
    if candidate_fields < max(1, int(baseline_fields * 0.65)):
        return False
    return float(candidate_generator.get("quality_score") or 0) >= float(baseline_generator.get("quality_score") or 0)


def _candidate_entry(index: int, field: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": index,
        "id": field["id"],
        "label": field["label"],
        "type": field["type"],
        "page": field["page"],
        "section": field.get("section") or "",
        "placeholder": field.get("placeholder") or "",
        "layout": field.get("layout") or {},
    }


def _candidate_chunks(fields: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    chunk_size = max(get_int_env("FORM_SCHEMA_MODEL_CHUNK_SIZE", 70), 20)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, field in enumerate(fields):
        layout = field.get("layout") if isinstance(field.get("layout"), dict) else {}
        group_id = str(layout.get("group_id") or "")
        if group_id:
            group_key = f"group:{group_id}"
        else:
            group_key = f"page:{int(field.get('page', 0))}:plain"
        grouped.setdefault(group_key, []).append(_candidate_entry(index, field))

    chunks: list[tuple[str, list[dict[str, Any]]]] = []
    for group_key, candidates in grouped.items():
        for offset in range(0, len(candidates), chunk_size):
            chunk = candidates[offset : offset + chunk_size]
            label = group_key if len(candidates) <= chunk_size else f"{group_key}:{offset // chunk_size + 1}"
            chunks.append((label, chunk))
    return chunks


def _model_refined_schema_payload(path: Path, parsed_pdf: dict[str, Any]) -> dict[str, Any]:
    heuristic_payload = _heuristic_schema_payload(path, parsed_pdf)
    collected_fields: list[dict[str, Any]] = []
    warnings: list[str] = []
    refined_title = heuristic_payload["title"]
    for region_label, candidates in _candidate_chunks(list(heuristic_payload["fields"])):
        if not candidates:
            continue
        raw_schema = ""
        try:
            prompt = _schema_prompt_for_candidates(path, heuristic_payload["title"], candidates, region_label)
            raw_schema = _call_groq_schema_model(prompt)
            payload = _extract_json_object(raw_schema)
            expanded = _expand_model_schema_payload(payload, path, parsed_pdf)
            if expanded.get("title"):
                refined_title = str(expanded["title"])
            collected_fields.extend(expanded["fields"])
        except Exception as error:
            if raw_schema:
                logger.error("[form-schema] Raw model output chunk bermasalah region=%s output=%s", region_label, _json_preview(raw_schema))
            warnings.append(f"model_chunk_failed:{region_label}:{error}")
            logger.warning(
                "[form-schema] Chunk model gagal file=%s region=%s error=%s",
                path.name,
                region_label,
                error,
            )

    return {
        "path": heuristic_payload["path"],
        "title": refined_title,
        "pages": heuristic_payload["pages"],
        "fields": collected_fields,
        "_warnings": warnings,
    }


def _json_preview(text: str, limit: int = 500) -> str:
    preview = " ".join(text.strip().split())
    if len(preview) <= limit:
        return preview
    return preview[: limit - 1].rstrip() + "..."


def _call_groq_schema_model(prompt: str) -> str:
    try:
        from groq import Groq
    except ImportError as error:
        raise RuntimeError("Dependency Groq belum terpasang. Jalankan pip install -r requirements.txt.") from error

    api_key = get_env("FORM_SCHEMA_GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("FORM_SCHEMA_GROQ_API_KEY belum diisi.")

    model_name = get_env("FORM_SCHEMA_MODEL", "openai/gpt-oss-120b").removeprefix("groq/")
    configured_tokens = get_int_env("FORM_SCHEMA_MAX_COMPLETION_TOKENS", _MAX_SCHEMA_OUTPUT_TOKENS)
    max_completion_tokens = min(configured_tokens, _MAX_SCHEMA_OUTPUT_TOKENS)
    if configured_tokens != max_completion_tokens:
        logger.warning(
            "[form-schema] FORM_SCHEMA_MAX_COMPLETION_TOKENS=%s dicap ke %s agar muat batas Groq on-demand",
            configured_tokens,
            max_completion_tokens,
        )
    configured_reasoning = get_env("FORM_SCHEMA_REASONING_EFFORT", "low")
    reasoning_effort = configured_reasoning if configured_reasoning in {"none", "low"} else "low"
    if configured_reasoning != reasoning_effort:
        logger.warning(
            "[form-schema] FORM_SCHEMA_REASONING_EFFORT=%s dicap ke %s agar output JSON tidak kepotong",
            configured_reasoning,
            reasoning_effort,
        )

    logger.info(
        "[form-schema] Mengirim prompt ke Groq model=%s prompt_chars=%s max_tokens=%s",
        model_name,
        len(prompt),
        max_completion_tokens,
    )

    client = Groq(
        api_key=api_key,
        timeout=get_int_env("GROQ_TIMEOUT_SECONDS", 240),
    )
    completion = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=get_float_env("FORM_SCHEMA_TEMPERATURE", 1.0),
        max_completion_tokens=max_completion_tokens,
        top_p=get_float_env("FORM_SCHEMA_TOP_P", 1.0),
        reasoning_effort=reasoning_effort,
        response_format={"type": "json_object"},
        stream=True,
        stop=None,
    )
    chunks: list[str] = []
    for chunk in completion:
        choices = getattr(chunk, "choices", None)
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        chunks.append(str(getattr(delta, "content", "") or ""))
    result = "".join(chunks).strip()
    logger.info("[form-schema] Respons Groq diterima chars=%s", len(result))
    return result


def generate_schema_for_form_pdf(path: Path) -> FormSchemaGenerationResult:
    started_at = time.perf_counter()
    try:
        logger.info("[form-schema] Mulai generate schema untuk %s", path.name)
        parsed_pdf = parse_pdf_for_schema(path)
        parsed_tables = sum(1 for page in parsed_pdf["pages"] if _grid_rows(parsed_pdf, int(page["number"])))
        logger.info(
            "[form-schema] PDF parsed file=%s pages=%s text_lines=%s candidates=%s tables=%s grid_lines=%s",
            path.name,
            len(parsed_pdf["pages"]),
            len(parsed_pdf["text_lines"]),
            len(parsed_pdf["field_candidates"]),
            parsed_tables,
            len(parsed_pdf.get("grid_lines", [])),
        )

        heuristic_schema = _finalize_schema_payload(
            _heuristic_schema_payload(path, parsed_pdf),
            source="heuristic",
        )
        schema = heuristic_schema
        if get_env("FORM_SCHEMA_GROQ_API_KEY", ""):
            try:
                logger.info("[form-schema] Mulai refinement Groq chunked untuk %s", path.name)
                payload = _model_refined_schema_payload(path, parsed_pdf)
                model_warnings = list(payload.pop("_warnings", []))
                model_schema = _finalize_schema_payload(
                    payload,
                    source="mixed" if model_warnings else "model",
                    inherited_warnings=model_warnings,
                )
                if _schema_is_better_than(model_schema, heuristic_schema):
                    schema = model_schema
                else:
                    logger.warning(
                        "[form-schema] Model schema ditolak untuk %s, fallback heuristic model_score=%s heuristic_score=%s model_fields=%s heuristic_fields=%s",
                        path.name,
                        model_schema["generator"]["quality_score"],
                        heuristic_schema["generator"]["quality_score"],
                        len(model_schema["fields"]),
                        len(heuristic_schema["fields"]),
                    )
            except Exception as model_error:
                logger.warning(
                    "[form-schema] Output model gagal dipakai untuk %s, fallback ke schema heuristik: %s",
                    path.name,
                    model_error,
                )
        else:
            schema["generator"]["warnings"].append("missing_form_schema_groq_api_key")
            schema["generator"]["quality_score"] = _quality_score(schema["fields"], schema["generator"]["warnings"])
            logger.warning(
                "[form-schema] FORM_SCHEMA_GROQ_API_KEY belum diisi, memakai schema heuristic untuk %s",
                path.name,
            )

        schema = _validate_schema_payload(schema, path)
        if not schema["fields"]:
            raise RuntimeError("Parser PDF tidak menemukan field form valid.")

        schema_dir = _form_schema_dir()
        schema_dir.mkdir(parents=True, exist_ok=True)
        schema_path = schema_dir / _schema_file_name(path)
        schema_path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info(
            "[form-schema] Schema tersimpan file=%s pages=%s tables=%s signatures=%s candidates=%s selected=%s source=%s quality_score=%s warnings=%s duration=%.2fs",
            schema_path,
            len(schema["pages"]),
            len(
                {
                    str((field.get("layout") or {}).get("group_id") or "")
                    for field in schema["fields"]
                    if str((field.get("layout") or {}).get("kind") or "") in {"table_cell", "choice_matrix"}
                }
                - {""}
            ),
            sum(1 for field in schema["fields"] if field["type"] == "signature_image"),
            len(parsed_pdf["field_candidates"]),
            len(schema["fields"]),
            schema.get("generator", {}).get("source"),
            schema.get("generator", {}).get("quality_score"),
            schema.get("generator", {}).get("warnings"),
            time.perf_counter() - started_at,
        )
        return FormSchemaGenerationResult(
            generated=True,
            schema_path=schema_path.relative_to(schema_dir.parent).as_posix(),
        )
    except Exception as error:
        logger.exception("[form-schema] Gagal generate schema untuk %s", path.name)
        return FormSchemaGenerationResult(generated=False, error=str(error))
