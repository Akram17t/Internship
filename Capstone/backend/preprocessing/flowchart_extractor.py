from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import fitz
from langchain_core.documents import Document

from backend.settings import get_env, get_float_env, get_int_env


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FLOWCHART_PROMPT_VERSION = "2"
FLOWCHART_HEADING_PATTERN = re.compile(
    r"(?im)^(?P<number>\d+)\.\s+ALUR\s+PROSES\s*$"
)
VALID_NODE_TYPES = {"start", "process", "decision", "end", "document", "unknown"}
_FLOWCHART_TIMING_SECONDS = 0.0
_FLOWCHART_DOCUMENT_COUNT = 0

FLOWCHART_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": sorted(VALID_NODE_TYPES),
                    },
                    "text": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["id", "type", "text", "confidence"],
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "label": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["from", "to", "label", "confidence"],
            },
        },
        "confidence": {"type": "number"},
    },
    "required": ["title", "nodes", "edges", "confidence"],
}
EDGE_CONFIRMATION_SCHEMA = {
    "type": "object",
    "properties": {
        "visible": {"type": "boolean"},
        "label": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["visible", "label", "confidence"],
}

FLOWCHART_PROMPT = """\
Ekstrak flowchart pada gambar menjadi SATU JSON object dengan bentuk persis:
{"title":"Judul","nodes":[{"id":"n1","type":"start","text":"Mulai","confidence":0.9}],"edges":[{"from":"n1","to":"n2","label":"","confidence":0.9}],"confidence":0.9}

Aturan:
- Jangan gunakan markdown, code fence, array terluar, key "node", atau key "edges_from".
- Baca hanya isi diagram, abaikan header/footer dokumen.
- Setiap kotak, terminator, dan diamond keputusan menjadi satu node.
- Gunakan type: start, process, decision, end, document, atau unknown.
- Ikuti arah ujung panah untuk membuat edges.
- Label cabang seperti Ya/Tidak harus disimpan pada edge terkait.
- Urutkan nodes dan edges mulai dari alur utama bagian atas.
- Jangan menambah langkah yang tidak terlihat pada gambar.
- Confidence bernilai 0 sampai 1.
- Jika teks kurang jelas, salin bagian yang terbaca dan turunkan confidence.
"""


@dataclass(frozen=True)
class FlowchartCandidate:
    heading_page: int
    image_page: int
    section: str


def reset_flowchart_timing() -> None:
    global _FLOWCHART_TIMING_SECONDS, _FLOWCHART_DOCUMENT_COUNT
    _FLOWCHART_TIMING_SECONDS = 0.0
    _FLOWCHART_DOCUMENT_COUNT = 0


def get_flowchart_timing() -> tuple[float, int]:
    return _FLOWCHART_TIMING_SECONDS, _FLOWCHART_DOCUMENT_COUNT


def _record_flowchart_timing(seconds: float, document_count: int) -> None:
    global _FLOWCHART_TIMING_SECONDS, _FLOWCHART_DOCUMENT_COUNT
    _FLOWCHART_TIMING_SECONDS += seconds
    _FLOWCHART_DOCUMENT_COUNT += document_count


def _is_enabled() -> bool:
    return get_env("FLOWCHART_EXTRACTION_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _resolve_cache_dir() -> Path:
    configured = Path(get_env("FLOWCHART_CACHE_DIR", "backend/cache/flowcharts"))
    return configured if configured.is_absolute() else PROJECT_ROOT / configured


def detect_flowchart_candidates(
    page_texts: list[str],
    image_area_ratios: list[float],
    *,
    min_image_area_ratio: float | None = None,
    max_continuation_pages: int | None = None,
) -> list[FlowchartCandidate]:
    """Temukan halaman gambar diagram dari heading pada halaman yang sama/sebelumnya."""
    minimum_ratio = (
        min_image_area_ratio
        if min_image_area_ratio is not None
        else get_float_env("FLOWCHART_MIN_IMAGE_AREA_RATIO", 0.08)
    )
    continuation_limit = (
        max_continuation_pages
        if max_continuation_pages is not None
        else get_int_env("FLOWCHART_MAX_CONTINUATION_PAGES", 1)
    )
    candidates: list[FlowchartCandidate] = []
    pending: tuple[int, str] | None = None

    for page_index, page_text in enumerate(page_texts):
        heading_match = FLOWCHART_HEADING_PATTERN.search(page_text)
        if heading_match:
            pending = (
                page_index,
                f"{heading_match.group('number')}. ALUR PROSES",
            )

        if pending is None:
            continue

        heading_page, section = pending
        distance = page_index - heading_page
        if distance > continuation_limit:
            pending = None
            continue
        if image_area_ratios[page_index] < minimum_ratio:
            continue

        candidates.append(
            FlowchartCandidate(
                heading_page=heading_page,
                image_page=page_index,
                section=section,
            )
        )
        pending = None

    return candidates


def _largest_placed_image(page: fitz.Page) -> tuple[int, float] | None:
    page_area = max(float(page.rect.width * page.rect.height), 1.0)
    largest: tuple[int, float] | None = None

    for image in page.get_images(full=True):
        xref = int(image[0])
        for rect in page.get_image_rects(xref):
            ratio = float(rect.width * rect.height) / page_area
            if largest is None or ratio > largest[1]:
                largest = (xref, ratio)

    return largest


def _cache_key(pdf_bytes: bytes, image_page: int, model_name: str) -> str:
    digest = hashlib.sha256()
    digest.update(pdf_bytes)
    digest.update(f":{image_page}:{model_name}:{FLOWCHART_PROMPT_VERSION}".encode("utf-8"))
    return digest.hexdigest()


def _read_cache(cache_path: Path) -> dict[str, Any] | None:
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_cache(cache_path: Path, payload: dict[str, Any]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = cache_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(cache_path)


def _decode_json_content(content: str) -> Any:
    normalized_content = content.strip()
    code_fence_match = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        normalized_content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if code_fence_match:
        normalized_content = code_fence_match.group(1)
    try:
        return json.loads(normalized_content)
    except json.JSONDecodeError as error:
        raise RuntimeError("Ollama vision returned invalid JSON") from error


def _send_ollama_vision(
    image_bytes: bytes,
    model_name: str,
    prompt: str,
    schema: dict[str, Any],
) -> Any:
    base_url = get_env("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    request_payload = {
        "model": model_name,
        "stream": False,
        "think": False,
        "format": schema,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [base64.b64encode(image_bytes).decode("ascii")],
            }
        ],
        "options": {"temperature": 0},
    }
    request = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(request_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = get_int_env("FLOWCHART_OLLAMA_TIMEOUT_SECONDS", 240)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama vision returned HTTP {error.code}: {detail}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Ollama vision request failed: {error}") from error

    content = response_payload.get("message", {}).get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama vision returned an empty response")
    return _decode_json_content(content)


def _call_ollama_vision(
    image_bytes: bytes,
    model_name: str,
    graph_issues: list[str] | None = None,
) -> dict[str, Any]:
    prompt = FLOWCHART_PROMPT
    if graph_issues:
        prompt += (
            "\nHasil pembacaan sebelumnya tidak lengkap:\n- "
            + "\n- ".join(graph_issues)
            + "\nBaca ulang seluruh gambar dari awal dan pastikan semua panah yang terlihat masuk JSON."
        )
    result = _send_ollama_vision(image_bytes, model_name, prompt, FLOWCHART_SCHEMA)
    if not isinstance(result, dict):
        raise RuntimeError("Ollama vision response must be a JSON object")
    return result


def _bounded_confidence(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def _validate_result(raw_result: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    raw_nodes = raw_result.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raw_nodes = []

    for index, raw_node in enumerate(raw_nodes, start=1):
        if not isinstance(raw_node, dict):
            continue
        node_id = str(raw_node.get("id") or f"n{index}").strip()
        text = " ".join(str(raw_node.get("text") or "").split())
        if not text or node_id in node_ids:
            continue
        node_type = str(raw_node.get("type") or "unknown").strip().lower()
        if node_type not in VALID_NODE_TYPES:
            node_type = "unknown"
        node_ids.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "text": text,
                "confidence": _bounded_confidence(raw_node.get("confidence")),
            }
        )

    if not nodes:
        raise RuntimeError("Flowchart extraction did not produce any readable nodes")

    edges: list[dict[str, Any]] = []
    raw_edges = raw_result.get("edges", [])
    if not isinstance(raw_edges, list):
        raw_edges = []
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, dict):
            continue
        source = str(raw_edge.get("from") or "").strip()
        target = str(raw_edge.get("to") or "").strip()
        if source not in node_ids or target not in node_ids:
            continue
        edges.append(
            {
                "from": source,
                "to": target,
                "label": " ".join(str(raw_edge.get("label") or "").split()),
                "confidence": _bounded_confidence(raw_edge.get("confidence")),
            }
        )

    title = " ".join(str(raw_result.get("title") or "Alur Proses").split())
    return {
        "title": title,
        "nodes": nodes,
        "edges": edges,
        "confidence": _bounded_confidence(raw_result.get("confidence")),
    }


def _find_graph_issues(result: dict[str, Any]) -> list[str]:
    nodes = result["nodes"]
    edges = result["edges"]
    incoming = {node["id"]: 0 for node in nodes}
    outgoing = {node["id"]: 0 for node in nodes}
    for edge in edges:
        outgoing[edge["from"]] += 1
        incoming[edge["to"]] += 1

    issues: list[str] = []
    for node in nodes:
        node_id = node["id"]
        node_type = node["type"]
        node_text = node["text"]
        if node_type == "start" and outgoing[node_id] == 0:
            issues.append(f"Node start '{node_text}' tidak memiliki panah keluar.")
        elif node_type == "end" and incoming[node_id] == 0:
            issues.append(f"Node end '{node_text}' tidak memiliki panah masuk.")
        elif node_type not in {"start", "end"}:
            if incoming[node_id] == 0:
                issues.append(f"Node '{node_text}' tidak memiliki panah masuk.")
            if outgoing[node_id] == 0:
                issues.append(f"Node '{node_text}' tidak memiliki panah keluar.")
    return issues


def _find_dangling_edge_candidate(
    result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    nodes = result["nodes"]
    edges = result["edges"]
    incoming = {node["id"]: 0 for node in nodes}
    outgoing = {node["id"]: 0 for node in nodes}
    for edge in edges:
        outgoing[edge["from"]] += 1
        incoming[edge["to"]] += 1

    sources = [
        node
        for node in nodes
        if node["type"] != "end" and outgoing[node["id"]] == 0
    ]
    targets = [
        node
        for node in nodes
        if node["type"] != "start" and incoming[node["id"]] == 0
    ]
    if len(sources) == 1 and len(targets) == 1 and sources[0]["id"] != targets[0]["id"]:
        return sources[0], targets[0]
    return None


def _confirm_dangling_edge(
    image_bytes: bytes,
    model_name: str,
    result: dict[str, Any],
) -> bool:
    candidate = _find_dangling_edge_candidate(result)
    if candidate is None:
        return False
    source, target = candidate
    prompt = (
        "Periksa gambar flowchart dengan teliti. Apakah ada panah yang terlihat langsung "
        f"dari node \"{source['text']}\" menuju node \"{target['text']}\"? "
        'Balas hanya JSON object: {"visible":true,"label":"","confidence":0.9}. '
        "Jangan menebak jika panah tidak terlihat."
    )
    confirmation = _send_ollama_vision(
        image_bytes,
        model_name,
        prompt,
        EDGE_CONFIRMATION_SCHEMA,
    )
    if not isinstance(confirmation, dict) or confirmation.get("visible") is not True:
        return False
    confidence = _bounded_confidence(confirmation.get("confidence"))
    minimum_confidence = get_float_env(
        "FLOWCHART_EDGE_CONFIRMATION_MIN_CONFIDENCE",
        0.85,
    )
    if confidence < minimum_confidence:
        return False
    result["edges"].append(
        {
            "from": source["id"],
            "to": target["id"],
            "label": " ".join(str(confirmation.get("label") or "").split()),
            "confidence": confidence,
        }
    )
    return True


def _linearize_flowchart(section: str, result: dict[str, Any]) -> str:
    node_by_id = {node["id"]: node for node in result["nodes"]}
    lines = [
        section,
        str(result["title"]),
        "",
        "Tahapan yang terbaca:",
    ]
    for index, node in enumerate(result["nodes"], start=1):
        node_type = str(node["type"]).capitalize()
        lines.append(f"{index}. [{node_type}] {node['text']}")

    if result["edges"]:
        lines.extend(["", "Hubungan dan arah alur:"])
        for edge in result["edges"]:
            source = node_by_id[edge["from"]]["text"]
            target = node_by_id[edge["to"]]["text"]
            label = f" --{edge['label']}-->" if edge["label"] else " ->"
            lines.append(f"- {source}{label} {target}")

    return "\n".join(lines).strip()


def extract_flowchart_documents(pdf_path: Path) -> list[Document]:
    """Ekstrak hanya image flowchart yang terdeteksi menjadi Document retrieval."""
    if not _is_enabled():
        return []

    started_at = perf_counter()
    model_name = get_env("FLOWCHART_VISION_MODEL", "qwen3.5:9b")
    minimum_confidence = get_float_env("FLOWCHART_MIN_CONFIDENCE", 0.6)
    pdf_bytes = pdf_path.read_bytes()
    flowchart_documents: list[Document] = []

    with fitz.open(pdf_path) as pdf:
        page_texts = [page.get_text("text") or "" for page in pdf]
        image_details = [_largest_placed_image(page) for page in pdf]
        image_area_ratios = [details[1] if details else 0.0 for details in image_details]
        candidates = detect_flowchart_candidates(page_texts, image_area_ratios)

        for candidate in candidates:
            image_details_for_page = image_details[candidate.image_page]
            if image_details_for_page is None:
                continue
            xref, image_area_ratio = image_details_for_page
            cache_key = _cache_key(pdf_bytes, candidate.image_page, model_name)
            cache_path = _resolve_cache_dir() / f"{cache_key}.json"
            cached_payload = _read_cache(cache_path)
            extraction_error = ""
            graph_issues: list[str] = []

            try:
                if cached_payload and cached_payload.get("status") == "success":
                    result = _validate_result(cached_payload["result"])
                    cache_status = "hit"
                    graph_validation_attempted = bool(
                        cached_payload.get("graph_validation_attempted")
                    )
                else:
                    image_bytes = pdf.extract_image(xref)["image"]
                    result = _validate_result(_call_ollama_vision(image_bytes, model_name))
                    cache_status = "miss"
                    graph_validation_attempted = False

                graph_issues = _find_graph_issues(result)
                if graph_issues and not graph_validation_attempted:
                    graph_validation_attempted = True
                    image_bytes = pdf.extract_image(xref)["image"]
                    try:
                        repaired_result = _validate_result(
                            _call_ollama_vision(image_bytes, model_name, graph_issues)
                        )
                        repaired_issues = _find_graph_issues(repaired_result)
                        if len(repaired_issues) < len(graph_issues):
                            result = repaired_result
                            graph_issues = repaired_issues
                        cache_status = "repair"
                    except RuntimeError as repair_error:
                        LOGGER.warning(
                            "Flowchart graph repair failed for %s page %s: %s",
                            pdf_path.name,
                            candidate.image_page + 1,
                            repair_error,
                        )

                if graph_issues:
                    image_bytes = pdf.extract_image(xref)["image"]
                    try:
                        if _confirm_dangling_edge(image_bytes, model_name, result):
                            graph_issues = _find_graph_issues(result)
                            cache_status = "repair"
                    except RuntimeError as confirmation_error:
                        LOGGER.warning(
                            "Flowchart edge confirmation failed for %s page %s: %s",
                            pdf_path.name,
                            candidate.image_page + 1,
                            confirmation_error,
                        )

                if cache_status != "hit" or graph_validation_attempted:
                    _write_cache(
                        cache_path,
                        {
                            "status": "success",
                            "source": pdf_path.name,
                            "image_page": candidate.image_page,
                            "model": model_name,
                            "prompt_version": FLOWCHART_PROMPT_VERSION,
                            "graph_validation_attempted": graph_validation_attempted,
                            "graph_issues": graph_issues,
                            "result": result,
                        },
                    )
            except (KeyError, OSError, RuntimeError, TypeError) as error:
                result = None
                cache_status = "error"
                extraction_error = str(error)
                LOGGER.warning(
                    "Flowchart extraction failed for %s page %s: %s",
                    pdf_path.name,
                    candidate.image_page + 1,
                    error,
                )

            metadata: dict[str, Any] = {
                "source": pdf_path.name,
                "doc_type": "pdf",
                "document_kind": "sop",
                "title": pdf_path.stem,
                "page": candidate.image_page,
                "section": candidate.section,
                "content_type": "flowchart",
                "extraction_method": "ollama_vision",
                "flowchart_model": model_name,
                "flowchart_cache": cache_status,
                "flowchart_image_area_ratio": round(image_area_ratio, 4),
            }
            if result is None:
                metadata["anomaly"] = "flowchart_extraction_failed"
                metadata["flowchart_error"] = extraction_error[:500]
                flowchart_documents.append(Document(page_content="", metadata=metadata))
                continue

            metadata.update(
                {
                    "flowchart_confidence": result["confidence"],
                    "flowchart_node_count": len(result["nodes"]),
                    "flowchart_edge_count": len(result["edges"]),
                }
            )
            if graph_issues:
                metadata["anomaly"] = "flowchart_incomplete_graph"
                metadata["flowchart_graph_issues"] = " | ".join(graph_issues)[:1000]
            elif result["confidence"] < minimum_confidence:
                metadata["anomaly"] = "flowchart_low_confidence"

            flowchart_documents.append(
                Document(
                    page_content=_linearize_flowchart(candidate.section, result),
                    metadata=metadata,
                )
            )

    _record_flowchart_timing(
        perf_counter() - started_at,
        len(flowchart_documents),
    )
    return flowchart_documents
