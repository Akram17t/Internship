from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.settings import get_env, get_float_env


ROOT_DIR = Path(__file__).resolve().parents[2]


def _flowchart_cache_dir() -> Path:
    configured = Path(get_env("FLOWCHART_CACHE_DIR", "backend/cache/flowcharts"))
    return configured if configured.is_absolute() else ROOT_DIR / configured


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


def _diagram_from_payload(
    path: Path,
    payload: dict[str, Any],
    *,
    section: str,
) -> dict[str, Any] | None:
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    nodes = result.get("nodes")
    edges = result.get("edges")
    if not isinstance(nodes, list) or not nodes or not isinstance(edges, list):
        return None
    if payload.get("graph_issues"):
        return None

    normalized_nodes = [
        {
            "id": str(node.get("id") or ""),
            "type": str(node.get("type") or "unknown"),
            "text": str(node.get("text") or ""),
            "confidence": float(node.get("confidence") or 0),
        }
        for node in nodes
        if isinstance(node, dict) and node.get("id") and node.get("text")
    ]
    node_ids = {node["id"] for node in normalized_nodes}
    normalized_edges = [
        {
            "source": str(edge.get("from") or ""),
            "target": str(edge.get("to") or ""),
            "label": str(edge.get("label") or ""),
            "confidence": float(edge.get("confidence") or 0),
        }
        for edge in edges
        if isinstance(edge, dict)
        and str(edge.get("from") or "") in node_ids
        and str(edge.get("to") or "") in node_ids
    ]
    if not normalized_nodes:
        return None

    page_index = payload.get("image_page")
    return {
        "id": path.stem,
        "title": str(result.get("title") or "Alur Proses"),
        "source": str(payload.get("source") or ""),
        "page": page_index + 1 if isinstance(page_index, int) else None,
        "section": section,
        "confidence": float(result.get("confidence") or 0),
        "nodes": normalized_nodes,
        "edges": normalized_edges,
    }


def find_flowcharts_for_citations(
    citations: list[dict[str, object]],
    *,
    cache_dir: Path | None = None,
    model_name: str | None = None,
) -> list[dict[str, Any]]:
    """Cari payload diagram untuk citation flowchart tanpa menyentuh vector DB."""
    if get_env("FLOWCHART_EXTRACTION_ENABLED", "true").lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return []

    expected_model = model_name or get_env("FLOWCHART_VISION_MODEL", "qwen3.5:9b")
    minimum_confidence = get_float_env("FLOWCHART_MIN_CONFIDENCE", 0.6)
    payloads = _load_cache_payloads(cache_dir or _flowchart_cache_dir())
    diagrams: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for citation in citations:
        source = str(citation.get("source") or "")
        page = citation.get("page")
        section = str(citation.get("section") or "")
        content_type = str(citation.get("content_type") or "")
        if content_type != "flowchart" and "alur proses" not in section.lower():
            continue

        for path, payload in payloads:
            image_page = payload.get("image_page")
            if payload.get("source") != source:
                continue
            if isinstance(page, int) and image_page != page - 1:
                continue
            if payload.get("model") != expected_model:
                continue

            diagram = _diagram_from_payload(path, payload, section=section)
            if diagram is None or diagram["confidence"] < minimum_confidence:
                continue
            if diagram["id"] not in used_ids:
                diagrams.append(diagram)
                used_ids.add(diagram["id"])
            break

    return diagrams
