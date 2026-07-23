from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import fitz
from langchain_core.documents import Document

from backend.settings import get_env, get_float_env, get_int_env


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FLOWCHART_PROMPT_VERSION = "4"
FLOWCHART_HEADING_PATTERN = re.compile(
    r"(?im)^(?P<number>\d+)\.\s+ALUR\s+PROSES\s*$"
)
_FLOWCHART_TIMING_SECONDS = 0.0
_FLOWCHART_DOCUMENT_COUNT = 0

FLOWCHART_PROMPT = """\
Baca flowchart pada gambar, lalu tulis ulang menjadi plain text dengan format persis seperti ini:

Tahapan yang terbaca:
1. [Start] Mulai
2. [Process] Nama proses
3. [Decision] Pertanyaan keputusan?
4. [End] Selesai

Hubungan dan arah alur:
- Mulai -> Nama proses
- Nama proses -> Pertanyaan keputusan?
- Pertanyaan keputusan? --Ya--> Selesai
- Pertanyaan keputusan? --Tidak--> Nama proses

Aturan:
- Plain text saja. Jangan gunakan markdown, code fence, JSON, tabel, atau penjelasan tambahan.
- Baca hanya isi flowchart pada gambar, abaikan header/footer dokumen.
- Setiap kotak, terminator, diamond keputusan, dan dokumen yang terlihat menjadi satu tahapan.
- Gunakan type: Start, Process, Decision, End, Document, atau Unknown.
- Ikuti arah ujung panah untuk bagian hubungan.
- Label cabang seperti Ya/Tidak harus ditulis dengan format --Ya--> atau --Tidak-->.
- Urutkan nodes dan edges mulai dari alur utama bagian atas.
- Jangan menambah langkah yang tidak terlihat pada gambar.
- Jika teks kurang jelas, salin bagian yang terbaca.
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


def _strip_thinking_blocks(content: str) -> str:
    value = re.sub(
        r"<think\b[^>]*>.*?</think>",
        "",
        str(content),
        flags=re.IGNORECASE | re.DOTALL,
    )
    return value.replace("<think>", "").replace("</think>", "").strip()


def _clean_flowchart_text(content: str) -> str:
    value = _strip_thinking_blocks(content)
    fence_match = re.fullmatch(
        r"```(?:text)?\s*(?P<body>.*?)\s*```",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fence_match:
        value = fence_match.group("body")

    lines = [line.rstrip() for line in value.replace("\r\n", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _image_media_type(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        return "image/gif"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _chat_message_content(completion: Any) -> str:
    choices: Any = getattr(completion, "choices", None)
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return str(getattr(message, "content", "") or "")


def _flowchart_base_url() -> str:
    return get_env("FLOWCHART_BASE_URL", get_env("CHAT_BASE_URL", "http://localhost:20128/v1")).rstrip("/")


def _flowchart_api_key() -> str:
    for env_name in (
        "FLOWCHART_API_KEY",
        "CHAT_API_KEY",
        "OPENAI_API_KEY",
        "ROUTER9_API_KEY",
        "NINE_ROUTER_API_KEY",
    ):
        value = get_env(env_name, "")
        if value:
            return value
    return "9router-local"


def _flowchart_max_tokens_field() -> str:
    field_name = get_env("FLOWCHART_MAX_TOKENS_FIELD", "max_tokens")
    if field_name not in {"max_tokens", "max_completion_tokens"}:
        raise RuntimeError(
            "FLOWCHART_MAX_TOKENS_FIELD must be max_tokens or max_completion_tokens in .env."
        )
    return field_name


def _send_flowchart_vision_text(
    image_bytes: bytes,
    model_name: str,
    prompt: str,
) -> str:
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError(
            "Dependency OpenAI belum terpasang. Jalankan pip install -r requirements.txt."
        ) from error

    data_url = (
        f"data:{_image_media_type(image_bytes)};base64,"
        f"{base64.b64encode(image_bytes).decode('ascii')}"
    )
    system_prompt = (
        "You read flowchart images and return only the requested structured text. "
        "Do not explain your reasoning. Do not use markdown tables, JSON, or code fences."
    )
    strict_prompt = (
        f"/no_think\n{prompt}\n\n"
        "Output only the two requested sections: 'Tahapan yang terbaca:' and "
        "'Hubungan dan arah alur:'. Do not write any other sentence."
    )
    try:
        client = OpenAI(
            api_key=_flowchart_api_key(),
            base_url=_flowchart_base_url(),
            timeout=get_int_env("FLOWCHART_TIMEOUT_SECONDS", 240),
        )
        request_payload: dict[str, Any] = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": strict_prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "temperature": 0,
            _flowchart_max_tokens_field(): get_int_env("FLOWCHART_MAX_COMPLETION_TOKENS", 2048),
            "top_p": 0.95,
            "stream": False,
        }
        completion = client.chat.completions.create(**request_payload)
    except Exception as error:
        raise RuntimeError(f"Flowchart vision request failed: {error}") from error

    content = _chat_message_content(completion)
    if not content.strip():
        raise RuntimeError("Flowchart vision returned an empty response")
    return _clean_flowchart_text(content)


def _call_flowchart_vision(image_bytes: bytes, model_name: str) -> str:
    return _send_flowchart_vision_text(image_bytes, model_name, FLOWCHART_PROMPT)


def extract_flowchart_documents(pdf_path: Path) -> list[Document]:
    """Ekstrak hanya image flowchart yang terdeteksi menjadi Document retrieval."""
    if not _is_enabled():
        return []

    started_at = perf_counter()
    model_name = get_env("FLOWCHART_MODEL", get_env("MODEL", "kiro/auto"))
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

            try:
                if cached_payload and cached_payload.get("status") == "success":
                    result = cached_payload.get("result")
                    if not isinstance(result, dict):
                        raise RuntimeError("Cached flowchart result is invalid")
                    flowchart_text = str(result.get("text") or "").strip()
                    if not flowchart_text:
                        raise RuntimeError("Cached flowchart text is empty")
                    cache_status = "hit"
                else:
                    image_bytes = pdf.extract_image(xref)["image"]
                    flowchart_text = _call_flowchart_vision(image_bytes, model_name)
                    if not flowchart_text.strip():
                        raise RuntimeError("Flowchart vision returned empty flowchart text")
                    result = {
                        "title": "Alur Proses",
                        "confidence": 1.0,
                        "text": flowchart_text,
                    }
                    cache_status = "miss"

                if cache_status != "hit":
                    _write_cache(
                        cache_path,
                        {
                            "status": "success",
                            "source": pdf_path.name,
                            "image_page": candidate.image_page,
                            "model": model_name,
                            "prompt_version": FLOWCHART_PROMPT_VERSION,
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
                "extraction_method": "openai_compatible_vision",
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
                    "flowchart_text_chars": len(flowchart_text),
                }
            )

            flowchart_documents.append(
                Document(
                    page_content=f"{candidate.section}\n{flowchart_text}".strip(),
                    metadata=metadata,
                )
            )

    _record_flowchart_timing(
        perf_counter() - started_at,
        len(flowchart_documents),
    )
    return flowchart_documents
