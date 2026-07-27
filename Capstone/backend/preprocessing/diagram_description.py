from __future__ import annotations

import base64
import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from backend.observability import openai_client_class, openai_observation_kwargs
from backend.openai_compat import (
    extract_chat_message_content,
    openai_client_kwargs,
    openai_request_kwargs,
    resolve_openai_compatible_api_key,
)
from backend.settings import get_env, get_int_env

LOGGER = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parents[2]
NO_DIAGRAM_SENTINEL = "NO_DIAGRAM_FOUND"

_SYSTEM_PROMPT = f"""You describe process-flow diagrams, flowcharts, and organizational charts found
on document pages. Transcribe every step, decision branch, label, arrow direction, and connection you
can see, in the order the flow follows, as plain structured text (numbered steps or indented bullets).
Preserve the diagram's original language. Do not add steps or facts that are not visibly present.

If the page does NOT contain any diagram, flowchart, chart, or organizational chart -- for example if
it is a page of paragraphs, a table, a cover page, or a blank/near-blank page -- respond with exactly
this token and nothing else: {NO_DIAGRAM_SENTINEL}"""


def _model_identity() -> str:
    return get_env("MODEL", "kr/claude-sonnet-4.5")


def _cache_dir() -> Path:
    configured = Path(get_env("DIAGRAM_CACHE_DIR", "backend/cache/diagrams"))
    return configured if configured.is_absolute() else ROOT_DIR / configured


def _cache_path(image_hash: str, model: str) -> Path:
    key = hashlib.sha256(f"{model}:{image_hash}".encode("utf-8")).hexdigest()
    return _cache_dir() / f"{key}.txt"


def _read_cache(cache_path: Path) -> str | None:
    try:
        cached = cache_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return cached or None


def _write_cache(cache_path: Path, description: str) -> None:
    cache_dir = cache_path.parent
    temp_path: Path | None = None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=cache_dir, delete=False, suffix=".tmp"
        ) as handle:
            handle.write(description)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(temp_path, cache_path)
        temp_path = None
    except OSError as error:
        LOGGER.warning("Could not write diagram description cache %s: %s", cache_path, error)
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _request_diagram_description(image_png_bytes: bytes) -> str:
    base_url = get_env("CHAT_BASE_URL", "http://localhost:20128/v1").rstrip("/")
    api_key = resolve_openai_compatible_api_key(
        base_url=base_url,
        primary_env="CHAT_API_KEY",
        fallback_envs=("OPENAI_API_KEY", "ROUTER9_API_KEY", "NINE_ROUTER_API_KEY"),
    )
    client = openai_client_class()(
        **openai_client_kwargs(
            api_key=api_key,
            base_url=base_url,
            timeout=get_int_env("CHAT_TIMEOUT_SECONDS", 240),
        )
    )
    encoded_image = base64.b64encode(image_png_bytes).decode("ascii")
    payload: dict[str, Any] = {
        "model": _model_identity(),
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Describe the process-flow diagram or org chart on this document page.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded_image}"},
                    },
                ],
            },
        ],
        "temperature": 0,
        "max_tokens": get_int_env("DIAGRAM_DESCRIPTION_MAX_TOKENS", 1024),
        "stream": False,
    }
    payload.update(openai_request_kwargs(api_key=api_key, base_url=base_url))
    payload.update(
        openai_observation_kwargs(
            "describe-page-diagram",
            metadata={"operation": "describe-page-diagram"},
        )
    )
    return extract_chat_message_content(client.chat.completions.create(**payload))


def describe_page_diagram(image_png_bytes: bytes) -> str:
    model = _model_identity()
    image_hash = hashlib.sha256(image_png_bytes).hexdigest()
    cache_path = _cache_path(image_hash, model)

    cached = _read_cache(cache_path)
    if cached is not None:
        return cached

    try:
        description = _request_diagram_description(image_png_bytes).strip()
    except Exception as error:
        LOGGER.warning("Diagram description request failed: %s", error)
        return ""

    if description:
        _write_cache(cache_path, description)
    return description
