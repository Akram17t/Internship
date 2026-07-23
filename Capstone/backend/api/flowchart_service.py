from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import fitz

from backend.settings import get_env


ROOT_DIR = Path(__file__).resolve().parents[2]
FLOWCHART_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def _flowchart_cache_dir() -> Path:
    configured = Path(get_env("FLOWCHART_CACHE_DIR", "backend/cache/flowcharts"))
    return configured if configured.is_absolute() else ROOT_DIR / configured


def _data_dir() -> Path:
    configured = Path(get_env("DATA_DIR", "backend/data"))
    return configured if configured.is_absolute() else ROOT_DIR / configured


def _is_display_enabled() -> bool:
    return get_env("FLOWCHART_DISPLAY_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _load_cache_payloads(cache_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    payloads: list[tuple[Path, dict[str, Any]]] = []
    if not cache_dir.exists():
        return payloads

    for path in cache_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("status") == "success":
            payloads.append((path, payload))

    return sorted(
        payloads,
        key=lambda item: item[0].stat().st_mtime,
        reverse=True,
    )


def _existing_source_names(data_dir: Path | None = None) -> set[str]:
    base_dir = data_dir or _data_dir()
    if not base_dir.exists():
        return set()
    return {path.name for path in base_dir.rglob("*") if path.is_file()}


def clear_flowchart_cache_for_source(
    source: str,
    *,
    cache_dir: Path | None = None,
) -> int:
    normalized_source = Path(str(source or "")).name.strip()
    if not normalized_source:
        return 0

    removed = 0
    for path, payload in _load_cache_payloads(cache_dir or _flowchart_cache_dir()):
        if str(payload.get("source") or "").strip() != normalized_source:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def prune_stale_flowchart_cache(
    valid_sources: set[str] | list[str] | tuple[str, ...],
    *,
    cache_dir: Path | None = None,
) -> int:
    normalized_sources = {
        Path(str(source or "")).name.strip()
        for source in valid_sources
        if str(source or "").strip()
    }

    removed = 0
    seen_keys: set[tuple[str, int | None]] = set()
    for path, payload in _load_cache_payloads(cache_dir or _flowchart_cache_dir()):
        payload_source = Path(str(payload.get("source") or "")).name.strip()
        image_page = payload.get("image_page")
        dedupe_key = (payload_source, image_page if isinstance(image_page, int) else None)
        if payload_source and payload_source in normalized_sources and dedupe_key not in seen_keys:
            seen_keys.add(dedupe_key)
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def _flowchart_from_payload(
    path: Path,
    payload: dict[str, Any],
    *,
    section: str,
) -> dict[str, Any] | None:
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    if not str(result.get("text") or "").strip():
        return None

    page_index = payload.get("image_page")
    return {
        "id": path.stem,
        "title": str(result.get("title") or "Alur Proses"),
        "source": str(payload.get("source") or ""),
        "page": page_index + 1 if isinstance(page_index, int) else None,
        "section": section,
        "confidence": float(result.get("confidence") or 0),
        "image_url": f"/api/flowcharts/{path.stem}",
    }


def find_flowcharts_for_citations(
    citations: list[dict[str, object]],
    *,
    cache_dir: Path | None = None,
    model_name: str | None = None,
    display_enabled: bool | None = None,
) -> list[dict[str, Any]]:
    """Cari payload diagram untuk citation flowchart tanpa menyentuh vector DB."""
    if display_enabled is not True and (
        display_enabled is False or not _is_display_enabled()
    ):
        return []
    if get_env("FLOWCHART_EXTRACTION_ENABLED", "true").lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return []

    expected_model = model_name or get_env(
        "FLOWCHART_MODEL",
        get_env("MODEL", "kr/claude-sonnet-4.5"),
    )
    payloads = _load_cache_payloads(cache_dir or _flowchart_cache_dir())
    existing_sources = _existing_source_names()
    flowcharts: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for citation in citations:
        source = str(citation.get("source") or "")
        page = citation.get("page")
        section = str(citation.get("section") or "")
        content_type = str(citation.get("content_type") or "")
        if content_type != "flowchart" and "alur proses" not in section.lower():
            continue
        if source not in existing_sources:
            continue

        for path, payload in payloads:
            image_page = payload.get("image_page")
            if payload.get("source") != source:
                continue
            if isinstance(page, int) and image_page != page - 1:
                continue
            if payload.get("model") != expected_model:
                continue

            flowchart = _flowchart_from_payload(path, payload, section=section)
            if flowchart is None:
                continue
            if flowchart["id"] not in used_ids:
                flowcharts.append(flowchart)
                used_ids.add(flowchart["id"])
            break

    return flowcharts


def _largest_image_xref(page: fitz.Page) -> int | None:
    page_area = max(float(page.rect.width * page.rect.height), 1.0)
    largest_xref: int | None = None
    largest_ratio = 0.0
    for image in page.get_images(full=True):
        xref = int(image[0])
        for rect in page.get_image_rects(xref):
            ratio = float(rect.width * rect.height) / page_area
            if ratio > largest_ratio:
                largest_xref = xref
                largest_ratio = ratio
    return largest_xref


def get_flowchart_image(
    flowchart_id: str,
    *,
    allow_disabled: bool = False,
) -> tuple[bytes, str] | None:
    """Ambil image object flowchart asli dari PDF berdasarkan cache id aman."""
    if not allow_disabled and not _is_display_enabled():
        return None
    if not FLOWCHART_ID_PATTERN.fullmatch(flowchart_id):
        return None
    cache_path = _flowchart_cache_dir() / f"{flowchart_id}.json"
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return None

    source = Path(str(payload.get("source") or "")).name
    page_index = payload.get("image_page")
    if not source or not isinstance(page_index, int):
        return None

    data_dir = _data_dir()
    source_path = next(
        (path for path in data_dir.rglob(source) if path.is_file() and path.name == source),
        None,
    )
    if source_path is None:
        return None

    try:
        with fitz.open(source_path) as pdf:
            if page_index < 0 or page_index >= len(pdf):
                return None
            xref = _largest_image_xref(pdf[page_index])
            if xref is None:
                return None
            image = pdf.extract_image(xref)
    except (OSError, RuntimeError, ValueError):
        return None

    content = image.get("image")
    extension = str(image.get("ext") or "png").lower()
    if not isinstance(content, bytes):
        return None
    media_type = "image/jpeg" if extension in {"jpg", "jpeg"} else f"image/{extension}"
    return content, media_type
